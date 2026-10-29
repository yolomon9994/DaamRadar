from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.basket import estimate_basket


class BudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.product = Product.objects.create(slug="budget-product", canonical_name="Budget test pack")
        cls.offer = RetailerListing.objects.create(product=cls.product, retailer=Retailer.objects.get(slug="naheed"),
            external_id="budget-pack", original_title="Budget test pack", current_price=Decimal("0.10"),
            availability="in_stock", last_checked=timezone.now())

    def setUp(self):
        cache.clear()

    def estimate(self, budget, items=None, unresolved=()):
        return estimate_basket(items if items is not None else [(self.product.slug, 3)], "live", unresolved, budget)

    def row(self, data):
        return next(row for row in data["retailers"] if row["slug"] == "naheed")

    def test_exact_decimal_remaining_equality_and_overage(self):
        for budget, expected in [
            ("0.31", {"status": "within_budget", "remaining": "0.01", "over_by": None}),
            ("0.30", {"status": "at_budget", "remaining": "0.00", "over_by": None}),
            ("0.29", {"status": "over_budget", "remaining": None, "over_by": "0.01"}),
            ("0.00", {"status": "over_budget", "remaining": None, "over_by": "0.30"}),
        ]:
            with self.subTest(budget=budget):
                data = self.estimate(Decimal(budget))
                self.assertEqual(data["budget"], budget)
                self.assertEqual(self.row(data)["budget_assessment"], expected)
                self.assertEqual(self.row(data)["total"], "0.30")

    def test_no_budget_preserves_existing_estimate(self):
        data = self.estimate(None)
        self.assertIsNone(data["budget"])
        self.assertEqual(self.row(data)["budget_assessment"], {"status": "not_set", "remaining": None, "over_by": None})
        self.assertEqual(self.row(data)["total"], "0.30")

    def test_incomplete_basket_never_uses_its_small_subtotal_to_assess_budget(self):
        missing = Product.objects.create(slug="missing-budget-pack", canonical_name="Not listed")
        row = self.row(self.estimate(Decimal("9999"), [(self.product.slug, 3), (missing.slug, 1)]))
        self.assertEqual(row["subtotal"], "0.30")
        self.assertIsNone(row["total"])
        self.assertEqual(row["budget_assessment"], {"status": "incomplete", "remaining": None, "over_by": None})

    def test_stale_stock_and_unresolved_exclusions_prevent_assessment(self):
        for changes in [{"availability": "out_of_stock"}, {"availability": "unknown"},
                        {"last_checked": timezone.now() - timedelta(hours=49)}]:
            with self.subTest(changes=changes):
                RetailerListing.objects.filter(pk=self.offer.pk).update(availability="in_stock", last_checked=timezone.now())
                RetailerListing.objects.filter(pk=self.offer.pk).update(**changes)
                row = self.row(self.estimate(Decimal("1000")))
                self.assertEqual(row["budget_assessment"]["status"], "incomplete")
                self.assertIsNone(row["budget_assessment"]["remaining"])
        row = self.row(self.estimate(Decimal("1000"), unresolved=[self.product.slug]))
        self.assertEqual(row["budget_assessment"]["status"], "incomplete")

    def test_delivery_scope_conflict_prevents_assessment_even_with_all_items_priced(self):
        other = Product.objects.create(slug="other-budget-pack", canonical_name="Other pack")
        RetailerListing.objects.create(product=other, retailer=self.offer.retailer, external_id="other-budget-pack",
            original_title="Other pack", current_price=Decimal("0.10"), availability="in_stock",
            last_checked=timezone.now(), delivery_area="Different area")
        row = self.row(self.estimate(Decimal("1000"), [(self.product.slug, 1), (other.slug, 1)]))
        self.assertEqual(row["covered_count"], 2)
        self.assertTrue(row["has_mixed_areas"])
        self.assertEqual(row["budget_assessment"]["status"], "incomplete")

    def test_single_unverified_complete_observed_estimate_keeps_area_warning(self):
        row = self.row(self.estimate(Decimal("1")))
        self.assertEqual(row["budget_assessment"]["remaining"], "0.70")
        self.assertTrue(row["has_unverified_areas"])
        self.assertNotIn("winner", row)

    def test_empty_list_has_no_retailer_or_zero_price_budget_claim(self):
        data = self.estimate(Decimal("3000"), [])
        self.assertEqual(data["budget"], "3000.00")
        self.assertEqual(data["retailers"], [])

    def test_demo_and_live_are_assessed_against_the_selected_items_only(self):
        params = {"source": "demo", "item": "demo-olpers-milk-1l:1", "budget": "325"}
        data = self.client.get("/api/basket/", params).json()
        self.assertEqual(self.row(data)["budget_assessment"]["status"], "at_budget")
        params["source"] = "live"
        self.assertEqual(self.row(self.client.get("/api/basket/", params).json())["budget_assessment"]["status"], "incomplete")

    def test_api_budget_bounds_and_format_validation(self):
        for amount in ["0", "0.01", "3000.10", "9999999999.99"]:
            with self.subTest(amount=amount):
                response = self.client.get("/api/basket/", {"source": "live", "item": "budget-product:3", "budget": amount})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["budget"], format(Decimal(amount), ".2f"))
        for amount in ["", "-1", "10000000000", "NaN", "Infinity", "true", "1e3", "01", ".50", "0.001", " 1", "1\n"]:
            with self.subTest(amount=amount):
                self.assertEqual(self.client.get("/api/basket/", {"budget": amount}).status_code, 400)

    def test_budget_is_read_only_and_does_not_trigger_collection(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No collection")):
            response = self.client.get("/api/basket/", {"source": "live", "item": "budget-product:3", "budget": "1.00"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
        self.assertContains(self.client.get("/shopping-list/?source=live"), "Plan your shopping budget")
