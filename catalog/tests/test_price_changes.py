import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from catalog.admin import PriceHistoryAdmin
from catalog.models import PriceHistory, Product, Retailer
from catalog.scraping.types import ScrapedProduct
from catalog.services.catalog import decorate, get_product_queryset
from catalog.services.history import price_history_chart
from catalog.services.ingestion import ingest
from catalog.services.observations import context_known
from catalog.services.price_changes import attach_price_changes


class PriceChangeTests(TestCase):
    def setUp(self):
        call_command("seed_retailers", stdout=StringIO())
        self.retailer = Retailer.objects.get(slug="alfatah")
        self.item = ScrapedProduct("milk-change", "Olpers Milk 1L", "https://alfatah.pk/products/milk",
                                   Decimal("340"), availability="in_stock")
        self.now = timezone.now()

    def collect(self, price="340", hours=2, **changes):
        with patch("catalog.services.ingestion.timezone.now", return_value=self.now - timedelta(hours=hours)):
            return ingest(self.retailer, replace(self.item, price=Decimal(price), **changes))[0]

    def product(self, listing):
        product = decorate(get_product_queryset().get(pk=listing.product_id))
        attach_price_changes([product])
        return product

    def change(self, listing):
        return next(offer.price_change for offer in self.product(listing).offers if offer.pk == listing.pk)

    def pair(self, price="325"):
        self.collect()
        return self.collect(price, hours=1)

    def test_decrease_increase_and_unchanged_use_decimal_previous_check(self):
        for previous, latest, status, amount, percent in [("340", "325", "decreased", "15.00", "4.41"),
            ("325", "350", "increased", "25.00", "7.69"), ("350", "350", "unchanged", "0.00", "0.00")]:
            with self.subTest(status=status):
                self.item = replace(self.item, external_id=status)
                self.collect(previous)
                listing = self.collect(latest, hours=1)
                change = self.change(listing)
                self.assertEqual((change["status"], change["amount"], change["percent"]), (status, amount, percent))
                self.assertEqual(change["previous_price"], format(Decimal(previous), ".2f"))

    def test_latest_two_checks_not_last_distinct_price(self):
        self.collect("340", hours=3)
        self.collect("325", hours=2)
        self.assertEqual(self.change(self.collect("325", hours=1))["status"], "unchanged")

    def test_one_or_no_history_never_invents_an_earlier_price(self):
        listing = self.collect()
        self.assertEqual(self.change(listing)["status"], "no_previous")
        listing.history.all().delete()
        self.assertEqual(self.change(listing)["status"], "no_previous")

    def test_context_is_captured_at_ingestion_and_not_mutated_by_later_edits(self):
        listing = self.collect()
        row = listing.history.get()
        original = copy.deepcopy(row.context)
        self.assertTrue(context_known(original))
        self.assertEqual(original["product"]["quantity"], "1000.000")
        self.assertEqual(original["external_id"], self.item.external_id)
        self.assertEqual(original["availability"], "in_stock")
        self.assertFalse(original["area_is_verified"])
        self.assertIsNone(original["area_verified_at"])
        Product.objects.filter(pk=listing.product_id).update(canonical_name="A changed current title")
        row.refresh_from_db()
        self.assertEqual(row.context, original)

    def test_legacy_or_malformed_context_withholds_change_instead_of_guessing(self):
        listing = self.pair()
        previous = listing.history.order_by("checked_at").first()
        for context in [None, {}, {"version": 99}, {"version": True}]:
            with self.subTest(context=context):
                PriceHistory.objects.filter(pk=previous.pk).update(context=context)
                change = self.change(listing)
                self.assertEqual(change["status"], "context_unknown")
                self.assertIsNone(change["amount"])

    def test_current_manual_changes_are_not_presented_as_recorded_price_moves(self):
        listing = self.pair()
        listing.current_price = Decimal("1")
        listing.save()
        self.assertEqual(self.change(listing)["status"], "unrecorded_changes")

    def test_pack_or_delivery_context_changes_withhold_delta(self):
        listing = self.pair()
        previous = listing.history.order_by("checked_at").first()
        original = copy.deepcopy(previous.context)
        for field, value in [("delivery_area", "Different area"), ("delivery_area_key", "different"),
                             ("area_is_verified", True), ("is_demo", True), ("url", "https://alfatah.pk/other")]:
            with self.subTest(field=field):
                PriceHistory.objects.filter(pk=previous.pk).update(context={**original, field: value})
                self.assertEqual(self.change(listing)["status"], "context_changed")
        changed = copy.deepcopy(original)
        changed["product"]["pack_count"] = 6
        PriceHistory.objects.filter(pk=previous.pk).update(context=changed)
        self.assertEqual(self.change(listing)["status"], "context_changed")

    def test_stock_context_does_not_create_a_drop_badge(self):
        self.collect()
        listing = self.collect("1", hours=1, availability="out_of_stock")
        self.assertEqual(self.change(listing)["status"], "stock_unavailable")

    def test_equal_or_future_check_times_withhold_delta(self):
        listing = self.pair()
        previous = listing.history.order_by("checked_at").first()
        PriceHistory.objects.filter(pk=previous.pk).update(checked_at=listing.last_checked)
        self.assertEqual(self.change(listing)["status"], "invalid_time")
        PriceHistory.objects.filter(pk=previous.pk).update(checked_at=self.now + timedelta(days=1))
        self.assertEqual(self.change(listing)["status"], "invalid_time")

    def test_stale_recorded_change_keeps_stale_listing_context_and_no_winner(self):
        self.collect(hours=74)
        listing = self.collect("325", hours=73)
        product = self.product(listing)
        self.assertEqual(product.offers[0].price_change["status"], "decreased")
        self.assertTrue(product.offers[0].is_stale)
        self.assertIsNone(product.best_price)
        self.assertFalse(product.best_ids)

    def test_alias_title_on_same_canonical_pack_can_compare(self):
        self.collect()
        listing = self.collect("325", hours=1, title="Olper's UHT Milk 1000ml")
        self.assertEqual(self.change(listing)["status"], "decreased")

    def test_reassigned_listing_does_not_compare_or_chart_another_product(self):
        self.collect()
        listing = self.collect("500", hours=1, title="Olpers Chocolate Milk 1L")
        product = self.product(listing)
        self.assertEqual(product.offers[0].price_change["status"], "context_changed")
        chart = price_history_chart(product)
        self.assertEqual(chart["count"], 1)
        self.assertEqual(chart["records"][0]["price"], Decimal("500"))

    def test_chart_preserves_captured_areas_and_breaks_known_context_changes(self):
        listing = self.pair()
        previous = listing.history.order_by("checked_at").first()
        context = {**previous.context, "delivery_area": "Earlier area"}
        PriceHistory.objects.filter(pk=previous.pk).update(context=context)
        chart = price_history_chart(self.product(listing))
        self.assertEqual(chart["count"], 2)
        self.assertEqual(chart["records"][0]["context"]["delivery_area"], "Earlier area")
        self.assertEqual(chart["series"][0]["segments"], [])

    def test_legacy_history_api_exposes_unknown_source_and_captured_source_survives_edits(self):
        listing = self.collect()
        listing.is_demo = True
        listing.save()
        data = self.client.get(f"/api/listings/{listing.pk}/history/").json()["results"][0]
        self.assertFalse(data["is_demo"])
        self.assertEqual(data["context_status"], "captured")
        listing.history.update(context=None)
        data = self.client.get(f"/api/listings/{listing.pk}/history/").json()["results"][0]
        self.assertIsNone(data["is_demo"])
        self.assertEqual(data["context_status"], "unknown")

    def test_badges_and_dates_render_on_cards_details_and_api_without_network(self):
        listing = self.pair()
        before = list(PriceHistory.objects.values_list("pk", "price", "checked_at", "context"))
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer requests")):
            self.assertContains(self.client.get("/?source=live"), "Recorded decrease: Rs. 15.00")
            response = self.client.get(f"/products/{listing.product.slug}/")
            self.assertContains(response, "4.41% absolute change")
            self.assertContains(response, "PKT")
            data = self.client.get(f"/api/products/{listing.product.slug}/").json()
            self.assertEqual(data["listings"][0]["price_change"]["amount"], "15.00")
        self.assertEqual(before, list(PriceHistory.objects.values_list("pk", "price", "checked_at", "context")))

    def test_history_change_lookup_is_one_query_for_all_listings(self):
        listing = self.pair()
        product = decorate(get_product_queryset().get(pk=listing.product_id))
        with self.assertNumQueries(1):
            attach_price_changes([product])
        self.assertEqual(product.offers[0].price_change["status"], "decreased")

    def test_admin_history_is_inspectable_but_cannot_be_added_changed_or_deleted(self):
        admin = PriceHistoryAdmin(PriceHistory, AdminSite())
        self.assertFalse(admin.has_add_permission(None))
        self.assertFalse(admin.has_change_permission(None))
        self.assertFalse(admin.has_delete_permission(None))


class ObservationMigrationTests(TransactionTestCase):
    def test_legacy_price_and_time_survive_migration_without_context_backfill(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("catalog", "0005_alter_adminpricerefresh_options_and_more")])
            apps = executor.loader.project_state([("catalog", "0005_alter_adminpricerefresh_options_and_more")]).apps
            retailer = apps.get_model("catalog", "Retailer").objects.create(name="Legacy", slug="legacy", website="https://legacy.invalid")
            product = apps.get_model("catalog", "Product").objects.create(canonical_name="Legacy pack", slug="legacy-pack")
            checked = timezone.now() - timedelta(days=10)
            listing = apps.get_model("catalog", "RetailerListing").objects.create(retailer=retailer, product=product,
                external_id="legacy", original_title="Legacy pack", current_price=Decimal("45"), last_checked=checked)
            row = apps.get_model("catalog", "PriceHistory").objects.create(listing=listing, price=Decimal("45"), checked_at=checked)
            MigrationExecutor(connection).migrate(latest)
            restored = PriceHistory.objects.get(pk=row.pk)
            self.assertEqual((restored.price, restored.checked_at, restored.context), (Decimal("45"), checked, None))
        finally:
            MigrationExecutor(connection).migrate(latest)
