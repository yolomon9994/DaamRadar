from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import Product, Retailer, RetailerListing
from catalog.services.basket import estimate_basket
from catalog.services.catalog import search_suggestions
from catalog.services.pack_comparison import pack_comparison
from catalog.services.snapshots import snapshot_metadata
from catalog.services.source_health import source_health
from catalog.services.watchlist import check_targets


class SnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.product = Product.objects.create(slug="snapshot-milk", canonical_name="Olpers Milk 1L", brand="olpers", quantity=Decimal("1000"), unit="ml")
        cls.offer = RetailerListing.objects.create(product=cls.product, retailer=Retailer.objects.get(slug="naheed"),
            external_id="snapshot-milk", original_title="Olpers Milk 1L", current_price="300.00", availability="in_stock")

    def setUp(self):
        self.now = timezone.now()

    def test_maximum_lifetime_and_old_observations(self):
        for checks in [[], [self.now - timedelta(days=3)], [self.now - timedelta(hours=1)]]:
            self.assertEqual(snapshot_metadata(checks, now=self.now)["expires_at"], (self.now + timedelta(minutes=5)).isoformat())

    def test_earliest_inclusive_freshness_cutoff_and_future_activation(self):
        for check, expiry in [(self.now - timedelta(hours=48), self.now),
                              (self.now - timedelta(hours=48) + timedelta(seconds=2), self.now + timedelta(seconds=2)),
                              (self.now + timedelta(seconds=3), self.now + timedelta(seconds=3))]:
            with self.subTest(check=check):
                self.assertEqual(snapshot_metadata([check], now=self.now)["expires_at"], expiry.isoformat())

    def test_basket_excludes_future_prices_totals_and_budget_claims(self):
        RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=self.now + timedelta(seconds=2))
        with patch("catalog.services.basket.timezone.now", return_value=self.now):
            data = estimate_basket([(self.product.slug, 2)], "live", budget=Decimal("1000"))
        row = data["retailers"][0]
        self.assertIsNone(row["total"])
        self.assertIsNone(row["subtotal"])
        self.assertEqual(row["lines"][0]["status"], "check_time_invalid")
        self.assertEqual(row["budget_assessment"]["status"], "incomplete")
        self.assertEqual(data["expires_at"], (self.now + timedelta(seconds=2)).isoformat())

    def test_basket_includes_exact_cutoff_but_excludes_after_it(self):
        RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=self.now - timedelta(hours=48))
        with patch("catalog.services.basket.timezone.now", return_value=self.now):
            data = estimate_basket([(self.product.slug, 2)], "live")
        self.assertEqual(data["retailers"][0]["total"], "600.00")
        self.assertEqual(data["expires_at"], self.now.isoformat())
        with patch("catalog.services.basket.timezone.now", return_value=self.now + timedelta(microseconds=1)):
            data = estimate_basket([(self.product.slug, 2)], "live")
        self.assertIsNone(data["retailers"][0]["total"])

    def test_expiry_tracks_all_fresh_offers_not_just_the_current_minimum(self):
        RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=self.now - timedelta(hours=48) + timedelta(seconds=4), availability="out_of_stock")
        RetailerListing.objects.create(product=self.product, retailer=Retailer.objects.get(slug="springs"),
            external_id="later", original_title=self.product.canonical_name, current_price="325", availability="in_stock", last_checked=self.now)
        with patch("catalog.services.basket.timezone.now", return_value=self.now), patch("catalog.services.watchlist.timezone.now", return_value=self.now):
            basket = estimate_basket([(self.product.slug, 1)], "live")
            watch = check_targets([(self.product.slug, Decimal("330"))], "live")
        self.assertEqual(basket["expires_at"], watch["expires_at"])
        self.assertEqual(basket["expires_at"], (self.now + timedelta(seconds=4)).isoformat())

    def test_pack_and_source_snapshots_follow_near_boundary_without_extra_source_queries(self):
        checked = self.now - timedelta(hours=48) + timedelta(seconds=2)
        RetailerListing.objects.filter(pk=self.offer.pk).update(last_checked=checked)
        data = pack_comparison(self.product, now=self.now)
        with CaptureQueriesContext(connection) as queries:
            health = source_health(now=self.now)
        self.assertEqual(len(queries), 2)
        self.assertEqual(data["snapshot"]["expires_at"], (self.now + timedelta(seconds=2)).isoformat())
        self.assertEqual(health["snapshot"]["expires_at"], data["snapshot"]["expires_at"])

    def test_html_and_product_api_are_uncached_and_publish_explicit_snapshot_metadata(self):
        for url in ["/?source=live", "/products/snapshot-milk/", "/products/snapshot-milk/pack-comparison/", "/sources/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertContains(response, "data-snapshot-expires")
            self.assertContains(response, "Automatic expiry needs JavaScript")
        for url in ["/api/products/snapshot-milk/", "/api/products/?source=live"]:
            response = self.client.get(url)
            self.assertIn("no-store", response["Cache-Control"])
            data = response.json()
            item = data["results"][0] if "results" in data else data
            self.assertEqual(item["snapshot"]["max_age_seconds"], 300)

    def test_lightweight_suggestions_keep_identity_and_filters_without_decorating_offers(self):
        with patch("catalog.services.catalog.decorate", side_effect=AssertionError("Suggestions do not display offers")), CaptureQueriesContext(connection) as queries:
            products = search_suggestions({"source": "live", "q": "Olpers Milk 1L", "fresh": "1", "max_price": "300"})
        self.assertEqual([p.slug for p in products], [self.product.slug])
        self.assertEqual(len(queries), 2)
        self.assertEqual(search_suggestions({"source": "live", "q": "Olpers Milk 250ml"}), [])

    def test_detail_prefetch_joins_retailers_and_has_no_per_offer_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/products/snapshot-milk/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 4)

    def test_detail_table_and_skip_target_are_keyboard_reachable_without_javascript(self):
        response = self.client.get("/products/snapshot-milk/")
        self.assertContains(response, 'id="main" tabindex="-1"')
        self.assertContains(response, 'tabindex="0" role="region" aria-label="Retailer comparisons')
