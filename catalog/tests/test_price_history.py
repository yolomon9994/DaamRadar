from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import TestCase

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.services.catalog import decorate, get_product_queryset
from catalog.services.history import HISTORY_LIMIT, LEFT, RIGHT, price_history_chart


class PriceHistoryChartTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.product = Product.objects.create(canonical_name="Olpers Milk 1L", slug="collected-milk", brand="olpers")
        cls.start = datetime(2026, 10, 18, 20, 0, tzinfo=datetime_timezone.utc)

    def listing(self, source="jalal-sons", area="Delivery area unverified", is_demo=False, external_id="milk"):
        return RetailerListing.objects.create(product=self.product, retailer=Retailer.objects.get(slug=source),
            original_title="Olpers Milk 1L", external_id=external_id, current_price=Decimal("999"),
            delivery_area=area, is_demo=is_demo)

    def record(self, listing, price="350.00", hours=0):
        return PriceHistory.objects.create(listing=listing, price=Decimal(price), checked_at=self.start + timedelta(hours=hours))

    def chart(self):
        return price_history_chart(decorate(get_product_queryset().get(pk=self.product.pk)))

    def page(self):
        response = self.client.get(f"/products/{self.product.slug}/")
        self.assertEqual(response.status_code, 200)
        return response, BeautifulSoup(response.content, "html.parser").select_one("[data-price-history]")

    def test_points_use_actual_prices_and_elapsed_times_in_chronological_order(self):
        listing = self.listing()
        self.record(listing, "360.25", hours=24)
        self.record(listing, "350.00", hours=0)
        self.record(listing, "350.00", hours=6)
        chart = self.chart()
        points = chart["series"][0]["points"]
        self.assertEqual([point["price"] for point in points], [Decimal("350"), Decimal("350"), Decimal("360.25")])
        self.assertEqual([point["x"] for point in points], [LEFT, LEFT + (RIGHT - LEFT) / 4, RIGHT])
        self.assertEqual(points[0]["y"], points[1]["y"])
        self.assertGreater(points[0]["y"], points[2]["y"])
        self.assertEqual(points[0]["checked_at"].hour, 1)
        self.assertEqual(points[0]["checked_at"].day, 19)
        self.assertEqual(chart["time_ticks"][0]["date"], points[0]["checked_at"])
        self.assertEqual(chart["time_ticks"][-1]["date"], points[-1]["checked_at"])
        response, section = self.page()
        self.assertEqual(len(section.select("circle")), 3)
        self.assertEqual(len(section.select("polyline")), 1)
        self.assertIn("19 Oct 2026, 01:00:00 PKT", section.select_one("circle title").get_text())
        self.assertIn("360.25", section.select_one(".history-table").get_text())
        self.assertIn("prices between checks are unknown", section.get_text())

    def test_single_observation_is_one_point_without_a_trend_line(self):
        self.record(self.listing(), "350.25")
        response, section = self.page()
        self.assertEqual(len(section.select("circle")), 1)
        self.assertFalse(section.select("polyline"))
        self.assertIn("One observation; no trend yet", section.get_text())
        self.assertEqual(float(section.select_one("circle")["cx"]), (LEFT + RIGHT) / 2)
        self.assertNotIn("NaN", str(section))
        self.assertNotIn("Infinity", str(section))

    def test_empty_history_does_not_invent_a_point_from_current_price(self):
        self.listing()
        response, section = self.page()
        self.assertIn("No observations recorded yet", section.get_text())
        self.assertFalse(section.select("svg, circle, polyline, .history-table"))
        self.assertEqual(self.chart()["count"], 0)

    def test_product_without_listings_has_an_honest_empty_state(self):
        response, section = self.page()
        self.assertFalse(section.select("[data-history-toggle]"))
        self.assertIn("No observations recorded yet", section.get_text())

    def test_retailer_series_are_separate_and_empty_series_is_not_a_chart_control(self):
        jalal = self.listing()
        cartpk = self.listing("cartpk")
        self.listing("naheed")
        self.record(jalal, hours=0)
        self.record(jalal, "355", hours=24)
        self.record(cartpk, "360", hours=6)
        chart = self.chart()
        self.assertEqual(len(chart["series"]), 3)
        self.assertEqual(chart["count"], 3)
        self.assertEqual(len({item["color"] for item in chart["series"]}), 3)
        response, section = self.page()
        self.assertEqual(len(section.select("[data-history-series]")), 2)
        self.assertEqual(len(section.select("polyline")), 1)
        self.assertEqual(len(section.select(".history-table tbody tr")), 3)
        for toggle in section.select("[data-history-toggle]"):
            self.assertTrue(toggle.has_attr("hidden"))  # Progressive enhancement; SVG/table need no JS.
        self.assertIn("Naheed", section.get_text())
        self.assertIn("No observations recorded", section.get_text())

    def test_demo_chart_is_explicitly_fictional_and_excludes_collected_history(self):
        self.record(self.listing(), "9999")
        response = self.client.get("/products/demo-olpers-milk-1l/")
        section = BeautifulSoup(response.content, "html.parser").select_one("[data-price-history]")
        self.assertIn("Fictional demo prices", section.get_text())
        self.assertIn("Sample price history", section.get_text())
        self.assertNotIn("9999", str(section))
        self.assertEqual(len(section.select("circle")), 3)
        self.assertFalse(section.select("polyline"))

    def test_mismatched_demo_listing_is_excluded_from_live_chart(self):
        self.record(self.listing(), "350")
        self.record(self.listing("cartpk", is_demo=True), "9999")
        chart = self.chart()
        self.assertEqual(chart["count"], 1)
        self.assertEqual(chart["series"][0]["label"], "Jalal Sons")
        response, section = self.page()
        self.assertNotIn("Cartpk", section.get_text())
        self.assertNotIn("9,999", section.get_text())

    def test_same_retailer_different_areas_keep_independent_labels_and_series(self):
        for area in ("Lahore", "Karachi"):
            self.record(self.listing(area=area))
        chart = self.chart()
        self.assertEqual(len(chart["series"]), 2)
        self.assertIn("Lahore", chart["series"][0]["label"])
        self.assertIn("Karachi", chart["series"][1]["label"])
        self.assertNotEqual(chart["series"][0]["id"], chart["series"][1]["id"])

    def test_history_is_bounded_per_listing_without_dropping_other_retailers(self):
        jalal, cartpk = self.listing(), self.listing("cartpk")
        PriceHistory.objects.bulk_create([
            PriceHistory(listing=jalal, price=Decimal("350"), checked_at=self.start + timedelta(minutes=index))
            for index in range(HISTORY_LIMIT + 10)
        ])
        self.record(cartpk, "360")
        product = decorate(get_product_queryset().get(pk=self.product.pk))
        with self.assertNumQueries(1):
            chart = price_history_chart(product)
        self.assertEqual(chart["count"], HISTORY_LIMIT + 1)
        self.assertTrue(chart["truncated"])
        self.assertEqual(chart["series"][1]["points"][0]["checked_at"], (self.start + timedelta(minutes=10)).astimezone(chart["records"][0]["checked_at"].tzinfo))
        response, section = self.page()
        self.assertIn("Showing the latest 120 observations per listing", section.get_text())
        self.assertEqual(len(section.select("circle")), HISTORY_LIMIT + 1)

    def test_equal_timestamps_and_prices_have_finite_coordinates_and_keep_both_observations(self):
        listing = self.listing()
        first, second = self.record(listing), self.record(listing)
        chart = self.chart()
        self.assertEqual([row["pk"] for row in chart["records"]], [first.pk, second.pk])
        self.assertEqual(len(chart["time_ticks"]), 1)
        self.assertTrue(all(row["x"] == (LEFT + RIGHT) / 2 for row in chart["records"]))
        self.assertEqual(chart["records"][0]["y"], chart["records"][1]["y"])

    def test_untrusted_names_are_escaped_in_svg_attributes_and_table(self):
        listing = self.listing()
        listing.retailer.name = '</title><script>alert("history")</script>'
        listing.retailer.save()
        self.record(listing)
        response, section = self.page()
        self.assertFalse(section.select("script"))
        self.assertIn(listing.retailer.name, section.select_one("circle")["aria-label"])
        self.assertContains(response, "&lt;script&gt;")

    def test_loading_page_never_collects_or_changes_history(self):
        self.record(self.listing())
        before = list(PriceHistory.objects.values_list("pk", "price", "checked_at"))
        with patch("requests.Session.get") as get:
            self.page()
            self.page()
        get.assert_not_called()
        self.assertEqual(list(PriceHistory.objects.values_list("pk", "price", "checked_at")), before)
