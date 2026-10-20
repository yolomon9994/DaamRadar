from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.matching.normalization import identify
from catalog.models import Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.types import CollectionError
from catalog.services.catalog import decorate, get_product_queryset
from catalog.services.ingestion import ingest

FIXTURES = Path(__file__).parent / "fixtures"
HTML = (FIXTURES / "cartpk_milk.html").read_text(encoding="utf-8")
URL = "https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr"
JALAL_URL = "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398"


def collected_item(adapter=None, html=HTML, url=URL):
    client = MagicMock()
    client.get_html.return_value = html
    return (adapter or CartpkAdapter()).collect(client, url)


class CartpkParserTests(SimpleTestCase):
    def test_observed_markup_works_without_repairing_broken_json_ld(self):
        item = collected_item()
        self.assertEqual(item.title, "OLPERS - Milk Full Cream 1 Litre")
        self.assertEqual(item.price, Decimal("360"))
        self.assertEqual(item.currency, "PKR")
        self.assertEqual(item.availability, "in_stock")
        self.assertEqual(item.image, "")
        self.assertEqual(item.external_id, "olper-s-milk-full-cream-milk-1ltr")
        self.assertIn("unverified", item.delivery_area)
        self.assertEqual(identify(item.title).quantity, 1000)

    def test_recommendation_prices_are_never_used(self):
        html = HTML.replace('data-price-amount="190"', 'data-price-amount="1"').replace('data-price-amount="720"', 'data-price-amount="9999"')
        self.assertEqual(collected_item(html=html).price, 360)
        # An unrelated product price is insufficient if the actual product's price disappears.
        html = HTML.replace('class="price-wrapper" data-price-amount="360" data-price-type="finalPrice"', 'class="price-wrapper"')
        with self.assertRaises(CollectionError):
            collected_item(html=html)

    def test_visible_price_currency_and_metadata_must_all_agree(self):
        cases = [
            HTML.replace('content="PKR"', 'content="USD"'),
            HTML.replace('content="360.00"', 'content="361.00"'),
            HTML.replace('data-price-amount="360"', 'data-price-amount="359"'),
            HTML.replace('Rs 360.00', 'Rs 361.00'),
            HTML.replace('property="product:price:currency"', 'property="unrelated"'),
            HTML.replace('property="product:price:amount"', 'property="unrelated"'),
            HTML.replace('data-price-amount="360"', 'data-price-amount="NaN"'),
            HTML.replace('content="360"', 'content="0"'),
        ]
        for html in cases:
            with self.subTest(html=html[:80]), self.assertRaises(CollectionError) as caught:
                collected_item(html=html)
            self.assertEqual(caught.exception.code, "parse_error")

    def test_missing_or_duplicate_product_fields_are_rejected(self):
        for html in [HTML.replace('class="product-info-main"', 'class="changed-layout"'),
                     HTML + '<h1>Another product</h1>',
                     HTML.replace('<h1 class="page-title">OLPERS - Milk Full Cream 1 Litre</h1>', '<h1></h1>'),
                     HTML.replace('<div class="product-info-main">', '<div class="product-info-main"><span data-price-type="finalPrice" data-price-amount="360">Rs 360.00</span>')]:
            with self.subTest(html=html[:80]), self.assertRaises(CollectionError):
                collected_item(html=html)

    def test_selectable_or_incompatible_products_are_not_imported(self):
        for html in [HTML.replace('</h1>', '</h1><select name="super_attribute[1]"></select>'),
                     HTML.replace('1 Litre', '250ml'), HTML.replace('1 Litre', '1.5 Litre'),
                     HTML.replace('1 Litre', '1 Litre pack of 12'),
                     HTML.replace('Milk Full Cream', 'Milk Low Fat'),
                     HTML.replace('Milk Full Cream', 'Chocolate Milk'),
                     HTML.replace('Milk Full Cream', 'Milk Full Cream Pouch')]:
            with self.subTest(html=html[:80]), self.assertRaises(CollectionError):
                collected_item(html=html)

    def test_canonical_and_exact_reviewed_url_are_enforced(self):
        with self.assertRaises(CollectionError):
            collected_item(html=HTML.replace('rel="canonical" href="' + URL, 'rel="canonical" href="https://www.cartpk.com/different-product'))
        client = MagicMock()
        for url in [URL + '?p=1', URL + '#variant', URL.replace('https:', 'http:'),
                    URL.replace('www.cartpk.com', 'evil.test'), 'https://www.cartpk.com/catalog/product/view/123',
                    'https://www.cartpk.com/another-milk-product']:
            with self.subTest(url=url), self.assertRaises(CollectionError):
                CartpkAdapter().collect(client, url)
        client.get_html.assert_not_called()

    def test_stock_is_not_assumed_and_conflicting_labels_fail(self):
        html = HTML.replace('<div class="stock available"><span>In stock</span></div>', '')
        self.assertEqual(collected_item(html=html).availability, "unknown")
        html = HTML.replace('stock available', 'stock unavailable').replace('In stock', 'Out of stock')
        self.assertEqual(collected_item(html=html).availability, "out_of_stock")
        for html in [HTML.replace('In stock', 'Out of stock'),
                     HTML.replace('</h1>', '</h1><div class="stock unavailable">Out of stock</div>')]:
            with self.assertRaises(CollectionError):
                collected_item(html=html)


class CartpkComparisonTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        jalal_html = (FIXTURES / "jalal_milk.html").read_text(encoding="utf-8")
        item = collected_item(JalalSonsAdapter(), jalal_html, JALAL_URL)
        self.jalal, _ = ingest(Retailer.objects.get(slug="jalal-sons"), item)

    def test_two_retailers_match_one_canonical_product_and_keep_area_warning(self):
        cartpk, _ = ingest(Retailer.objects.get(slug="cartpk"), collected_item())
        self.assertEqual(cartpk.product_id, self.jalal.product_id)
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 1)
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 2)
        product = decorate(get_product_queryset().get(pk=cartpk.product_id))
        self.assertEqual([offer.current_price for offer in product.offers], [350, 360])
        self.assertTrue(product.has_mixed_areas)
        self.assertFalse(product.has_comparison)
        self.assertFalse(product.best_ids)
        self.assertEqual(product.savings, 0)
        response = self.client.get(f'/products/{product.slug}/')
        self.assertContains(response, "Visit retailer", count=2)
        self.assertContains(response, "Cartpk")
        self.assertContains(response, "Jalal Sons")
        self.assertContains(response, "Delivery areas may differ or be unverified")
        data = self.client.get(f'/api/products/{product.slug}/').json()
        self.assertEqual([item['current_price'] for item in data['listings']], ['350.00', '360.00'])
        self.assertFalse(any(item['is_best'] for item in data['listings']))
        self.assertTrue(all(not item['is_demo'] for item in data['listings']))

    @override_settings(SCRAPING_ENABLED=True)
    def test_manual_batch_upserts_one_listing_and_appends_history(self):
        retailer = Retailer.objects.get(slug="cartpk")
        self.assertFalse(retailer.collection_enabled)
        self.assertEqual(retailer.status, "pending")
        with self.assertRaises(CommandError), patch('requests.Session.get') as get:
            call_command('scrape', 'cartpk', batch='cartpk-milk-1l', stdout=StringIO())
        get.assert_not_called()
        retailer.collection_enabled, retailer.status = True, 'enabled'
        retailer.save()
        with patch('catalog.management.commands.scrape.PoliteClient') as client_class:
            client_class.return_value.get_html.return_value = HTML
            for _ in range(2):
                call_command('scrape', 'cartpk', batch='cartpk-milk-1l', stdout=StringIO())
        listing = retailer.listings.get(is_demo=False)
        self.assertEqual(listing.product_id, self.jalal.product_id)
        self.assertEqual(listing.history.count(), 2)
        self.assertEqual(ScrapeRun.objects.filter(retailer=retailer, status='success').count(), 2)

    def test_ambiguous_price_preserves_previous_observation(self):
        retailer = Retailer.objects.get(slug="cartpk")
        listing, _ = ingest(retailer, collected_item())
        before = (listing.last_checked, listing.current_price, listing.history.count())
        with self.assertRaises(CollectionError):
            ingest(retailer, collected_item(html=HTML.replace('content="360.00"', 'content="999"')))
        listing.refresh_from_db()
        self.assertEqual((listing.last_checked, listing.current_price, listing.history.count()), before)
