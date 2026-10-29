"""Public freshness semantics, safe summaries and permission-gated management links."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import AdminPriceRefresh, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import JalalSonsAdapter
from catalog.services.source_health import source_health


@override_settings(SCRAPING_ENABLED=True, SCRAPER_CONTACT="private-contact@example.invalid", PRICE_STALE_HOURS=48)
class PublicSourceHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        Retailer.objects.filter(slug__in=("jalal-sons", "cartpk")).update(status="enabled", collection_enabled=True)
        cls.product = Product.objects.create(slug="health-milk", canonical_name="Collected milk 1L")
        cls.now = datetime(2026, 10, 29, 12, tzinfo=datetime_timezone.utc)

    def listing(self, *, hours=1, source="jalal-sons", external_id="milk", product=None, is_demo=False, availability="in_stock"):
        return RetailerListing.objects.create(product=product or self.product, retailer=Retailer.objects.get(slug=source),
            external_id=external_id, original_title="Collected milk 1L", current_price="350.00", is_demo=is_demo,
            last_checked=self.now - timedelta(hours=hours), availability=availability)

    def recorded_run(self, *, status="success", hours=4, duration=1, **kwargs):
        started = self.now - timedelta(hours=hours)
        return ScrapeRun.objects.create(retailer=Retailer.objects.get(slug="jalal-sons"), status=status,
            started_at=started, completed_at=None if status == "running" else started + timedelta(minutes=duration), **kwargs)

    def get(self):
        with patch("catalog.services.source_health.timezone.now", return_value=self.now):
            return self.client.get(reverse("sources"))

    def row(self, health, source="jalal-sons"):
        return next(row for row in health["source_rows"] if row["retailer"].slug == source)

    def test_distinct_products_and_listing_counts_exclude_demo_and_mismatched_flags(self):
        self.listing(hours=48, availability="unknown")
        self.listing(source="cartpk", hours=49, availability="out_of_stock")
        self.listing(external_id="wrong-listing", is_demo=True)
        self.listing(external_id="wrong-product", product=Product.objects.get(slug="demo-olpers-milk-1l"))
        health = source_health(now=self.now)
        self.assertEqual(health["product_count"], 1)
        self.assertEqual(health["totals"], {"live": 2, "fresh": 1, "stale": 1, "future": 0})
        self.assertEqual(self.row(health)["retailer"].last_checked, self.now - timedelta(hours=48))
        self.assertEqual(self.row(health, "cartpk")["freshness"], "All observations stale")
        response = self.get()
        self.assertContains(response, "It does not confirm stock, delivery coverage or a checkout price")
        self.assertContains(response, "2 collected retailer listings")

    def test_future_timestamps_are_anomalies_not_recent_checks(self):
        self.listing(hours=-1)
        self.listing(hours=50, external_id="old")
        health = source_health(now=self.now)
        self.assertEqual(health["totals"], {"live": 2, "fresh": 0, "stale": 1, "future": 1})
        self.assertEqual(self.row(health)["freshness"], "Check timestamps need review")
        self.assertEqual(self.row(health)["retailer"].last_checked, self.now - timedelta(hours=50))
        response = self.get()
        self.assertContains(response, "1 listing has a future check timestamp")

    @override_settings(PRICE_STALE_HOURS=12)
    def test_configured_window_and_snapshot_time_are_rendered_consistently_in_pkt(self):
        self.listing(hours=12)
        self.listing(hours=12.001, external_id="old")
        response = self.get()
        self.assertEqual(response.context["totals"]["fresh"], 1)
        self.assertEqual(response.context["totals"]["stale"], 1)
        self.assertContains(response, "last 12 hours")
        self.assertContains(response, "after 12 hours under the current configuration")
        self.assertContains(response, "29 Oct 2026, 17:00:00 PKT")
        self.assertContains(response, "29 Oct 2026, 05:00:00 PKT")
        self.assertContains(response, "Counts describe stored data at that time")

    def test_latest_attempt_and_completed_success_remain_separate_after_partial_and_failed_runs(self):
        success = self.recorded_run(hours=10)
        self.recorded_run(status="partial", hours=3, products_collected=1)
        self.recorded_run(status="failed", hours=1)
        self.listing(hours=2)
        health = source_health(now=self.now)
        row = self.row(health)
        self.assertEqual(row["latest_outcome"], "Collection attempt failed")
        self.assertEqual(row["retailer"].last_success_at, success.completed_at)
        self.assertEqual(row["retailer"].last_checked, self.now - timedelta(hours=2))
        self.assertEqual(row["freshness"], "Recent checks recorded")
        self.assertContains(self.get(), "A successful selection covers only that run's selected URLs")

    def test_success_requires_completion_and_uses_completion_order(self):
        latest_completion = self.recorded_run(hours=5, duration=180)
        self.recorded_run(hours=4)
        invalid = self.recorded_run(hours=1)
        ScrapeRun.objects.filter(pk=invalid.pk).update(completed_at=None)
        self.assertEqual(self.row(source_health(now=self.now))["retailer"].last_success_at, latest_completion.completed_at)

    def test_old_running_record_is_shown_even_when_latest_attempt_failed_and_is_never_cleared(self):
        running = self.recorded_run(status="running", hours=80)
        self.recorded_run(status="blocked", hours=1)
        response = self.get()
        self.assertContains(response, "A collection is marked running in stored records")
        self.assertContains(response, "does not confirm that its worker is still active")
        self.assertContains(response, "Collection attempt blocked")
        running.refresh_from_db()
        self.assertEqual(running.status, "running")

    def test_source_configuration_gates_are_separate_from_data_freshness(self):
        self.listing(hours=80)
        row = self.row(source_health(now=self.now))
        self.assertEqual(row["collection_state"], "Manual collection configured")
        self.assertEqual(row["freshness"], "All observations stale")
        for overrides in ({"SCRAPING_ENABLED": False}, {"SCRAPER_CONTACT": ""}, {"SCRAPER_CONTACT": "invalid"}):
            with override_settings(**overrides):
                self.assertEqual(self.row(source_health(now=self.now))["collection_state"], "Manual collection paused")
        with patch.object(JalalSonsAdapter, "enabled", False):
            self.assertEqual(self.row(source_health(now=self.now))["collection_state"], "Collection unavailable")
        Retailer.objects.filter(slug="jalal-sons").update(collection_enabled=False)
        self.assertEqual(self.row(source_health(now=self.now))["collection_state"], "Manual collection paused")
        Retailer.objects.filter(slug="jalal-sons").update(status="pending")
        self.assertEqual(self.row(source_health(now=self.now))["collection_state"], "Source under review")
        Retailer.objects.create(name="Unknown source", slug="unknown", website="https://example.invalid", collection_enabled=True, status="enabled")
        self.assertEqual(self.row(source_health(now=self.now), "unknown")["collection_state"], "Collection unavailable")

    def test_operator_errors_results_and_contact_are_not_exposed(self):
        self.recorded_run(status="failed", error="PRIVATE-ERROR password=secret file=C:/private",
                 error_code="PRIVATE-CODE", results=[{"url": "https://example.invalid/PRIVATE-RESULT"}])
        response = self.get()
        for private in ("PRIVATE-ERROR", "PRIVATE-CODE", "PRIVATE-RESULT", "private-contact@example.invalid", "password=secret"):
            self.assertNotContains(response, private)
        retailer = self.row(response.context)["retailer"]
        self.assertFalse(hasattr(retailer, "error"))
        self.assertNotIn("recent_issues", response.context)

    def test_management_links_follow_staff_model_and_action_permissions(self):
        self.assertNotContains(self.get(), "data-source-management")
        viewer = User.objects.create_user("health-viewer", password=None)
        self.client.force_login(viewer)
        self.assertNotContains(self.get(), "data-source-management")
        viewer.is_staff = True
        viewer.save()
        self.assertNotContains(self.get(), "data-source-management")
        permissions = Permission.objects.filter(content_type__app_label="catalog", codename__in=(
            "view_retailer", "view_retailerlisting", "view_product", "view_scraperun"))
        viewer.user_permissions.set(permissions)
        response = self.get()
        self.assertContains(response, "Review collection health")
        self.assertNotContains(response, "Review and refresh stale prices")
        self.assertNotContains(response, "Import reviewed products")
        viewer.user_permissions.add(Permission.objects.get(codename="run_price_refresh"))
        self.assertContains(self.get(), "Review and refresh stale prices")
        self.assertNotContains(self.get(), "Import reviewed products")
        viewer.user_permissions.add(Permission.objects.get(codename="import_reviewed_catalog"))
        self.assertContains(self.get(), "Import reviewed products")
        viewer.is_staff = False
        viewer.save()
        self.assertNotContains(self.get(), "data-source-management")

    def test_change_permissions_allow_management_links_and_linked_admin_pages_work(self):
        viewer = User.objects.create_user("health-editor", password=None, is_staff=True)
        viewer.user_permissions.set(Permission.objects.filter(content_type__app_label="catalog", codename__in=(
            "change_retailer", "change_retailerlisting", "change_product", "change_scraperun", "import_reviewed_catalog")))
        self.client.force_login(viewer)
        soup = BeautifulSoup(self.get().content, "html.parser")
        for link in soup.select('[data-source-management] a'):
            self.assertEqual(self.client.get(link["href"].split("#")[0]).status_code, 200)

    def test_only_get_and_head_work_and_views_do_not_write_or_collect(self):
        self.listing()
        self.recorded_run(status="partial")
        models = (Retailer, Product, RetailerListing, PriceHistory, ScrapeRun, AdminPriceRefresh)
        before = [list(model.objects.order_by("pk").values()) for model in models]
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer requests")), \
             patch("catalog.services.admin_refresh.launch_refresh") as launch:
            self.assertEqual(self.get().status_code, 200)
            self.assertEqual(self.client.head(reverse("sources")).status_code, 200)
            for method in (self.client.post, self.client.put, self.client.delete):
                self.assertEqual(method(reverse("sources"), {}).status_code, 405)
        launch.assert_not_called()
        self.assertEqual(before, [list(model.objects.order_by("pk").values()) for model in models])

    def test_health_uses_two_queries_even_with_many_sources_and_observations(self):
        for index in range(12):
            Retailer.objects.create(name=f"Additional source {index}", slug=f"extra-{index}", website="https://example.invalid")
            self.listing(external_id=f"observation-{index}")
        with self.assertNumQueries(2):
            health = source_health(now=self.now)
            self.assertEqual(len(health["source_rows"]), 17)
        with self.assertNumQueries(2):
            self.assertEqual(self.get().status_code, 200)

    def test_source_browse_links_preserve_live_catalog_and_retailer(self):
        self.listing()
        response = self.get()
        soup = BeautifulSoup(response.content, "html.parser")
        link = soup.select_one('[data-source="jalal-sons"] .source-links a')
        self.assertEqual(link["href"], "/?source=live&retailer=jalal-sons#explore")
        self.assertEqual(self.client.get(link["href"].split("#")[0]).context["source"], "live")
        self.assertEqual(len(soup.select('[data-source="cartpk"] .source-links a')), 1)

    def test_source_text_is_escaped_and_snapshot_responses_cannot_be_shared_cached(self):
        Retailer.objects.filter(slug="jalal-sons").update(name='<script>alert("name")</script>', access_notes='<script>alert("notes")</script>')
        response = self.get()
        soup = BeautifulSoup(response.content, "html.parser").select_one(".source-grid")
        self.assertFalse(soup.select("script"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])


class EmptyPublicSourceHealthTests(TestCase):
    def test_empty_database_has_explicit_states_without_seeding_or_writes(self):
        response = self.client.get(reverse("sources"))
        self.assertContains(response, "No live retailer prices have been collected")
        self.assertContains(response, "No source records have been configured yet")
        self.assertEqual(response.context["product_count"], 0)
        self.assertFalse(Retailer.objects.exists())

    def test_demo_only_setup_does_not_claim_collected_coverage(self):
        call_command("seed_demo", stdout=StringIO())
        response = self.client.get(reverse("sources"))
        self.assertEqual(response.context["totals"], {"live": 0, "fresh": 0, "stale": 0, "future": 0})
        self.assertEqual(response.context["product_count"], 0)
        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEqual([node.get_text(strip=True) for node in soup.select('.source-data-state')], ["No collected observations"] * 5)
        self.assertContains(response, "No completed success recorded", count=5)
        self.assertContains(response, "explore the fictional demo catalog")
