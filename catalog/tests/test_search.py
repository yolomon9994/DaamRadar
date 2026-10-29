"""Offer filters must match one observation while preserving comparison context."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import AdminPriceRefresh, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.search_filters import InvalidOfferFilters, offer_filters
from catalog.services.catalog import decorate, get_product_queryset, search_catalog, search_suggestions


@override_settings(PRICE_STALE_HOURS=48)
class SearchImprovementsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.now = datetime(2026, 10, 29, 12, tzinfo=datetime_timezone.utc)
        cls.product = Product.objects.create(slug="search-olpers-1l", canonical_name="Olpers Milk 1L", brand="olpers", quantity=1000, unit="ml")

    def listing(self, *, price="350", hours=1, stock="in_stock", source="jalal-sons", key="milk", product=None):
        return RetailerListing.objects.create(product=product or self.product, retailer=Retailer.objects.get(slug=source),
            external_id=key, original_title=(product or self.product).canonical_name, current_price=price,
            last_checked=self.now - timedelta(hours=hours), availability=stock,
            delivery_area="Delivery area unverified")

    def search(self, **params):
        return search_catalog({"source": "live", **params}, now=self.now)

    def get(self, url="/", **params):
        with patch("catalog.services.catalog.timezone.now", return_value=self.now):
            return self.client.get(url, {"source": "live", **params})

    def test_fresh_cutoff_is_inclusive_and_excludes_future_while_stock_is_separate(self):
        self.listing(hours=48, stock="unknown")
        self.listing(hours=49, source="cartpk")
        self.listing(hours=-1, source="naheed")
        products = self.search(fresh="1")
        self.assertEqual(len(products), 1)
        self.assertEqual([o.retailer.slug for o in products[0].offers if o.matches_offer_filters], ["jalal-sons"])
        self.assertEqual(self.search(fresh="1", in_stock="1"), [])
        self.assertEqual(len(self.search(in_stock="1")), 1)
        self.assertIsNone(products[0].best_price)

    @override_settings(PRICE_STALE_HOURS=12)
    def test_custom_freshness_window_and_future_prices_cannot_be_best(self):
        self.listing(hours=13)
        self.listing(hours=-1, source="cartpk", price="1")
        self.assertEqual(self.search(fresh="1"), [])
        product = decorate(get_product_queryset().get(pk=self.product.pk), now=self.now)
        self.assertIsNone(product.best_price)
        self.assertEqual(sum(o.check_time_is_future for o in product.offers), 1)
        self.assertContains(self.get(), "Check time needs review")
        data = self.get(reverse("api-products")).json()["results"][0]
        self.assertEqual(sum(o["check_time_is_future"] for o in data["listings"]), 1)

    def test_offer_conditions_must_match_the_same_listing(self):
        self.listing(price="100", hours=72)
        self.listing(price="300", source="cartpk")
        self.assertEqual(self.search(fresh="1", max_price="200"), [])
        self.assertEqual(len(self.search(max_price="200")), 1)
        self.assertEqual(self.search(retailer="jalal-sons", fresh="1"), [])
        self.assertEqual(len(self.search(retailer="cartpk", fresh="1", min_price="300", max_price="300.00")), 1)

    def test_decimal_range_is_inclusive_and_uses_pack_not_standard_unit_price(self):
        self.product.quantity = 250
        self.product.canonical_name = "Olpers Milk 250ml"
        self.product.save()
        self.listing(price="85.25")
        self.assertEqual(len(self.search(min_price="85.25", max_price="85.25")), 1)
        self.assertEqual(self.search(max_price="85.24"), [])
        self.assertEqual(self.search(min_price="85.26"), [])
        self.assertEqual(self.search(min_price="341"), [])
        self.assertEqual(len(self.search(min_price="0")), 1)

    def test_filtered_results_keep_all_offers_and_do_not_manufacture_a_winner(self):
        cheap = self.listing(price="300")
        expensive = self.listing(price="400", source="cartpk")
        product = self.search(min_price="350")[0]
        self.assertEqual(product.best_price, Decimal("300"))
        self.assertEqual([o.pk for o in product.offers], [cheap.pk, expensive.pk])
        self.assertEqual([o.matches_offer_filters for o in product.offers], [False, True])
        self.assertFalse(product.has_comparison)
        for listing in (cheap, expensive):
            listing.delivery_area = "Test delivery scope"
            listing.delivery_area_key = "test-scope"
            listing.area_evidence_url = listing.retailer.website.rstrip("/") + "/delivery-evidence"
            listing.area_verified_at = self.now
            listing.save()
        comparable = self.search(min_price="350")[0]
        self.assertTrue(comparable.has_comparison)
        self.assertEqual(comparable.best_ids, {cheap.pk})
        self.assertEqual(comparable.savings, Decimal("100"))
        response = self.get(min_price="350")
        self.assertContains(response, "Matches filters", count=2)  # one label plus the explanatory note
        self.assertContains(response, "other offers stay visible for context")
        data = self.get(reverse("api-products"), min_price="350").json()["results"][0]
        self.assertEqual(data["best_price"], "300.00")
        self.assertEqual([o["matches_offer_filters"] for o in data["listings"]], [False, True])
        self.assertTrue(all(o["matches_offer_filters"] is None for o in self.get(reverse("api-products")).json()["results"][0]["listings"]))

    def test_invalid_price_or_boolean_filters_fail_clearly_in_html_and_both_apis(self):
        cases = [{"min_price": value} for value in ("-1", "NaN", "Infinity", "1e2", "2.001", "10000000000", "abc")]
        cases += [{"fresh": "yes"}, {"in_stock": "true"}, {"min_price": "300", "max_price": "200"}]
        for params in cases:
            with self.subTest(params=params):
                with self.assertRaises(InvalidOfferFilters):
                    offer_filters(params)
                html = self.get(**params)
                self.assertEqual(html.status_code, 400)
                self.assertContains(html, "Correct the offer filters before searching", status_code=400)
                for url in (reverse("api-products"), reverse("api-search-suggestions")):
                    self.assertEqual(self.get(url, q="milk", **params).status_code, 400)

    def test_zero_and_disabled_flags_are_valid_and_price_error_keeps_input(self):
        self.listing()
        self.assertEqual(len(self.search(fresh="0", in_stock="0", min_price="0", max_price="9999999999.99")), 1)
        html = BeautifulSoup(self.get(min_price="500", max_price="300").content, "html.parser")
        self.assertEqual(html.select_one('input[name="min_price"][type="number"]')["value"], "500")
        self.assertEqual(html.select_one('input[name="max_price"][type="number"]')["value"], "300")

    def test_suggestions_use_same_catalog_size_and_offer_filters_without_prices(self):
        self.listing()
        response = self.get(reverse("api-search-suggestions"), q="Olpers Milk 1000ml", fresh="1", in_stock="1", max_price="350")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "live")
        self.assertEqual(response.json()["results"], [{"name": "Olpers Milk 1L", "size": "1 L", "slug": self.product.slug,
                                                       "url": f"/products/{self.product.slug}/"}])
        self.assertEqual(self.get(reverse("api-search-suggestions"), q="Olpers Milk 250ml").json()["results"], [])
        self.assertEqual(self.get(reverse("api-search-suggestions"), q="Milk", max_price="349.99").json()["results"], [])
        demo = self.client.get(reverse("api-search-suggestions"), {"q": "Olpers", "source": "demo"}).json()["results"]
        self.assertTrue(demo and all(row["slug"].startswith("demo-") for row in demo))
        self.assertIn("no-store", response["Cache-Control"])

    def test_suggestions_are_bounded_to_six_and_short_queries_do_no_catalog_work(self):
        for index in range(8):
            product = Product.objects.create(slug=f"extra-{index}", canonical_name=f"Olpers Milk {index + 2}L", brand="olpers", quantity=(index+2)*1000, unit="ml")
            self.listing(product=product, key=product.slug)
        self.assertEqual(len(search_suggestions({"source": "live", "q": "Olpers"})), 6)
        with self.assertNumQueries(0):
            self.assertEqual(search_suggestions({"source": "live", "q": "m"}), [])

    def test_query_variant_packaging_and_pack_size_guards_apply_to_suggestions(self):
        self.listing()
        for query in ("Olpers Chocolate Milk 1L", "Olpers Milk 6x1L", "Olpers Milk Pouch 1L", "Nestle Milk 1L"):
            self.assertEqual(search_suggestions({"source": "live", "q": query}), [])

    def test_hero_and_pagination_preserve_offer_filters_and_catalog(self):
        for index in range(13):
            product = Product.objects.create(slug=f"milk-{index}", canonical_name=f"Olpers Milk {index+2}L", brand="olpers", quantity=(index+2)*1000, unit="ml")
            self.listing(product=product, key=product.slug)
        response = self.get(fresh="1", in_stock="1", min_price="100", max_price="400", retailer="jalal-sons")
        soup = BeautifulSoup(response.content, "html.parser")
        fields = {node["name"]: node.get("value") for node in soup.select('#hero-search input[type="hidden"]')}
        for key, value in {"source":"live", "fresh":"1", "in_stock":"1", "min_price":"100", "max_price":"400", "retailer":"jalal-sons"}.items():
            self.assertEqual(fields[key], value)
        self.assertIn("fresh=1", soup.select_one('.pagination-bar a')["href"])
        self.assertIn("max_price=400", soup.select_one('.pagination-bar a')["href"])
        self.assertEqual(self.get(fresh="1", in_stock="1", min_price="100", max_price="400", retailer="jalal-sons", page="2").context["page_obj"].paginator.count, 13)

    def test_empty_filtered_state_offers_a_scoped_reset_and_ordinary_empty_state_keeps_size_warning(self):
        self.listing(hours=72)
        response = self.get(q="Olpers Milk 1L", fresh="1", retailer="jalal-sons")
        self.assertContains(response, "No listings meet these offer filters")
        soup = BeautifulSoup(response.content, "html.parser")
        reset = soup.select_one('.empty-state .primary-button')["href"]
        self.assertIn("q=Olpers+Milk+1L", reset)
        self.assertIn("retailer=jalal-sons", reset)
        self.assertNotIn("fresh=", reset)
        unmatched = self.get(q="Olpers Milk 250ml")
        self.assertContains(unmatched, "No matching products in this catalog")
        self.assertContains(unmatched, "different pack size is not automatically substituted")

    def test_search_and_suggestions_never_collect_or_write_and_unsafe_text_is_escaped(self):
        self.listing()
        models = (Product, RetailerListing, PriceHistory, ScrapeRun, AdminPriceRefresh, Retailer)
        before = [list(model.objects.order_by("pk").values()) for model in models]
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer requests")):
            self.assertEqual(self.get(q="milk", fresh="1").status_code, 200)
            self.assertEqual(self.get(reverse("api-search-suggestions"), q="milk").status_code, 200)
            self.assertEqual(self.client.post(reverse("api-search-suggestions"), {}).status_code, 405)
            self.assertContains(self.get(q='<script>alert("x")</script>'), "&lt;script&gt;")
        self.assertEqual(before, [list(model.objects.order_by("pk").values()) for model in models])
