from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.watchlist import check_targets


class WatchlistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.product = Product.objects.create(slug="real-milk", canonical_name="Milk 6 x 250ml",
            quantity=Decimal("250"), unit="ml", pack_count=6)
        cls.checked = timezone.now() - timedelta(minutes=1)
        cls.offer = RetailerListing.objects.create(product=cls.product, retailer=Retailer.objects.get(slug="naheed"),
            external_id="watched-milk", original_title="Milk 6 x 250ml", current_price=Decimal("510"),
            availability="in_stock", last_checked=cls.checked)

    def setUp(self):
        cache.clear()

    def result(self, target="510"):
        return check_targets([("real-milk", Decimal(target))], "live")["items"][0]

    def test_exact_decimal_target_equality_above_and_below(self):
        for target, status in [("509.99", "above_target"), ("510.00", "target_met"), ("510.01", "target_met")]:
            with self.subTest(target=target):
                item = self.result(target)
                self.assertEqual(item["status"], status)
                self.assertEqual(item["observed_price"], "510.00")
                self.assertEqual(item["offers"][0]["meets_target"], status == "target_met")

    def test_target_is_per_exact_canonical_pack_not_standard_unit(self):
        item = self.result("340")
        self.assertEqual(item["status"], "above_target")
        self.assertEqual(item["size"], "6 × 250 ml")
        self.assertEqual(item["standard_unit_price"]["amount"], "340.00")

    def test_stale_out_of_stock_unknown_and_future_observations_do_not_trigger(self):
        for changes, status in [({"last_checked": timezone.now() - timedelta(hours=49)}, "stale"),
                                ({"availability": "out_of_stock"}, "out_of_stock"),
                                ({"availability": "unknown"}, "availability_unknown"),
                                ({"last_checked": timezone.now() + timedelta(days=1)}, "unavailable")]:
            with self.subTest(changes=changes):
                RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=self.checked, availability="in_stock")
                RetailerListing.objects.filter(pk=self.offer.pk).update(**changes)
                item = self.result("9999")
                self.assertEqual(item["status"], status)
                self.assertIsNone(item["observed_price"])
                self.assertIsNone(item["standard_unit_price"])
                self.assertEqual(item["offers"], [])
                self.assertIsNotNone(item["last_observed_at"])

    def test_ineligible_cheaper_offer_does_not_create_target_match(self):
        RetailerListing.objects.create(product=self.product, retailer=self.offer.retailer, external_id="cheap-stale",
            original_title="Milk", current_price=Decimal("1"), availability="in_stock", last_checked=self.checked - timedelta(days=3))
        item = self.result("500")
        self.assertEqual(item["status"], "above_target")
        self.assertEqual(len(item["offers"]), 1)
        self.assertEqual(item["observed_price"], "510.00")

    def test_individual_area_observations_keep_warnings_without_winner_claim(self):
        RetailerListing.objects.create(product=self.product, retailer=self.offer.retailer, external_id="other-area",
            original_title="Milk", current_price=Decimal("400"), availability="in_stock", last_checked=self.checked,
            delivery_area="Other area")
        item = self.result("450")
        self.assertEqual(item["status"], "target_met")
        self.assertTrue(item["has_mixed_areas"])
        self.assertTrue(item["has_unverified_areas"])
        self.assertEqual([offer["meets_target"] for offer in item["offers"]], [False, True])
        self.assertNotIn("winner", item)
        self.assertNotIn("savings", item)

    def test_valid_verified_area_does_not_receive_unverified_warning(self):
        RetailerListing.objects.filter(pk=self.offer.pk).update(delivery_area="Verified area", delivery_area_key="scope-one",
            area_evidence_url=self.offer.retailer.website.rstrip("/") + "/delivery", area_verified_at=timezone.now())
        self.assertFalse(self.result()["has_unverified_areas"])
        self.assertTrue(self.result()["offers"][0]["area_is_verified"])

    def test_demo_live_wrong_source_and_missing_products_stay_separate(self):
        demo = "demo-olpers-milk-1l"
        for source, slugs, statuses in [("demo", [demo, "real-milk", "deleted"], ["target_met", "product_unavailable", "product_unavailable"]),
                                        ("live", [demo, "real-milk"], ["product_unavailable", "above_target"])]:
            result = check_targets([(slug, Decimal("400")) for slug in slugs], source)
            self.assertEqual([item["status"] for item in result["items"]], statuses)
        RetailerListing.objects.filter(product=self.product).update(is_demo=True)
        self.assertEqual(self.result()["status"], "not_listed")

    def test_unknown_size_does_not_prevent_checking_a_known_pack_price(self):
        Product.objects.filter(pk=self.product.pk).update(quantity=None, unit="")
        item = self.result()
        self.assertEqual(item["status"], "target_met")
        self.assertIsNone(item["standard_unit_price"])

    def test_snapshot_expiry_is_earliest_eligible_freshness_boundary(self):
        now = timezone.now()
        RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=now - timedelta(hours=47))
        with patch("catalog.services.watchlist.timezone.now", return_value=now):
            data = check_targets([("real-milk", Decimal("510"))], "live")
        self.assertEqual(data["expires_at"], (now + timedelta(hours=1)).isoformat())
        self.assertEqual(data["evaluated_at"], now.isoformat())
        with patch("catalog.services.watchlist.timezone.now", return_value=now + timedelta(hours=2)):
            data = check_targets([("real-milk", Decimal("510"))], "live")
        self.assertEqual(data["items"][0]["status"], "stale")
        self.assertIsNone(data["expires_at"])

    def test_api_bounds_duplicates_target_format_and_source_validation(self):
        invalid = ["0", "-1", "0.001", "NaN", "Infinity", "1e3", "true", "10000000000", "1.234", "01", "1\n", "", ".50"]
        for price in invalid:
            with self.subTest(price=price):
                self.assertEqual(self.client.get("/api/watchlist/", {"item": "real-milk:" + price}).status_code, 400)
        for params in [{"source": "all"}, {"item": ["real-milk:1", "real-milk:2"]},
                       {"item": [f"p-{index}:1" for index in range(51)]}, {"item": "bad/slug:1"}]:
            self.assertEqual(self.client.get("/api/watchlist/", params).status_code, 400)
        response = self.client.get("/api/watchlist/", {"source": "live", "item": "real-milk:9999999999.99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["target"], "9999999999.99")
        self.assertEqual(len(self.client.get("/api/watchlist/", {"item": [f"p-{index}:0.01" for index in range(50)]}).json()["items"]), 50)

    def test_api_empty_and_unsupported_write(self):
        data = self.client.get("/api/watchlist/").json()
        self.assertEqual(data["items"], [])
        self.assertIsNone(data["expires_at"])
        self.assertEqual(self.client.post("/api/watchlist/", {}).status_code, 405)

    def test_checks_are_read_only_and_make_no_retailer_requests(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with CaptureQueriesContext(connection) as queries, patch("requests.sessions.Session.send", side_effect=AssertionError("No external requests")):
            response = self.client.get("/api/watchlist/", {"source": "live", "item": "real-milk:510"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))

    def test_page_and_product_controls_work_without_an_account(self):
        response = self.client.get("/watchlist/?source=live")
        self.assertContains(response, "Your price watchlist")
        self.assertContains(response, 'data-source="live"')
        self.assertContains(response, "Enable JavaScript")
        self.assertContains(self.client.get("/products/real-milk/"), "Target pack price (PKR)")
        self.assertContains(self.client.get("/?source=demo"), 'data-watch-link')
