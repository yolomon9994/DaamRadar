"""Observed pantry pairs and regression checks for the existing milk catalog."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from catalog.matching.normalization import identify, match_score
from catalog.models import Category, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.reviewed import MILK_COMPARISON_PRODUCTS, PANTRY_COMPARISON_PRODUCTS, REVIEWED_PRODUCTS
from catalog.scraping.types import CollectionError
from catalog.services.ingestion import ingest

FIXTURES = Path(__file__).parent / "fixtures"
SUFFIXES = ("dalda_sunflower_1000", "dalda_canola_4500", "shan_biryani_50")
PRICES = (("609", "630"), ("2834", "3150"), ("158", "130"))


def pages(source):
    prefix, origin, key = (("jalal", "https://www.jalalsons.com.pk", "jalal_path") if source == "jalal-sons"
                           else ("cartpk", "https://www.cartpk.com", "cartpk_path"))
    return {origin + item[key]: (FIXTURES / f"{prefix}_{suffix}.html").read_text(encoding="utf-8")
            for item, suffix in zip(PANTRY_COMPARISON_PRODUCTS, SUFFIXES)}


def collect(source, url, html):
    client = MagicMock()
    client.get_html.return_value = html
    return (JalalSonsAdapter() if source == "jalal-sons" else CartpkAdapter()).collect(client, url)


class PantryParserTests(SimpleTestCase):
    def test_observed_titles_prices_sizes_and_packaging_match_without_rewriting_titles(self):
        items = {source: [collect(source, url, html) for url, html in pages(source).items()]
                 for source in ("jalal-sons", "cartpk")}
        for index, pair in enumerate(PRICES):
            for source, price in zip(("jalal-sons", "cartpk"), pair):
                item = items[source][index]
                self.assertEqual(item.price, Decimal(price))
                self.assertEqual(item.currency, "PKR")
                self.assertEqual(item.availability, "in_stock")
                self.assertEqual(item.image, "")
                self.assertIn("unverified", item.delivery_area)
                identity = identify(item.title, item.brand)
                self.assertEqual(identity.quantity, (1000, 4500, 50)[index])
                self.assertEqual(identity.unit, ("ml", "ml", "g")[index])
                self.assertEqual(identity.pack_count, 1)
            self.assertEqual(match_score(identify(items["jalal-sons"][index].title, items["jalal-sons"][index].brand),
                                         identify(items["cartpk"][index].title)), 100)
        self.assertEqual(identify(items["cartpk"][0].title).packaging, frozenset({"pouch"}))
        # Unspecified packaging stays unspecified; no bottle/tin inference from the 4.5L size.
        self.assertEqual(identify(items["cartpk"][1].title).packaging, frozenset())

    def test_each_source_rejects_quantity_variant_packaging_or_pack_drift(self):
        for source in ("jalal-sons", "cartpk"):
            for index, (url, html) in enumerate(pages(source).items()):
                title = BeautifulSoup(html, "html.parser").h1.get_text()
                changed_titles = [title + " pack of 5", title + " Bottle", title + " Box", title + " Promo"]
                changed_titles.append(title.replace("1Ltr", "2Ltr").replace("4.5L", "3L").replace("50G", "100G"))
                changed_titles.append(title.replace("SunFlower", "Canola").replace("SUNFLOWER", "CANOLA")
                                      if index == 0 else title.replace("Canola", "Corn") if index == 1
                                      else title.replace("Biryani", "Sindhi Biryani"))
                for changed in changed_titles:
                    with self.subTest(source=source, url=url, changed=changed), self.assertRaises(CollectionError):
                        # Change JSON-LD name and visible heading together on Jalal Sons.
                        collect(source, url, html.replace(title, changed))

    def test_wrong_product_at_an_allowed_url_still_fails(self):
        mapping = pages("cartpk")
        urls = list(mapping)
        for index, url in enumerate(urls):
            wrong_url = urls[(index + 1) % len(urls)]
            with self.subTest(url=url), self.assertRaises(CollectionError):
                collect("cartpk", url, mapping[wrong_url].replace(wrong_url, url))

    def test_unreviewed_nearby_urls_and_url_options_fail_before_fetch(self):
        client = MagicMock()
        url = next(iter(pages("cartpk")))
        for candidate in (url + "/", url + "?size=1", url + "#variant", url.replace("https:", "http:"),
                          url.replace("www.cartpk.com", "example.test"),
                          "https://www.cartpk.com/dalda-cooking-oil-pouch-1l-5pcs", "https://www.cartpk.com/shan-biryani-masala-100g"):
            with self.subTest(candidate=candidate), self.assertRaises(CollectionError):
                CartpkAdapter().collect(client, candidate)
        client.get_html.assert_not_called()

    def test_oil_and_spice_variants_have_hard_identity_guards(self):
        for left, right in (("Dalda Sunflower Oil Pouch 1L", "Dalda Canola Oil Pouch 1L"),
                            ("Dalda Canola Oil 4.5L", "Dalda Corn Oil 4.5L"),
                            ("Shan Biryani Masala 50g", "Shan Sindhi Biryani Masala 50g"),
                            ("Shan Biryani Masala 50g", "Shan Chicken Biryani Masala 50g"),
                            ("Dalda Sunflower Oil Pouch 1L", "Dalda Sunflower Oil Bottle 1L")):
            with self.subTest(left=left, right=right):
                self.assertEqual(match_score(identify(left), identify(right)), 0)

    def test_new_registry_keeps_original_milk_pairs_and_unreviewed_urls_excluded(self):
        self.assertEqual(len(MILK_COMPARISON_PRODUCTS), 5)
        self.assertTrue(all(item in REVIEWED_PRODUCTS for item in PANTRY_COMPARISON_PRODUCTS))
        self.assertTrue(all(item["cartpk_path"] in CartpkAdapter.reviewed_titles for item in PANTRY_COMPARISON_PRODUCTS))


@override_settings(SCRAPING_ENABLED=True)
class PantryCatalogTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        Retailer.objects.filter(slug__in=("jalal-sons", "cartpk")).update(status="enabled", collection_enabled=True)

    def batch(self, source, page_mapping=None):
        mapping = pages(source) if page_mapping is None else page_mapping
        with patch("catalog.management.commands.scrape.PoliteClient") as factory:
            factory.return_value.get_html.side_effect = mapping.__getitem__
            factory.return_value.request_count = 4
            call_command("scrape", source, batch=f"{source}-pantry-comparison", stdout=StringIO())

    def assert_catalog(self):
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 3)
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 6)
        self.assertEqual(Product.objects.filter(is_demo=True).count(), 12)
        for product in Product.objects.filter(is_demo=False):
            self.assertEqual(product.category.slug, "pantry")
            self.assertEqual(product.illustration, "spice" if product.brand == "shan" else "oil")
            self.assertEqual(product.listings.count(), 2)
            response = self.client.get(f"/products/{product.slug}/")
            self.assertContains(response, "Visit retailer", count=2)
            self.assertContains(response, "Delivery areas may differ or be unverified")
            history = BeautifulSoup(response.content, "html.parser").select_one("[data-price-history]")
            self.assertEqual(len(history.select("circle")), product.listings.count())
            data = self.client.get(f"/api/products/{product.slug}/").json()
            self.assertEqual(len(data["listings"]), 2)
            self.assertFalse(data["has_comparison"])
            self.assertFalse(any(item["is_best"] or item["is_demo"] for item in data["listings"]))
            self.assertEqual([Decimal(item["current_price"]) for item in data["listings"]], sorted(product.listings.values_list("current_price", flat=True)))

    def test_three_pairs_import_and_repeat_without_duplicates_or_demo_changes(self):
        before = list(RetailerListing.objects.filter(is_demo=True).values())
        self.batch("jalal-sons")
        self.batch("cartpk")
        self.assert_catalog()
        ids = set(RetailerListing.objects.filter(is_demo=False).values_list("pk", flat=True))
        self.batch("jalal-sons")
        self.batch("cartpk")
        self.assertEqual(set(RetailerListing.objects.filter(is_demo=False).values_list("pk", flat=True)), ids)
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 3)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 12)
        self.assertTrue(all(listing.history.count() == 2 for listing in RetailerListing.objects.filter(is_demo=False)))
        self.assertEqual(before, list(RetailerListing.objects.filter(is_demo=True).values()))

    def test_reverse_import_order_links_the_same_pairs(self):
        self.batch("cartpk")
        self.batch("jalal-sons")
        self.assert_catalog()

    def test_category_brand_quantity_and_retailer_filters_use_collected_pantry_records(self):
        self.batch("jalal-sons")
        self.batch("cartpk")
        self.assertEqual(self.client.get("/api/products/?source=live&category=pantry").json()["count"], 3)
        self.assertEqual(self.client.get("/api/products/?source=live&category=dairy").json()["count"], 0)
        data = self.client.get("/api/products/?source=live&category=pantry&brand=dalda&retailer=cartpk").json()
        self.assertEqual(data["count"], 2)
        self.assertTrue(all(len(product["listings"]) == 1 for product in data["results"]))
        self.assertEqual(self.client.get("/api/products/?source=live&q=Dalda+Canola+Oil+4500ml").json()["count"], 1)
        self.assertEqual(self.client.get("/api/products/?source=live&q=Dalda+Sunflower+Oil+Pouch+1L").json()["count"], 1)
        response = self.client.get("/?source=live&category=pantry")
        self.assertContains(response, "Pantry essentials")
        self.assertEqual(response.context["page_obj"].paginator.count, 3)

    @override_settings(SCRAPING_ENABLED=False)
    def test_new_batches_preview_without_network_or_writes(self):
        for source in ("jalal-sons", "cartpk"):
            output = StringIO()
            with patch("requests.Session.get") as get:
                call_command("scrape", source, batch=f"{source}-pantry-comparison", dry_run=True, stdout=output)
            get.assert_not_called()
            self.assertIn("Dry run: 3 URL(s)", output.getvalue())
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertFalse(Product.objects.filter(is_demo=False).exists())

    def test_price_metadata_failure_preserves_previous_observation(self):
        self.batch("cartpk")
        before = list(RetailerListing.objects.filter(is_demo=False).values())
        history_count = PriceHistory.objects.count()
        mapping = pages("cartpk")
        url = next(iter(mapping))
        mapping[url] = mapping[url].replace('content="630.00"', 'content="1.00"')
        with self.assertRaises(CommandError):
            self.batch("cartpk", mapping)
        self.assertEqual(before, list(RetailerListing.objects.filter(is_demo=False).values()))
        self.assertEqual(PriceHistory.objects.count(), history_count)

    def test_sequential_refresh_updates_stale_pantry_listings_and_skips_fresh_records(self):
        self.batch("jalal-sons")
        self.batch("cartpk")
        RetailerListing.objects.filter(is_demo=False).update(last_checked=timezone.now() - timedelta(days=3))

        def client_for(origin):
            source = "jalal-sons" if "jalalsons" in origin else "cartpk"
            client = MagicMock()
            client.get_html.side_effect = pages(source).__getitem__
            client.request_count = 4
            return client

        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=client_for):
            call_command("refresh_prices", stdout=StringIO())
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 3)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 12)
        with patch("requests.Session.get") as get, patch("catalog.management.commands.scrape.PoliteClient") as factory:
            call_command("refresh_prices", stdout=StringIO())
        get.assert_not_called()
        factory.assert_not_called()


@override_settings(SCRAPING_ENABLED=True)
class PantryWithoutDemoTests(TestCase):
    def test_real_only_setup_creates_the_reviewed_category_without_loading_demo_products(self):
        call_command("seed_retailers", stdout=StringIO())
        Retailer.objects.filter(slug="cartpk").update(status="enabled", collection_enabled=True)
        self.assertEqual(Category.objects.count(), 0)
        mapping = pages("cartpk")
        with patch("catalog.management.commands.scrape.PoliteClient") as factory:
            factory.return_value.get_html.side_effect = mapping.__getitem__
            call_command("scrape", "cartpk", batch="cartpk-pantry-comparison", stdout=StringIO())
        self.assertEqual(Category.objects.get().slug, "pantry")
        self.assertFalse(Product.objects.filter(is_demo=True).exists())
        self.assertEqual(Product.objects.filter(category__slug="pantry", is_demo=False).count(), 3)
