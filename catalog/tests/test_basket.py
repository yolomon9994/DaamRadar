from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.basket import estimate_basket


class BasketTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.milk = Product.objects.create(slug="real-milk", canonical_name="Milk 1L")
        cls.tea = Product.objects.create(slug="real-tea", canonical_name="Tea 100g")
        cls.retailer = Retailer.objects.get(slug="naheed")
        cls.other = Retailer.objects.get(slug="springs")
        cls.checked = timezone.now() - timedelta(minutes=1)
        cls.milk_offer = RetailerListing.objects.create(
            product=cls.milk, retailer=cls.retailer, external_id="milk", original_title="Milk 1L",
            current_price=Decimal("0.10"), availability="in_stock", last_checked=cls.checked)
        cls.tea_offer = RetailerListing.objects.create(
            product=cls.tea, retailer=cls.retailer, external_id="tea", original_title="Tea 100g",
            current_price=Decimal("2.25"), availability="in_stock", last_checked=cls.checked)
        RetailerListing.objects.create(product=cls.milk, retailer=cls.other, external_id="milk",
            original_title="Milk 1L", current_price=Decimal("0.05"), availability="in_stock", last_checked=cls.checked)

    def estimate(self, items=None):
        return estimate_basket(items or [("real-milk", 3), ("real-tea", 2)], "live")

    def row(self, result, slug="naheed"):
        return next(row for row in result["retailers"] if row["slug"] == slug)

    def test_decimal_quantity_totals_and_unverified_estimate(self):
        result = self.estimate()
        row = self.row(result)
        self.assertEqual(row["total"], "4.80")
        self.assertEqual(row["lines"][0]["line_total"], "0.30")
        self.assertTrue(row["is_complete"])
        self.assertTrue(row["has_unverified_areas"])
        self.assertEqual(row["lines"][0]["last_checked"], self.checked.isoformat())
        self.assertEqual(row["lines"][0]["last_observed_at"], self.checked.isoformat())
        self.assertEqual(result["items"][0]["size"], "Size unspecified")

    def test_partial_coverage_has_subtotal_but_no_full_total(self):
        result = self.estimate()
        row = self.row(result, "springs")
        self.assertEqual(row["subtotal"], "0.15")
        self.assertIsNone(row["total"])
        self.assertFalse(row["is_complete"])
        self.assertEqual(row["covered_count"], 1)
        self.assertEqual(row["lines"][1]["status"], "missing")
        self.assertEqual([row["name"] for row in result["retailers"]], ["Naheed", "Springs"])
        self.assertNotIn("winner", result)

    def test_stale_out_of_stock_and_unknown_prices_excluded(self):
        for fields, status in [
            ({"last_checked": timezone.now() - timedelta(hours=49)}, "stale"),
            ({"availability": "out_of_stock"}, "out_of_stock"),
            ({"availability": "unknown"}, "availability_unknown"),
        ]:
            with self.subTest(status=status):
                RetailerListing.objects.filter(pk=self.milk_offer.pk).update(
                    last_checked=self.checked, availability="in_stock")
                RetailerListing.objects.filter(pk=self.milk_offer.pk).update(**fields)
                row = self.row(self.estimate())
                self.assertEqual(row["lines"][0]["status"], status)
                expected = fields.get("last_checked", self.checked).isoformat()
                self.assertEqual(row["lines"][0]["last_observed_at"], expected)
                self.assertIsNone(row["lines"][0]["last_checked"])
                self.assertEqual(row["subtotal"], "4.50")
                self.assertIsNone(row["total"])

    def test_no_eligible_items_has_no_zero_price_total(self):
        RetailerListing.objects.filter(is_demo=False).update(availability="out_of_stock")
        row = self.row(self.estimate())
        self.assertIsNone(row["subtotal"])
        self.assertIsNone(row["total"])
        self.assertEqual(row["covered_count"], 0)

    def test_demo_live_and_missing_products_remain_separate(self):
        data = estimate_basket([("demo-olpers-milk-1l", 1), ("real-milk", 1), ("deleted-product", 1)], "demo")
        self.assertEqual([item["available"] for item in data["items"]], [True, False, False])
        self.assertEqual(data["items"][0]["size"], "1 L")
        self.assertEqual(data["items"][2]["size"], "Size unavailable")
        for row in data["retailers"]:
            self.assertIsNone(row["total"])
            self.assertEqual(row["covered_count"], 1)
            self.assertEqual(row["lines"][1]["status"], "product_unavailable")
            self.assertFalse(row["has_unverified_areas"])
        data = estimate_basket([("demo-olpers-milk-1l", 1)], "live")
        self.assertFalse(data["items"][0]["available"])
        self.assertTrue(all(row["covered_count"] == 0 for row in data["retailers"]))

    def test_empty_list_has_no_totals(self):
        self.assertEqual(estimate_basket([], "demo")["retailers"], [])

    def test_unverified_location_alternatives_are_not_cheapest_location(self):
        RetailerListing.objects.create(product=self.milk, retailer=self.retailer, external_id="other-area",
            original_title="Milk", current_price=Decimal("0.01"), availability="in_stock",
            last_checked=self.checked, delivery_area="Other area")
        row = self.row(self.estimate())
        self.assertEqual(row["lines"][0]["status"], "area_ambiguous")
        self.assertIsNone(row["total"])
        self.assertEqual(row["subtotal"], "4.50")

    def verify(self, offer, key="lahore-scope"):
        RetailerListing.objects.filter(pk=offer.pk).update(delivery_area="Verified area", delivery_area_key=key,
            area_evidence_url=self.retailer.website.rstrip("/") + "/delivery", area_verified_at=timezone.now())

    def test_shared_verified_scope_has_complete_estimate(self):
        self.verify(self.milk_offer)
        self.verify(self.tea_offer)
        row = self.row(self.estimate())
        self.assertTrue(row["is_complete"])
        self.assertFalse(row["has_unverified_areas"])
        self.assertFalse(row["has_mixed_areas"])

    def test_mixed_verified_or_unverified_scopes_withhold_full_estimate(self):
        self.verify(self.milk_offer)
        self.verify(self.tea_offer, key="different-scope")
        row = self.row(self.estimate())
        self.assertTrue(row["has_mixed_areas"])
        self.assertFalse(row["is_complete"])
        self.assertIsNone(row["total"])
        self.assertEqual(row["subtotal"], "4.80")
        RetailerListing.objects.filter(pk__in=[self.milk_offer.pk, self.tea_offer.pk]).update(
            delivery_area_key="", area_evidence_url="", area_verified_at=None)
        RetailerListing.objects.filter(pk=self.tea_offer.pk).update(delivery_area="Different label")
        self.assertTrue(self.row(self.estimate())["has_mixed_areas"])

    def test_same_verified_scope_alternatives_choose_lowest_eligible_price(self):
        self.verify(self.milk_offer)
        second = RetailerListing.objects.create(product=self.milk, retailer=self.retailer, external_id="same-scope",
            original_title="Milk", current_price=Decimal("0.08"), availability="in_stock", last_checked=self.checked)
        self.verify(second)
        row = self.row(self.estimate([("real-milk", 3)]))
        self.assertEqual(row["total"], "0.24")

    def test_read_only_api_uses_local_data_without_network(self):
        counts = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No network")):
            response = self.client.get("/api/basket/", {"source": "live", "item": ["real-milk:3", "real-tea:2"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.row(response.json())["total"], "4.80")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(counts, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
        self.assertEqual(self.client.post("/api/basket/", {}).status_code, 405)

    def test_api_rejects_invalid_quantities_slugs_duplicates_sources_and_limits(self):
        cases = [{"item": ["real-milk:" + q]} for q in ["0", "-1", "100", "1.5", "NaN", "01", "1\n"]]
        cases += [{"item": ["bad/slug:1"]}, {"source": "other"},
                  {"item": ["real-milk:1", "real-milk:2"]},
                  {"item": [f"product-{i}:1" for i in range(51)]}]
        for params in cases:
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/basket/", params).status_code, 400)
        self.assertEqual(self.client.get("/api/basket/", {"item": ["real-milk:99"], "source": "live"}).status_code, 200)

    def test_shopping_page_and_add_controls_are_accessible_without_an_account(self):
        response = self.client.get("/shopping-list/?source=live")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Observed item-price estimates")
        self.assertContains(response, "Enable JavaScript")
        self.assertContains(response, 'data-source="live"')
        self.assertContains(self.client.get("/?source=demo"), 'data-list-add="demo-olpers-milk-1l"')
        self.assertContains(self.client.get("/products/real-milk/"), 'data-list-source="live"')
