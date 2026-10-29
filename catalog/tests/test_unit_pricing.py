from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.basket import estimate_basket
from catalog.services.catalog import decorate, get_product_queryset, search_catalog
from catalog.services.unit_pricing import standard_unit_price


class UnitPriceCalculationTests(SimpleTestCase):
    def rate(self, quantity, unit, price, packs=1):
        return standard_unit_price(SimpleNamespace(quantity=quantity, unit=unit, pack_count=packs), price)

    def test_liquid_mass_and_count_rates_use_total_pack_contents(self):
        for quantity, unit, price, packs, amount, per in [
            (500, "ml", 180, 1, "360.00", "L"), (1000, "ml", 325, 1, "325.00", "L"),
            (250, "ml", 510, 6, "340.00", "L"), (50, "g", 140, 1, "2800.00", "kg"),
            (4500, "ml", 3000, 1, "666.67", "L"), (250, "g", 200, 2, "400.00", "kg"),
            (6, "pc", 120, 2, "10.00", "item"), (1, "pc", 25, 1, "25.00", "item"),
        ]:
            with self.subTest(quantity=quantity, unit=unit, packs=packs):
                rate = self.rate(quantity, unit, price, packs)
                self.assertEqual((rate["amount"], rate["unit"], rate["less_than"]), (amount, per, None))

    def test_decimal_rounding_and_display_are_explicit(self):
        self.assertEqual(self.rate(400, "ml", "1.07")["display"], "Rs. 2.68/L")
        self.assertEqual(self.rate(50, "g", 140)["display"], "Rs. 2,800.00/kg")

    def test_unknown_unsupported_and_invalid_dimensions_never_guess(self):
        for quantity, unit, price, packs in [(None, "ml", 100, 1), (1000, "", 100, 1),
            (1, "L", 100, 1), (1, "kg", 100, 1), (0, "ml", 100, 1), (-1, "g", 100, 1),
            (1, "ml", 100, 0), (1, "ml", 100, "1.5"), ("1.5", "pc", 100, 1),
            ("NaN", "g", 100, 1), (100, "g", "Infinity", 1), (100, "g", None, 1),
            (100, "g", -1, 1), (100, "g", 0, 1), (True, "pc", 10, 1), (1, "pc", 10, True)]:
            with self.subTest(quantity=quantity, unit=unit, price=price, packs=packs):
                self.assertIsNone(self.rate(quantity, unit, price, packs))

    def test_small_positive_rate_never_displays_a_free_unit(self):
        rate = self.rate("9999999.999", "g", "0.01", 32767)
        self.assertEqual(rate, {"amount": None, "unit": "kg", "less_than": "0.01", "display": "< Rs. 0.01/kg"})


class UnitPriceIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.multipack = Product.objects.create(slug="live-six-milks", canonical_name="Olpers Milk 6 x 250ml",
            brand="olpers", quantity=Decimal("250"), unit="ml", pack_count=6)
        cls.offer = RetailerListing.objects.create(product=cls.multipack, retailer=Retailer.objects.get(slug="naheed"),
            external_id="six-milks", original_title=cls.multipack.canonical_name, current_price=Decimal("510"),
            availability="in_stock", last_checked=timezone.now())

    def decorated(self):
        return decorate(get_product_queryset().get(pk=self.multipack.pk))

    def test_cards_details_and_api_show_rates_beside_pack_prices(self):
        for path in ["/?source=demo&q=Olpers", "/products/demo-olpers-milk-250ml/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "Rs. 340.00/L")
                self.assertContains(response, "fictional")
        for path in ["/api/products/live-six-milks/", "/api/products/?source=live"]:
            with self.subTest(path=path):
                data = self.client.get(path).json()
                if "results" in data:
                    data = data["results"][0]
                self.assertEqual(data["standard_unit_price"]["amount"], "340.00")
                self.assertEqual(data["best_price"], "510.00")
                self.assertEqual(data["listings"][0]["standard_unit_price"]["display"], "Rs. 340.00/L")
                self.assertTrue(data["has_unverified_areas"])
                self.assertFalse(data["has_comparison"])

    def test_multipack_basket_rate_is_independent_of_requested_pack_quantity(self):
        for requested in [1, 3]:
            row = estimate_basket([(self.multipack.slug, requested)], "live")["retailers"][0]
            self.assertEqual(row["lines"][0]["unit_price"], "510.00")
            self.assertEqual(row["lines"][0]["standard_unit_price"]["amount"], "340.00")
            self.assertEqual(row["total"], format(Decimal(510) * requested, ".2f"))
            self.assertTrue(row["has_unverified_areas"])

    def test_stale_and_unavailable_rates_keep_the_original_observation_context(self):
        for changes in [{"last_checked": timezone.now() - timedelta(days=3)}, {"availability": "out_of_stock"}, {"availability": "unknown"}]:
            with self.subTest(changes=changes):
                RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=timezone.now(), availability="in_stock")
                RetailerListing.objects.filter(pk=self.offer.pk).update(**changes)
                product = self.decorated()
                self.assertIsNone(product.standard_unit_price)
                self.assertEqual(product.offers[0].standard_unit_price["amount"], "340.00")
                self.assertFalse(product.best_ids)
                data = self.client.get("/api/products/live-six-milks/").json()
                self.assertIsNone(data["standard_unit_price"])
                line = estimate_basket([(self.multipack.slug, 1)], "live")["retailers"][0]["lines"][0]
                self.assertIsNone(line["standard_unit_price"])
                self.assertIsNone(line["line_total"])

    def test_unknown_size_keeps_pack_price_and_explicit_unavailable_rate(self):
        Product.objects.filter(pk=self.multipack.pk).update(quantity=None, unit="")
        response = self.client.get("/products/live-six-milks/")
        self.assertContains(response, "Unit price unavailable")
        self.assertContains(response, "Rs. 510")
        data = self.client.get("/api/products/live-six-milks/").json()
        self.assertIsNone(data["standard_unit_price"])
        self.assertIsNone(data["listings"][0]["standard_unit_price"])

    def test_rates_do_not_create_winners_or_change_pack_price_sorting(self):
        product = self.decorated()
        self.assertEqual(product.standard_unit_price["amount"], "340.00")
        self.assertFalse(product.has_comparison)
        self.assertEqual(product.savings, 0)
        products = search_catalog({"source": "demo", "q": "Olpers", "sort": "price_asc"})
        self.assertEqual([p.slug for p in products], ["demo-olpers-milk-250ml", "demo-olpers-milk-1l"])
        self.assertEqual([p.standard_unit_price["amount"] for p in products], ["340.00", "325.00"])

    def test_forced_unresolved_item_never_gets_a_standard_unit_price(self):
        result = estimate_basket([(self.multipack.slug, 1)], "live", [self.multipack.slug])
        self.assertIsNone(result["retailers"][0]["lines"][0]["standard_unit_price"])

    def test_display_calculation_has_no_writes_or_retailer_requests(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer requests")):
            self.assertEqual(self.client.get("/products/live-six-milks/").status_code, 200)
            self.assertEqual(self.client.get("/api/products/?source=demo").status_code, 200)
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
