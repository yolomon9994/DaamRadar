"""Observed pairs, sale-price scoping, title drift and repeatable batch imports."""
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.matching.normalization import identify, match_score
from catalog.models import PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.batches import BATCHES
from catalog.scraping.reviewed import MILK_COMPARISON_PRODUCTS
from catalog.scraping.types import CollectionError

FIXTURES = Path(__file__).parent / "fixtures"
SUFFIXES = ("milk", "olpers_1500", "milkpak_250", "nurpur_1000", "haleeb_1000")
PRICES = (("350", "360"), ("518", "570"), ("94", "105"), ("358", "620"), ("334", "405"))


def pages(source):
    return {
        ("https://www.cartpk.com" + product["cartpk_path"] if source == "cartpk"
         else "https://www.jalalsons.com.pk" + product["jalal_path"]):
        (FIXTURES / f'{"cartpk" if source == "cartpk" else "jalal"}_{suffix}.html').read_text(encoding="utf-8")
        for product, suffix in zip(MILK_COMPARISON_PRODUCTS, SUFFIXES)
    }


def collect(source, url, html):
    client = MagicMock()
    client.get_html.return_value = html
    return (CartpkAdapter() if source == "cartpk" else JalalSonsAdapter()).collect(client, url)


class ReviewedMilkParserTests(SimpleTestCase):
    def test_all_five_observed_pairs_have_the_same_strict_identity(self):
        for product, prices in zip(MILK_COMPARISON_PRODUCTS, PRICES):
            items = []
            for source, price in zip(("jalal-sons", "cartpk"), prices):
                url = ("https://www.cartpk.com" + product["cartpk_path"] if source == "cartpk"
                       else "https://www.jalalsons.com.pk" + product["jalal_path"])
                with self.subTest(title=product["title"], source=source):
                    item = collect(source, url, pages(source)[url])
                    self.assertEqual(item.price, Decimal(price))
                    self.assertEqual(item.availability, "in_stock")
                    self.assertEqual(item.currency, "PKR")
                    self.assertEqual(item.image, "")
                    self.assertIn("unverified", item.delivery_area)
                    items.append(item)
            self.assertEqual(match_score(identify(items[0].title, items[0].brand), identify(items[1].title)), 100)

    def test_sale_price_is_collected_without_using_the_regular_price(self):
        url = "https://www.cartpk.com/nestle-milk-pack-250-ml"
        html = pages("cartpk")[url]
        self.assertIn('data-price-type="oldPrice"', html)
        self.assertEqual(collect("cartpk", url, html).price, 105)
        # Regular price may change independently; final price must still agree with metadata.
        html = html.replace('data-price-amount="120"', 'data-price-amount="999"').replace('Rs 120.00', 'Rs 999.00')
        self.assertEqual(collect("cartpk", url, html).price, 105)
        with self.assertRaises(CollectionError):
            collect("cartpk", url, html.replace('content="105.00"', 'content="120.00"'))

    def test_each_reviewed_url_rejects_another_products_title(self):
        for source in ("jalal-sons", "cartpk"):
            for url, html in pages(source).items():
                with self.subTest(source=source, url=url), self.assertRaises(CollectionError):
                    # Both JSON-LD name and heading change together on Jalal Sons.
                    title = BeautifulSoup(html, "html.parser").h1.get_text()
                    collect(source, url, html.replace(title, "Nestle Chocolate Milk 250ml"))

    def test_new_cartpk_urls_reject_packaging_packs_variants_and_wrong_sizes(self):
        for url, html in list(pages("cartpk").items())[1:]:
            title = BeautifulSoup(html, "html.parser").h1.get_text()
            for changed in (title + " pack of 12", title + " Pouch", title + " Low Fat",
                            title + " Chocolate", title.replace("1.5", "2").replace("250", "200").replace("1L", "2L")):
                with self.subTest(url=url, changed=changed), self.assertRaises(CollectionError):
                    collect("cartpk", url, html.replace(title, changed))

    def test_unreviewed_nearby_products_are_rejected_before_network(self):
        client = MagicMock()
        for path in ("/olpers-milk-250ml", "/olpers-milk-1-5-ltr-extra", "/nestle-milk-pack-1-liter",
                     "/nestle-milk-pack-250-ml/", "/nurpur-milk-1-12-1l-corton"):
            with self.subTest(path=path), self.assertRaises(CollectionError):
                CartpkAdapter().collect(client, "https://www.cartpk.com" + path)
        client.get_html.assert_not_called()

    def test_aliases_preserve_distinct_milk_lines_and_packaging(self):
        self.assertEqual(match_score(identify("Nestle Milk Pak 250ml"), identify("Nestle Milkpak 250ml")), 100)
        self.assertEqual(match_score(identify("NURPUR Milk Full Cream1Ltr"), identify("Nurpur Milk 1L")), 100)
        for left, right in (("Nurpur Milk 1L", "Haleeb Milk 1L"),
                            ("Haleeb Milk 1L", "Haleeb Asli Milk 1L"),
                            ("Nestle Milkpak 250ml", "Nestle Milk Pak Cream 250ml"),
                            ("Nestle Milkpak 250ml", "Nestle Milk Pak Active Milk 250ml"),
                            ("Nurpur Milk 1L", "Nurpur Milk 1L carton")):
            with self.subTest(left=left, right=right):
                self.assertLess(match_score(identify(left), identify(right)), 92)


@override_settings(SCRAPING_ENABLED=True)
class ReviewedMilkBatchTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        Retailer.objects.filter(slug__in=("cartpk", "jalal-sons")).update(status="enabled", collection_enabled=True)

    def run_batch(self, source):
        with patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.side_effect = pages(source).__getitem__
            client_class.return_value.request_count = 6
            call_command("scrape", source, batch=f"{source}-milk-comparison", stdout=StringIO())

    def assert_catalog(self):
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 5)
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 10)
        self.assertEqual(Product.objects.filter(is_demo=True).count(), 12)
        for product in Product.objects.filter(is_demo=False):
            self.assertEqual(product.listings.count(), 2)
            self.assertEqual(product.listings.values("retailer").distinct().count(), 2)
            self.assertEqual(product.category.slug, "dairy")
            detail = self.client.get(f"/products/{product.slug}/")
            self.assertContains(detail, "Visit retailer", count=2)
            self.assertContains(detail, "Delivery areas may differ or be unverified")
            data = self.client.get(f"/api/products/{product.slug}/").json()
            self.assertEqual(len(data["listings"]), 2)
            self.assertEqual([Decimal(item["current_price"]) for item in data["listings"]],
                             sorted(product.listings.values_list("current_price", flat=True)))
            self.assertFalse(data["has_comparison"])
            self.assertFalse(any(item["is_best"] or item["is_demo"] for item in data["listings"]))

    def test_batches_import_five_pairs_and_rechecks_append_history_without_duplicates(self):
        for source in ("jalal-sons", "cartpk"):
            self.run_batch(source)
        self.assert_catalog()
        original_ids = set(RetailerListing.objects.filter(is_demo=False).values_list("pk", flat=True))
        for source in ("jalal-sons", "cartpk"):
            self.run_batch(source)
        self.assertEqual(set(RetailerListing.objects.filter(is_demo=False).values_list("pk", flat=True)), original_ids)
        self.assertTrue(all(listing.history.count() == 2 for listing in RetailerListing.objects.filter(is_demo=False)))
        self.assertEqual(ScrapeRun.objects.filter(status="success", products_collected=5).count(), 4)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 20)

    def test_import_order_does_not_change_matching(self):
        self.run_batch("cartpk")
        self.run_batch("jalal-sons")
        self.assert_catalog()

    @override_settings(SCRAPING_ENABLED=False)
    def test_both_expanded_batches_are_network_free_dry_runs(self):
        for source in ("jalal-sons", "cartpk"):
            output = StringIO()
            with patch("requests.Session.get") as get:
                call_command("scrape", source, batch=f"{source}-milk-comparison", dry_run=True, stdout=output)
            get.assert_not_called()
            self.assertIn("Dry run: 5 URL(s)", output.getvalue())
            self.assertEqual(len(BATCHES[f"{source}-milk-comparison"]["urls"]), 5)
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertFalse(RetailerListing.objects.filter(is_demo=False).exists())
