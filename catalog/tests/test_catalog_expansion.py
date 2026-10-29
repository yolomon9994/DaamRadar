"""Reviewed factual extracts exercise parsing, import and bounded refresh offline."""
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
from catalog.models import PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.batches import BATCHES, reviewed_urls
from catalog.scraping.expansion import EXPANSION_PRODUCTS
from catalog.scraping.types import CollectionError
from catalog.services.catalog_import import get_import_batch, plan_import
from catalog.services.admin_refresh import validate_refresh

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = {"jalal-sons": ("jalal", "https://www.jalalsons.com.pk", "jalal_path", JalalSonsAdapter),
           "cartpk": ("cartpk", "https://www.cartpk.com", "cartpk_path", CartpkAdapter)}
EXPECTED = {"dalda_ghee_5000": "3044", "dalda_ghee_2500": "1574", "tapal_bags_100": "899",
            "lipton_430": "1008", "surf_1000": "640", "yogurt_plain_200": "164",
            "yogurt_strawberry_100": "110", "milkpak_cream_200": "228", "milkpak_butter_200": "658",
            "nesfruta_mango_1000": "249", "milo_180": "94", "milo_tin_235": "594",
            "national_chat_100": "188", "national_biryani_45": "158", "national_ginger_50": "244",
            "national_salt_800": "60", "national_chilli_100": "198", "evian_500": "594",
            "malee_coconut_330": "548", "everyday_15": "30", "shan_korma_50": "350",
            "national_chat_50": "170"}


def pages(source):
    prefix, origin, key, _ = SOURCES[source]
    return {origin + item[key]: (FIXTURES / f"{prefix}_expanded_{item['key']}.html").read_text(encoding="utf-8")
            for item in EXPANSION_PRODUCTS if key in item}


def collect(source, url, html):
    client = MagicMock()
    client.get_html.return_value = html
    return SOURCES[source][3]().collect(client, url)


class ExpansionParserTests(SimpleTestCase):
    def test_all_reviewed_factual_extracts_keep_identity_price_stock_and_unknown_area(self):
        for source, (_, origin, key, _) in SOURCES.items():
            for profile in EXPANSION_PRODUCTS:
                if key not in profile:
                    continue
                url = origin + profile[key]
                with self.subTest(source=source, product=profile["key"]):
                    item = collect(source, url, pages(source)[url])
                    price = "250" if source == "cartpk" and profile["key"] == "milkpak_cream_200" else EXPECTED[profile["key"]]
                    self.assertEqual(item.price, Decimal(price))
                    self.assertEqual(item.availability, "in_stock")
                    self.assertEqual(item.currency, "PKR")
                    self.assertEqual(item.image, "")
                    self.assertIn("unverified", item.delivery_area)
                    self.assertEqual(match_score(identify(item.title, item.brand), identify(profile["title"])), 100)
                    self.assertIsNotNone(identify(item.title, item.brand).quantity)

    def test_all_new_saved_batches_are_bounded_exact_and_have_fixtures(self):
        seen = {source: set() for source in SOURCES}
        for key, batch in BATCHES.items():
            if "-expanded-" not in key:
                continue
            self.assertGreater(len(batch["urls"]), 0)
            self.assertLessEqual(len(batch["urls"]), 10)
            self.assertEqual(len(batch["urls"]), len(set(batch["urls"])))
            self.assertEqual(get_import_batch(key)[1], batch["urls"])
            seen[batch["retailer"]].update(batch["urls"])
        for source in SOURCES:
            self.assertEqual(seen[source], set(pages(source)))
            self.assertTrue(seen[source] <= reviewed_urls(source))

    def test_every_new_reviewed_url_rejects_identity_drift(self):
        for source in SOURCES:
            for url, html in pages(source).items():
                title = BeautifulSoup(html, "html.parser").h1.get_text()
                for changed in (title + " Pack of 5", title + " Promo", title + " Bottle" if "Tin" in title else title + " Tin"):
                    with self.subTest(url=url, changed=changed), self.assertRaises(CollectionError):
                        collect(source, url, html.replace(title, changed))

    def test_new_cartpk_urls_still_require_matching_currency_and_price_evidence(self):
        for url, html in pages("cartpk").items():
            for changed in (html.replace('content="PKR"', 'content="USD"'),
                            html.replace('data-price-amount="', 'data-price-amount="1'),
                            html.replace('In stock', 'Out of stock')):
                with self.subTest(url=url), self.assertRaises(CollectionError):
                    collect("cartpk", url, changed)
        client = MagicMock()
        with self.assertRaises(CollectionError):
            CartpkAdapter().collect(client, "https://www.cartpk.com/shan-korma-masala-100g")
        client.get_html.assert_not_called()

    def test_incomplete_brand_only_listing_is_not_assumed_to_be_detergent(self):
        self.assertEqual(match_score(identify("Surf Excel 1 KG", "Surf"),
                                     identify("Surf Excel Detergent Powder 1kg")), 0)


@override_settings(SCRAPING_ENABLED=True, SCRAPER_CONTACT="operator@example.invalid")
class ExpansionImportTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        Retailer.objects.filter(slug__in=SOURCES).update(status="enabled", collection_enabled=True)
        self.fetched = []

    def factory(self, origin):
        source = "cartpk" if "cartpk" in origin else "jalal-sons"
        client = MagicMock()
        client.request_count = 0

        def fetch(url):
            self.fetched.append(url)
            return pages(source)[url]

        client.get_html.side_effect = fetch
        return client

    def import_all(self, order=("jalal-sons", "cartpk"), missing_only=False):
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.factory):
            for source in order:
                for key, batch in BATCHES.items():
                    if batch["retailer"] == source and "-expanded-" in key:
                        call_command("scrape", source, batch=key, missing_only=missing_only, stdout=StringIO())

    def assert_catalog(self):
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 22)
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 23)
        self.assertEqual(Product.objects.filter(is_demo=True).count(), 12)
        cream = Product.objects.get(is_demo=False, canonical_name__icontains="Cream")
        self.assertEqual(cream.listings.count(), 2)
        for product in Product.objects.filter(is_demo=False):
            data = self.client.get(f"/api/products/{product.slug}/").json()
            self.assertEqual(data["category"], product.category.name)
            self.assertFalse(data["has_comparison"])
            self.assertFalse(any(row["is_best"] or row["is_demo"] for row in data["listings"]))
            self.assertTrue(all(row["price_change"]["status"] == "no_previous" for row in data["listings"]))
            detail = self.client.get(f"/products/{product.slug}/")
            self.assertContains(detail, "Visit retailer", count=product.listings.count())
            self.assertContains(detail, "Delivery areas may differ or be unverified")
        for category, count in (("dairy", 5), ("pantry", 9), ("drinks", 7), ("household", 1)):
            self.assertEqual(self.client.get(f"/api/products/?source=live&category={category}").json()["count"], count)
        self.assertEqual(Product.objects.filter(is_demo=False, brand="national", canonical_name__icontains="Chat").count(), 2)

    def test_imports_categorize_pair_cream_keep_sizes_separate_and_preserve_demo(self):
        demo_before = list(RetailerListing.objects.filter(is_demo=True).values())
        self.import_all()
        self.assert_catalog()
        self.assertEqual(demo_before, list(RetailerListing.objects.filter(is_demo=True).values()))
        self.assertTrue(all(row.context["version"] == 1 for row in PriceHistory.objects.filter(listing__is_demo=False)))
        before = list(RetailerListing.objects.filter(is_demo=False).values())
        self.fetched.clear()
        self.import_all(missing_only=True)
        self.assertEqual(before, list(RetailerListing.objects.filter(is_demo=False).values()))
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 23)
        self.assertEqual(self.fetched, [])
        for key in BATCHES:
            if "-expanded-" in key:
                self.assertEqual(plan_import(key)["missing_count"], 0)

    def test_reverse_source_order_still_pairs_only_the_reviewed_cream(self):
        self.import_all(order=("cartpk", "jalal-sons"))
        self.assert_catalog()

    def test_fresh_checkout_without_demo_creates_all_four_categories(self):
        Product.objects.all().delete()
        from catalog.models import Category
        Category.objects.all().delete()
        self.import_all()
        self.assertEqual(set(Category.objects.values_list("slug", flat=True)), {"dairy", "pantry", "drinks", "household"})
        self.assertFalse(Product.objects.filter(is_demo=True).exists())

    def test_new_batch_dry_runs_do_not_access_network_or_create_data(self):
        with patch("requests.Session.get") as get:
            for key, batch in BATCHES.items():
                if "-expanded-" in key:
                    call_command("scrape", batch["retailer"], batch=key, dry_run=True, stdout=StringIO())
        get.assert_not_called()
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertFalse(Product.objects.filter(is_demo=False).exists())

    def test_expanded_admin_refresh_accepts_a_bounded_selection_and_successive_runs_finish_it(self):
        self.import_all()
        RetailerListing.objects.filter(is_demo=False).update(last_checked=timezone.now() - timedelta(days=3))
        validate_refresh(["jalal-sons", "cartpk"])
        self.fetched.clear()
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.factory):
            call_command("refresh_prices", stdout=StringIO())
        first_urls = set(self.fetched)
        self.assertEqual(len(first_urls), 14)  # ten Jalal Sons plus four Cartpk
        self.assertEqual(RetailerListing.objects.filter(is_demo=False, last_checked__lt=timezone.now() - timedelta(days=2)).count(), 9)
        self.fetched.clear()
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.factory):
            call_command("refresh_prices", stdout=StringIO())
        self.assertEqual(len(self.fetched), 9)
        self.assertFalse(first_urls & set(self.fetched))
        self.assertTrue(all(len(run.results) <= 10 for run in ScrapeRun.objects.all()))
        with patch("catalog.management.commands.scrape.PoliteClient") as factory:
            call_command("refresh_prices", stdout=StringIO())
        factory.assert_not_called()

    def test_arbitrary_eleven_url_import_is_still_rejected_before_fetch(self):
        with patch("catalog.management.commands.scrape.PoliteClient") as factory, self.assertRaisesMessage(CommandError, "At most 10"):
            call_command("scrape", "jalal-sons", url=list(pages("jalal-sons"))[:11], stdout=StringIO())
        factory.assert_not_called()
