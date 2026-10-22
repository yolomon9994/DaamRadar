from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.services.collection_health import ISSUE_LIMIT, collection_health


@override_settings(SCRAPING_ENABLED=True, PRICE_STALE_HOURS=48)
class CollectionHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.operator = User.objects.create_superuser("operator", password=None)
        cls.now = datetime(2026, 10, 22, 12, 0, tzinfo=datetime_timezone.utc)
        cls.product = Product.objects.create(canonical_name="Olpers Milk 1L", slug="collected-health-milk", brand="olpers")
        Retailer.objects.filter(slug__in=("jalal-sons", "cartpk")).update(status="enabled", collection_enabled=True)

    def setUp(self):
        self.url = reverse("admin:catalog_collection_health")
        self.client.force_login(self.operator)

    def listing(self, *, source="jalal-sons", hours=1, is_demo=False, product=None, external_id="milk", availability="in_stock"):
        return RetailerListing.objects.create(product=product or self.product, retailer=Retailer.objects.get(slug=source),
            external_id=external_id, original_title="Olpers Milk 1L", current_price="350.00", availability=availability,
            is_demo=is_demo, last_checked=self.now - timedelta(hours=hours), delivery_area="Delivery area unverified")

    def recorded_run(self, *, source="jalal-sons", status="success", hours=4, duration=1, **kwargs):
        start = self.now - timedelta(hours=hours)
        return ScrapeRun.objects.create(retailer=Retailer.objects.get(slug=source), status=status,
            started_at=start, completed_at=None if status == "running" else start + timedelta(minutes=duration), **kwargs)

    def get(self, params=None):
        with patch("catalog.services.collection_health.timezone.now", return_value=self.now):
            return self.client.get(self.url, params or {})

    def row(self, health, source="jalal-sons"):
        return next(row for row in health["source_rows"] if row["retailer"].slug == source)

    def test_counts_exclude_demo_and_mismatched_flags_and_honor_the_exact_cutoff(self):
        self.listing(hours=48, external_id="boundary", availability="unknown")
        self.listing(hours=49, external_id="old", availability="out_of_stock")
        self.listing(hours=1, is_demo=True, external_id="wrong-demo")
        self.listing(product=Product.objects.get(slug="demo-olpers-milk-1l"), hours=80, external_id="wrong-product")
        health = collection_health(now=self.now)
        self.assertEqual(health["totals"], {"live": 2, "fresh": 1, "stale": 1, "running": 0})
        retailer = self.row(health)["retailer"]
        self.assertEqual((retailer.live_count, retailer.fresh_count, retailer.stale_count), (2, 1, 1))
        self.assertEqual(retailer.last_checked, self.now - timedelta(hours=48))
        self.assertEqual(list(health["stale_listings"].values_list("external_id", flat=True)), ["old"])
        listing_admin = self.client.get(reverse("admin:catalog_retailerlisting_changelist"),
                                       {"is_demo__exact": "0", "product_source": "live"})
        self.assertEqual(listing_admin.status_code, 200)
        self.assertEqual(listing_admin.context["cl"].queryset.count(), 2)

    @override_settings(PRICE_STALE_HOURS=12)
    def test_configured_staleness_window_is_used(self):
        self.listing(hours=13)
        health = collection_health(now=self.now)
        self.assertEqual(health["totals"]["stale"], 1)
        self.assertEqual(health["cutoff"], self.now - timedelta(hours=12))

    def test_partial_or_failed_runs_do_not_replace_last_full_success(self):
        success = self.recorded_run(hours=10)
        self.recorded_run(status="partial", hours=3, products_collected=1, error_code="timeout")
        failure = self.recorded_run(status="failed", hours=1, error_code="parse_error")
        self.listing(hours=2)
        response = self.get()
        row = self.row(response.context)
        self.assertEqual(row["retailer"].last_success_id, success.pk)
        self.assertEqual(row["retailer"].latest_run_id, failure.pk)
        self.assertEqual(row["latest_status_label"], "Failed")
        self.assertEqual(row["retailer"].last_checked, self.now - timedelta(hours=2))
        self.assertEqual(len(response.context["recent_issues"]), 2)
        self.assertContains(response, "Last full success")

    def test_full_success_is_ordered_by_completion_and_requires_a_completion_time(self):
        later_completion = self.recorded_run(hours=5, duration=180)
        self.recorded_run(hours=4)
        missing_completion = self.recorded_run(hours=1)
        ScrapeRun.objects.filter(pk=missing_completion.pk).update(completed_at=None)
        health = collection_health(now=self.now)
        self.assertEqual(self.row(health)["retailer"].last_success_id, later_completion.pk)

    def test_old_running_run_is_visible_without_resetting_or_assuming_it_is_dead(self):
        active = self.recorded_run(status="running", hours=80)
        newer = self.recorded_run(status="failed", hours=1)
        response = self.get()
        row = self.row(response.context)
        self.assertEqual(row["retailer"].active_run_id, active.pk)
        self.assertEqual(row["retailer"].latest_run_id, newer.pk)
        self.assertFalse(row["manual_ready"])
        self.assertEqual(response.context["totals"]["running"], 1)
        self.assertContains(response, f"Inspect running run #{active.pk}")
        active.refresh_from_db()
        self.assertEqual(active.status, "running")

    def test_source_configuration_uses_all_switches_and_adapter_status(self):
        health = collection_health(now=self.now)
        self.assertTrue(self.row(health)["manual_ready"])
        Retailer.objects.filter(slug="naheed").update(status="enabled", collection_enabled=True)
        unavailable = self.row(collection_health(now=self.now), "naheed")
        self.assertFalse(unavailable["manual_ready"])
        self.assertIn("403", " ".join(unavailable["reasons"]))
        with override_settings(SCRAPING_ENABLED=False):
            row = self.row(collection_health(now=self.now))
        self.assertFalse(row["manual_ready"])
        self.assertIn("The global collection switch is off.", row["reasons"])
        Retailer.objects.create(name="Unconfigured store", slug="unconfigured", status="enabled", collection_enabled=True)
        row = self.row(collection_health(now=self.now), "unconfigured")
        self.assertIn("No collection adapter is configured.", row["reasons"])

    def test_retailer_filter_applies_to_counts_due_listings_and_recent_issues(self):
        self.listing(hours=80)
        self.listing(source="cartpk", hours=60)
        self.recorded_run(status="blocked")
        self.recorded_run(source="cartpk", status="partial")
        response = self.get({"retailer": "cartpk"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["source_rows"]), 1)
        self.assertEqual(response.context["totals"]["stale"], 1)
        self.assertEqual(response.context["page_obj"].object_list[0].retailer.slug, "cartpk")
        self.assertEqual(response.context["recent_issues"][0].retailer.slug, "cartpk")

    def test_invalid_filter_fails_clearly_without_showing_unfiltered_data(self):
        response = self.get({"retailer": "missing-retailer"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Select a valid choice", status_code=400)
        self.assertNotIn("source_rows", response.context)

    def test_due_listings_are_paginated_oldest_first_and_keep_the_filter(self):
        for index in range(27):
            self.listing(source="cartpk", hours=60 + index, external_id=f"milk-{index}")
        response = self.get({"retailer": "cartpk"})
        self.assertEqual(response.context["page_obj"].paginator.count, 27)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertEqual(response.context["page_obj"][0].external_id, "milk-26")
        self.assertContains(response, "retailer=cartpk&amp;page=2")
        second = self.get({"retailer": "cartpk", "page": "2"})
        self.assertEqual(len(second.context["page_obj"]), 2)
        self.assertEqual(self.get({"page": "not-a-page"}).status_code, 200)

    def test_recent_issues_are_bounded_and_remain_visible_after_success(self):
        for index in range(ISSUE_LIMIT + 3):
            self.recorded_run(status="failed", hours=index + 2)
        self.recorded_run(hours=1)
        health = collection_health(now=self.now)
        self.assertEqual(len(health["recent_issues"]), ISSUE_LIMIT)
        self.assertEqual(self.row(health)["latest_status_label"], "Success")
        self.assertTrue(all(run.status == "failed" for run in health["recent_issues"]))
        self.assertEqual(health["recent_issues"][0].started_at, self.now - timedelta(hours=2))

    def test_diagnostics_use_two_eager_queries_regardless_of_source_count(self):
        self.listing(hours=60)
        self.recorded_run(status="partial")
        with self.assertNumQueries(2):
            health = collection_health(now=self.now)
            for row in health["source_rows"]:
                _ = (row["retailer"].last_success_at, row["retailer"].live_count, row["manual_ready"])
            for run in health["recent_issues"]:
                _ = run.retailer.name

    def test_access_requires_active_staff_and_all_relevant_model_permissions(self):
        self.client.logout()
        self.assertRedirects(self.get(), reverse("admin:login") + f"?next={self.url}", fetch_redirect_response=False)
        public = User.objects.create_user("public", password=None)
        self.client.force_login(public)
        self.assertEqual(self.get().status_code, 302)
        staff = User.objects.create_user("staff", password=None, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.get().status_code, 403)
        for model in ("retailer", "retailerlisting", "product"):
            staff.user_permissions.add(Permission.objects.get(codename=f"view_{model}"))
        self.assertEqual(self.get().status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_scraperun"))
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse("admin:index")), "Collection health")
        self.assertContains(self.client.get(reverse("admin:catalog_retailer_changelist")), "Collection health")
        staff.is_active = False
        staff.save()
        self.assertEqual(self.get().status_code, 302)

    def test_change_permissions_also_allow_viewing(self):
        staff = User.objects.create_user("editor", password=None, is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(codename__in=[f"change_{model}" for model in ("retailer", "retailerlisting", "product", "scraperun")]))
        self.client.force_login(staff)
        self.assertEqual(self.get().status_code, 200)

    def test_loading_or_posting_cannot_start_collection_or_mutate_records(self):
        listing = self.listing(hours=60)
        self.recorded_run(status="partial", error="A connection closed.")
        before = (list(RetailerListing.objects.values()), list(ScrapeRun.objects.values()),
                  PriceHistory.objects.count(), list(Retailer.objects.values()))
        with patch("requests.Session.get") as get:
            self.assertEqual(self.get().status_code, 200)
            self.assertEqual(self.client.post(self.url, {"retailer": "jalal-sons"}).status_code, 405)
        get.assert_not_called()
        after = (list(RetailerListing.objects.values()), list(ScrapeRun.objects.values()),
                 PriceHistory.objects.count(), list(Retailer.objects.values()))
        self.assertEqual(before, after)
        listing.refresh_from_db()
        self.assertEqual(listing.last_checked, self.now - timedelta(hours=60))

    def test_error_text_and_source_names_are_escaped(self):
        run = self.recorded_run(status="failed", error='<script>alert("error")</script>')
        run.retailer.name = '<script>alert("source")</script>'
        run.retailer.save()
        response = self.get()
        soup = BeautifulSoup(response.content, "html.parser").select_one(".collection-health")
        self.assertFalse(soup.select("script"))
        self.assertIn(run.error, soup.get_text())
        self.assertContains(response, "&lt;script&gt;")

    def test_admin_drilldown_links_work(self):
        self.listing(hours=60)
        self.recorded_run(status="failed")
        response = self.get()
        soup = BeautifulSoup(response.content, "html.parser").select_one(".collection-health")
        links = {link["href"] for link in soup.select('a[href^="/admin/"]')}
        for url in links:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class EmptyCollectionHealthTests(TestCase):
    def test_fresh_database_shows_empty_states_without_seeding_or_collecting(self):
        self.client.force_login(User.objects.create_superuser("operator", password=None))
        response = self.client.get(reverse("admin:catalog_collection_health"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No retailers configured")
        self.assertContains(response, "No stale collected listings")
        self.assertContains(response, "No failed, blocked, or partial runs")
        self.assertFalse(Retailer.objects.exists())
