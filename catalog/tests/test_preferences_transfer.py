import copy
import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.list_transfer import product_descriptor


class PreferencesTransferTests(TestCase):
    url = "/api/preferences/preview/"

    @classmethod
    def setUpTestData(cls):
        cls.milk = Product.objects.create(slug="local-milk", canonical_name="Olpers Milk 1L", brand="olpers",
                                         quantity=Decimal("1000"), unit="ml")
        cls.demo = Product.objects.create(slug="demo-milk", canonical_name="Olpers Milk 1L", brand="olpers",
                                         quantity=Decimal("1000"), unit="ml", is_demo=True)
        retailer = Retailer.objects.create(name="QA", slug="qa", website="https://example.com")
        RetailerListing.objects.create(product=cls.milk, retailer=retailer, external_id="milk", original_title="Olpers Milk 1L",
                                       current_price="300.00", availability="in_stock", last_checked=timezone.now())

    def setUp(self):
        cache.clear()

    def document(self):
        return {"format": "daamradar-planning-preferences", "version": 1, "source": "live",
                "exported_at": timezone.now().isoformat(), "budget": "5000.25", "targets": [
                    {"slug": "remote-milk", "target": "325.50", "name": self.milk.canonical_name,
                     "size": "1 L", "product": product_descriptor(self.milk)}]}

    def post(self, document):
        return self.client.post(self.url, json.dumps(document), content_type="application/json")

    def test_portable_exact_identity_retains_target_and_budget_without_observations(self):
        data = self.post(self.document()).json()
        self.assertEqual(data["source"], "live")
        self.assertEqual(data["budget"], "5000.25")
        item = data["targets"][0]
        self.assertEqual((item["slug"], item["target"], item["status"]), (self.milk.slug, "325.50", "matched"))
        self.assertEqual(item["product"], product_descriptor(self.milk))
        self.assertNotIn("quantity", item)
        self.assertNotIn('"price":', json.dumps(data))
        self.assertNotIn("observed_price", data)

    def test_same_installation_and_normalized_alias_match(self):
        for slug, name in [(self.milk.slug, self.milk.canonical_name), ("other-installation", "Olper's UHT Milk 1000ml")]:
            document = self.document()
            document["targets"][0]["slug"] = slug
            document["targets"][0]["product"]["name"] = name
            self.assertEqual(self.post(document).json()["targets"][0]["slug"], self.milk.slug)

    def test_identity_differences_never_create_a_target_for_another_pack(self):
        for changes in [{"quantity": "500", "name": "Olpers Milk 500ml"}, {"brand": "nestle"},
                        {"variant": "chocolate"}, {"packaging": "bottle"}, {"gtin": "1234567890123"},
                        {"pack_count": 6, "name": "Olpers Milk 6 x 1L"}, {"unit": "g"}]:
            with self.subTest(changes=changes):
                document = self.document()
                document["targets"][0]["slug"] = self.milk.slug
                document["targets"][0]["product"].update(changes)
                item = self.post(document).json()["targets"][0]
                self.assertIsNone(item["slug"])
                self.assertEqual((item["status"], item["target"]), ("unavailable", "325.50"))

    def test_missing_metadata_retains_display_hints_without_trusting_existing_slug(self):
        document = self.document()
        document["targets"][0].update(slug=self.milk.slug, product=None, name="Saved unknown grocery", size="Saved size")
        item = self.post(document).json()["targets"][0]
        self.assertIsNone(item["slug"])
        self.assertIsNone(item["product"])
        self.assertEqual((item["name"], item["size"]), ("Saved unknown grocery", "Saved size"))

    def test_product_size_is_recomputed_instead_of_trusting_display_hint(self):
        document = self.document()
        document["targets"][0]["product"]["size"] = "999 kg"
        self.assertEqual(self.post(document).json()["targets"][0]["size"], "1 L")

    def test_source_separation_and_ambiguous_matches(self):
        document = self.document()
        document["source"] = "demo"
        self.assertEqual(self.post(document).json()["targets"][0]["slug"], self.demo.slug)
        document["source"] = "live"
        Product.objects.create(slug="duplicate", canonical_name=self.milk.canonical_name,
                               brand=self.milk.brand, quantity=self.milk.quantity, unit=self.milk.unit)
        item = self.post(document).json()["targets"][0]
        self.assertEqual(item["status"], "ambiguous")
        self.assertIsNone(item["slug"])

    def test_bounded_resolution_retains_uncertain_targets(self):
        with patch("catalog.services.list_transfer.CANDIDATE_LIMIT", 0):
            item = self.post(self.document()).json()["targets"][0]
        self.assertIsNone(item["slug"])
        self.assertIn("Too many", item["reason"])

    def test_duplicate_raw_or_resolved_targets_are_rejected(self):
        for slug in ["remote-milk", "a-second-alias"]:
            document = self.document()
            document["targets"].append({**copy.deepcopy(document["targets"][0]), "slug": slug})
            self.assertEqual(self.post(document).status_code, 400)

    def test_decimal_strings_are_strict_and_normalized(self):
        for field in ["budget", "target"]:
            for value in [True, False, 325, 1.5, "NaN", "Infinity", "1e3", "-1", "1.234", "10000000000", " 1", "1\n", ""]:
                with self.subTest(field=field, value=value):
                    document = self.document()
                    (document if field == "budget" else document["targets"][0])[field] = value
                    self.assertEqual(self.post(document).status_code, 400)
        document = self.document()
        document["budget"] = "0000"
        document["targets"][0]["target"] = "0001.5"
        data = self.post(document).json()
        self.assertEqual((data["budget"], data["targets"][0]["target"]), ("0.00", "1.50"))
        document["targets"][0]["target"] = "0"
        self.assertEqual(self.post(document).status_code, 400)

    def test_empty_backups_nullable_budgets_and_maximum_amounts_are_explicit(self):
        document = self.document()
        document.update(targets=[], budget=None)
        self.assertEqual(self.post(document).json(), {"source": "live", "targets": [], "budget": None})
        document = self.document()
        document["budget"] = document["targets"][0]["target"] = "9999999999.99"
        self.assertEqual(self.post(document).status_code, 200)
        document["targets"][0]["target"] = None
        self.assertEqual(self.post(document).status_code, 400)

    def test_unexpected_fields_and_invalid_product_details_are_rejected(self):
        for level in ["document", "target", "product"]:
            document = self.document()
            target = document if level == "document" else document["targets"][0]
            if level == "product":
                target = target["product"]
            target["observed_price"] = "0.01"
            self.assertEqual(self.post(document).status_code, 400)
        for changes in [{"quantity": "0"}, {"quantity": None}, {"pack_count": True}, {"name": ""}]:
            document = self.document()
            document["targets"][0]["product"].update(changes)
            self.assertEqual(self.post(document).status_code, 400)

    def test_file_metadata_count_size_and_json_boundaries(self):
        for field, value in [("format", "other"), ("source", "all"), ("version", 2), ("version", True), ("exported_at", "yesterday")]:
            document = self.document()
            document[field] = value
            self.assertEqual(self.post(document).status_code, 400)
        document = self.document()
        for count, status in [(50, 200), (51, 400)]:
            document["targets"] = [{"slug": f"unknown-{i}", "target": "0.01", "name": "Unknown grocery", "size": "Unspecified", "product": None} for i in range(count)]
            self.assertEqual(self.post(document).status_code, status)
        self.assertEqual(self.client.post(self.url, " " * (256 * 1024 + 1), content_type="application/json").status_code, 413)
        self.assertEqual(self.client.post(self.url, "{bad", content_type="application/json").status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)

    def test_preview_is_read_only_anonymous_never_cached_and_makes_no_external_requests(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with CaptureQueriesContext(connection) as queries, patch("requests.sessions.Session.send", side_effect=AssertionError("No network")):
            response = self.post(self.document())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_watch_checks_supply_portable_identity_and_cannot_price_unresolved_collisions(self):
        params = {"source": "live", "item": self.milk.slug + ":325.50"}
        item = self.client.get("/api/watchlist/", params).json()["items"][0]
        self.assertEqual(item["status"], "target_met")
        self.assertEqual(item["product"], product_descriptor(self.milk))
        params["unresolved"] = self.milk.slug
        item = self.client.get("/api/watchlist/", params).json()["items"][0]
        self.assertFalse(item["available"])
        self.assertIsNone(item["product"])
        self.assertIsNone(item["observed_price"])
        self.assertEqual(item["offers"], [])
        self.assertEqual(item["status"], "product_unavailable")
        self.assertEqual(self.client.get("/api/watchlist/", {"unresolved": "not-selected"}).status_code, 400)
