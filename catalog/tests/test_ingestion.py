from dataclasses import replace
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from catalog.models import PriceHistory, Product, Retailer
from catalog.scraping.types import ScrapedProduct
from catalog.services.ingestion import ingest


class IngestionTests(TestCase):
    def setUp(self):
        call_command("seed_retailers", stdout=StringIO())
        self.retailer = Retailer.objects.get(slug="alfatah")
        self.item = ScrapedProduct("milk-1", "Olpers Milk 1L", "https://alfatah.pk/products/milk", Decimal("320"), availability="in_stock")

    def test_insert_update_and_snapshot_even_if_price_unchanged(self):
        listing, created = ingest(self.retailer, self.item)
        self.assertTrue(created)
        updated, created = ingest(self.retailer, replace(self.item, price=Decimal("330")))
        self.assertFalse(created)
        self.assertEqual(listing.pk, updated.pk)
        self.assertEqual(updated.current_price, Decimal("330"))
        self.assertEqual(Product.objects.count(), 1)
        ingest(self.retailer, replace(self.item, price=Decimal("330")))
        self.assertEqual(PriceHistory.objects.count(), 3)

    def test_matches_equivalent_listing_from_another_retailer(self):
        first, _ = ingest(self.retailer, self.item)
        retailer = Retailer.objects.get(slug="springs")
        second, _ = ingest(retailer, replace(self.item, external_id="other-id", title="Olper's UHT Milk 1000ml", url="https://springs.com.pk/products/milk"))
        self.assertEqual(first.product_id, second.product_id)

    def test_changed_variant_gets_separate_product(self):
        first, _ = ingest(self.retailer, self.item)
        second, _ = ingest(self.retailer, replace(self.item, title="Olpers Chocolate Milk 1L"))
        self.assertNotEqual(first.product_id, second.product_id)

    def test_unknown_identity_update_is_stable(self):
        unknown = replace(self.item, title="An unrecognized product")
        first, _ = ingest(self.retailer, unknown)
        second, _ = ingest(self.retailer, unknown)
        self.assertEqual(first.product_id, second.product_id)
        self.assertEqual(Product.objects.count(), 1)

    def test_rejects_invalid_inputs_atomically(self):
        for change in [{"price": Decimal("-1")}, {"price": Decimal("NaN")}, {"price": Decimal("1.001")},
                       {"currency": "USD"}, {"url": "https://evil.test/products/milk"},
                       {"url": "http://alfatah.pk/products/milk"}, {"title": ""}, {"availability": "maybe"}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ingest(self.retailer, replace(self.item, **change))
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    def test_demo_records_are_not_matched_into_live(self):
        demo, _ = ingest(self.retailer, self.item, is_demo=True)
        live, _ = ingest(self.retailer, self.item)
        self.assertNotEqual(demo.product_id, live.product_id)
