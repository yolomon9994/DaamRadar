import copy
import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import PriceHistory, Product, RetailerListing
from catalog.services.list_transfer import product_descriptor


class ListTransferTests(TestCase):
    url = "/api/shopping-list/preview/"

    @classmethod
    def setUpTestData(cls):
        cls.milk = Product.objects.create(slug="local-generated-milk-id", canonical_name="Olpers Milk 1L",
            brand="olpers", quantity=Decimal("1000"), unit="ml")
        cls.demo = Product.objects.create(slug="demo-milk", canonical_name="Olpers Milk 1L",
            brand="olpers", quantity=Decimal("1000"), unit="ml", is_demo=True)

    def setUp(self):
        cache.clear()

    def document(self, product=None, slug="another-installation-milk-id"):
        return {"format": "daamradar-shopping-list", "version": 1, "source": "live",
                "exported_at": timezone.now().isoformat(), "items": [
                    {"slug": slug, "quantity": 3, "product": product_descriptor(product or self.milk)}]}

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_round_trip_same_installation_and_portable_alias(self):
        for slug, name in [(self.milk.slug, self.milk.canonical_name), ("remote-random-id", "Olper's UHT Milk 1000ml")]:
            with self.subTest(slug=slug):
                data = self.document(slug=slug)
                data["items"][0]["product"]["name"] = name
                response = self.post(data)
                self.assertEqual(response.status_code, 200)
                item = response.json()["items"][0]
                self.assertEqual((item["status"], item["slug"], item["quantity"]), ("matched", self.milk.slug, 3))
                self.assertEqual(item["product"], product_descriptor(self.milk))

    def test_identity_guards_prevent_size_brand_variant_packaging_and_gtin_substitution(self):
        mutations = [{"quantity": "500.000", "name": "Olpers Milk 500ml"}, {"brand": "nestle"},
                     {"variant": "chocolate"}, {"packaging": "bottle"}, {"gtin": "1234567890123"},
                     {"pack_count": 6, "name": "Olpers Milk 6 x 1L"}, {"unit": "g"},
                     {"name": "Olpers Milk 500ml"}]
        for changes in mutations:
            with self.subTest(changes=changes):
                data = self.document(slug=self.milk.slug)
                data["items"][0]["product"].update(changes)
                response = self.post(data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["items"][0]["status"], "unavailable")
                self.assertIsNone(response.json()["items"][0]["slug"])

    def test_ambiguous_identity_stays_unpriced_but_exact_local_descriptor_is_safe(self):
        Product.objects.create(slug="duplicate", canonical_name=self.milk.canonical_name,
            brand="olpers", quantity=Decimal("1000"), unit="ml")
        item = self.post(self.document()).json()["items"][0]
        self.assertEqual(item["status"], "ambiguous")
        self.assertIsNone(item["slug"])
        item = self.post(self.document(slug=self.milk.slug)).json()["items"][0]
        self.assertEqual(item["slug"], self.milk.slug)

    def test_demo_and_collected_resolve_only_within_selected_source(self):
        data = self.document(slug=self.demo.slug)
        self.assertEqual(self.post(data).json()["items"][0]["slug"], self.milk.slug)
        data["source"] = "demo"
        self.assertEqual(self.post(data).json()["items"][0]["slug"], self.demo.slug)
        Product.objects.filter(is_demo=True).delete()
        self.assertIsNone(self.post(data).json()["items"][0]["slug"])

    def test_missing_product_is_retained_with_name_quantity_and_recomputed_size(self):
        data = self.document()
        data["items"][0]["product"].update(name="Missing Milk 500ml", quantity="500.000", size="999 kg")
        item = self.post(data).json()["items"][0]
        self.assertEqual((item["quantity"], item["imported_name"], item["product"]["size"]), (3, "Missing Milk 500ml", "500 ml"))
        self.assertIsNone(item["slug"])

    def test_old_list_without_metadata_never_blindly_matches_slug(self):
        data = self.document(slug=self.milk.slug)
        data["items"][0]["product"] = None
        item = self.post(data).json()["items"][0]
        self.assertEqual(item["status"], "unavailable")
        self.assertIsNone(item["slug"])
        self.assertIsNone(item["product"])

    def test_unknown_size_only_restores_with_exact_local_descriptor(self):
        unknown = Product.objects.create(slug="unknown-size", canonical_name="Unspecified groceries")
        for slug, status in [(unknown.slug, "matched"), ("different-id", "unavailable")]:
            with self.subTest(slug=slug):
                self.assertEqual(self.post(self.document(unknown, slug)).json()["items"][0]["status"], status)

    def test_duplicate_raw_references_and_duplicate_resolved_products_rejected(self):
        for slug in ["another-installation-milk-id", "a-second-alias"]:
            with self.subTest(slug=slug):
                data = self.document()
                data["items"].append({**copy.deepcopy(data["items"][0]), "slug": slug})
                self.assertEqual(self.post(data).status_code, 400)

    def test_bounded_candidate_search_fails_closed_without_truncating_list(self):
        with patch("catalog.services.list_transfer.CANDIDATE_LIMIT", 0):
            item = self.post(self.document()).json()["items"][0]
        self.assertIsNone(item["slug"])
        self.assertIn("Too many", item["reason"])
        self.assertEqual(item["quantity"], 3)

    def test_unexpected_price_fields_at_all_levels_are_rejected(self):
        for level in ["document", "item", "product"]:
            with self.subTest(level=level):
                data = self.document()
                target = data if level == "document" else data["items"][0]
                if level == "product":
                    target = target["product"]
                target["price"] = "0.01"
                self.assertEqual(self.post(data).status_code, 400)

    def test_format_source_version_and_pack_quantities_are_validated(self):
        for key, value in [("format", "other"), ("source", "all"), ("version", 2), ("version", True),
                           ("exported_at", "yesterday")]:
            with self.subTest(key=key, value=value):
                data = self.document()
                data[key] = value
                self.assertEqual(self.post(data).status_code, 400)
        for quantity in [0, 100, -1, 1.5, True, None]:
            with self.subTest(quantity=quantity):
                data = self.document()
                data["items"][0]["quantity"] = quantity
                self.assertEqual(self.post(data).status_code, 400)

    def test_normalized_product_fields_are_validated(self):
        for changes in [{"quantity": "0"}, {"quantity": "NaN"}, {"quantity": "1.0001"},
                        {"quantity": None}, {"unit": "L"}, {"pack_count": True}, {"pack_count": 0},
                        {"name": ""}, {"brand": "a" * 101}]:
            with self.subTest(changes=changes):
                data = self.document()
                data["items"][0]["product"].update(changes)
                self.assertEqual(self.post(data).status_code, 400)

    def test_item_count_file_size_and_json_boundaries(self):
        data = self.document()
        for count, status in [(0, 400), (50, 200), (51, 400)]:
            with self.subTest(count=count):
                data["items"] = [{"slug": f"unknown-{index}", "quantity": 99, "product": None} for index in range(count)]
                self.assertEqual(self.post(data).status_code, status)
        self.assertEqual(self.client.post(self.url, "{" + " " * (256 * 1024), content_type="application/json").status_code, 413)
        self.assertEqual(self.client.post(self.url, "{broken", content_type="application/json").status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)

    def test_preview_has_no_database_mutation_or_external_request(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with CaptureQueriesContext(connection) as queries, patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer requests")):
            response = self.post(self.document())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertNotIn('"price":', json.dumps(response.json()))
        self.assertNotIn('"current_price":', json.dumps(response.json()))

    def test_basket_descriptor_contains_no_prices_and_unresolved_cannot_be_priced(self):
        response = self.client.get("/api/basket/", {"source": "live", "item": self.milk.slug + ":2"})
        self.assertEqual(response.json()["items"][0]["product"], product_descriptor(self.milk))
        self.assertEqual(set(product_descriptor(self.milk)), {"name", "brand", "quantity", "unit", "pack_count", "variant", "packaging", "gtin", "size"})
        response = self.client.get("/api/basket/", {"source": "live", "item": self.milk.slug + ":2", "unresolved": self.milk.slug})
        self.assertFalse(response.json()["items"][0]["available"])
        self.assertIsNone(response.json()["items"][0]["product"])
        self.assertEqual(self.client.get("/api/basket/", {"unresolved": "not-selected"}).status_code, 400)
