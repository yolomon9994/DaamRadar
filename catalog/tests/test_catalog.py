from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import PriceHistory, Product, RetailerListing
from catalog.services.catalog import decorate, get_product_queryset, search_catalog


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())

    def test_homepage_search_and_source_page(self):
        for path in ["/", "/?q=milk", "/?source=live", "/sources/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "DaamRadar")
        self.assertContains(self.client.get("/"), "fictional examples")
        self.assertContains(self.client.get("/?source=live"), "No live prices have been collected yet")

    def test_partial_case_insensitive_and_typo_searches(self):
        for query in ["OLPERS", "Olpers Milk 1000ml", "nutela", "surf exel", "ketch"]:
            with self.subTest(query=query):
                self.assertGreater(len(search_catalog({"q": query})), 0)
        self.assertEqual(len(search_catalog({"q": "Olpers Milk 1L"})), 1)
        self.assertEqual(len(search_catalog({"q": "unfindable9876"})), 0)

    def test_filters_combine_and_offer_filter_changes_comparison(self):
        products = search_catalog({"category": "dairy", "brand": "Olper's", "retailer": "springs"})
        self.assertEqual(len(products), 2)
        self.assertTrue(all(p.offer_count == 1 for p in products))
        self.assertTrue(all(p.offers[0].retailer.slug == "springs" for p in products))

    def test_price_sorting(self):
        ascending = [p.best_price for p in search_catalog({"sort": "price_asc"})]
        descending = [p.best_price for p in search_catalog({"sort": "price_desc"})]
        self.assertEqual(ascending, sorted(ascending))
        self.assertEqual(descending, sorted(ascending, reverse=True))

    def test_demo_and_live_are_separate(self):
        self.assertEqual(search_catalog({"source": "live"}), [])
        self.assertEqual(len(search_catalog({"source": "demo"})), 12)

    def test_out_of_stock_unknown_and_stale_are_not_best(self):
        product = Product.objects.get(slug="demo-olpers-milk-1l")
        listings = list(product.listings.order_by("current_price"))
        listings[0].availability = "out_of_stock"
        listings[0].save()
        listings[1].availability = "unknown"
        listings[1].save()
        product = decorate(get_product_queryset().get(pk=product.pk))
        self.assertEqual(product.best_price, Decimal("340"))
        RetailerListing.objects.filter(pk=listings[2].pk).update(last_checked=timezone.now() - timedelta(days=3))
        product = decorate(get_product_queryset().get(pk=product.pk))
        self.assertIsNone(product.best_price)
        self.assertFalse(product.best_ids)

    def test_mixed_areas_prevent_winner(self):
        listing = RetailerListing.objects.filter(product__slug="demo-olpers-milk-1l").first()
        listing.delivery_area = "Different area"
        listing.save()
        product = decorate(get_product_queryset().get(pk=listing.product_id))
        self.assertTrue(product.has_mixed_areas)
        self.assertFalse(product.best_ids)
        self.assertEqual(product.savings, 0)

    def test_detail_prices_are_sorted_and_demo_links_disabled(self):
        response = self.client.get("/products/demo-olpers-milk-1l/")
        self.assertEqual(response.status_code, 200)
        prices = [offer.current_price for offer in response.context["product"].offers]
        self.assertEqual(prices, sorted(prices))
        self.assertContains(response, "Demo only", count=3)
        self.assertNotContains(response, "Visit retailer")
        self.assertEqual(self.client.get("/products/missing/").status_code, 404)

    def test_seed_rerun_is_idempotent(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))

    def test_api_filters_serializes_and_refuses_writes(self):
        url = reverse("api-products")
        response = self.client.get(url, {"q": "Olpers Milk 1L"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        product = data["results"][0]
        self.assertEqual(product["best_price"], "325.00")
        self.assertTrue(product["is_demo"])
        self.assertEqual(len(product["listings"]), 3)
        self.assertEqual(self.client.post(url, {}).status_code, 405)
        self.assertEqual(self.client.get(url, {"source": "live"}).json()["count"], 0)
        self.assertEqual(self.client.get(url, {"page_size": 2}).json()["count"], 12)
        self.assertEqual(len(self.client.get(url, {"page_size": 2}).json()["results"]), 2)

    def test_history_api_and_unknown_listing(self):
        listing = RetailerListing.objects.first()
        response = self.client.get(reverse("api-history", args=[listing.pk]))
        self.assertEqual(response.json()["count"], 1)
        self.assertTrue(response.json()["results"][0]["is_demo"])
        self.assertEqual(self.client.get(reverse("api-history", args=[999999])).status_code, 404)

    def test_queries_are_escaped(self):
        response = self.client.get("/", {"q": '<script>alert("x")</script>'})
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
