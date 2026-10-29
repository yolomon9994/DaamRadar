from copy import deepcopy
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import AdminPriceRefresh, PriceHistory, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.types import CollectionError
from catalog.services.admin_refresh import launch_refresh, refresh_progress, run_refresh, validate_refresh, validate_worker_database
from catalog.services.ingestion import ingest
from .test_refresh_prices import CARTPK_HTML, CARTPK_URL, JALAL_HTML, JALAL_URL


@override_settings(SCRAPING_ENABLED=True, SCRAPER_CONTACT="operator@example.invalid")
class AdminRefreshTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.operator = User.objects.create_superuser("refresh-operator", password=None)
        Retailer.objects.filter(slug__in=["jalal-sons", "cartpk"]).update(status="enabled", collection_enabled=True)
        for slug, adapter, url, html in [("jalal-sons", JalalSonsAdapter(), JALAL_URL, JALAL_HTML),
                                         ("cartpk", CartpkAdapter(), CARTPK_URL, CARTPK_HTML)]:
            client = MagicMock()
            client.get_html.return_value = html
            ingest(Retailer.objects.get(slug=slug), adapter.collect(client, url))
        RetailerListing.objects.filter(is_demo=False).update(last_checked=timezone.now() - timedelta(days=3))

    def setUp(self):
        self.client.force_login(self.operator)
        self.start = reverse("admin:catalog_refresh_start")
        self.events = []

    def job(self, sources=None, **values):
        sources = sources or ["jalal-sons", "cartpk"]
        return AdminPriceRefresh.objects.create(requested_by=self.operator, sources=sources, results=[
            {"retailer": slug, "outcome": "not_attempted", "run_id": None, "run_status": None,
             "products_collected": 0, "request_count": 0, "error": ""} for slug in sources], **values)

    def client_factory(self, origin):
        source = "cartpk" if origin == "https://www.cartpk.com" else "jalal-sons"
        self.events.append("open:" + source)
        client = MagicMock()
        client.request_count = 2
        client.get_html.side_effect = lambda url: CARTPK_HTML if source == "cartpk" else JALAL_HTML
        client.close.side_effect = lambda: self.events.append("close:" + source)
        return client

    def test_start_requires_post_and_launches_once_after_commit(self):
        self.assertEqual(self.client.get(self.start).status_code, 405)
        with patch("catalog.admin.validate_worker_database"), patch("catalog.admin.launch_refresh") as launch:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.start, {"source": "both"})
            job = AdminPriceRefresh.objects.get()
            self.assertRedirects(response, reverse("admin:catalog_refresh_detail", args=[job.pk]))
            launch.assert_called_once_with(job.pk)
            self.assertEqual(job.sources, ["jalal-sons", "cartpk"])
            self.assertEqual(job.status, "queued")
            self.assertEqual(self.client.post(self.start, {"source": "cartpk"}).status_code, 409)
            self.assertEqual(AdminPriceRefresh.objects.count(), 1)
            launch.assert_called_once()

    def test_database_constraint_blocks_a_second_active_admin_request(self):
        job = self.job()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.job()
        job.status = "success"
        job.save()
        self.assertTrue(self.job().is_active)

    def test_dashboard_reader_can_follow_but_cannot_start_without_explicit_permission(self):
        user = User.objects.create_user("reader", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(content_type__app_label="catalog", codename__in=[
            "view_retailer", "view_product", "view_retailerlisting", "view_scraperun"]))
        job = self.job()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("admin:catalog_refresh_detail", args=[job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:catalog_refresh_status", args=[job.pk])).status_code, 200)
        self.assertEqual(self.client.post(self.start, {"source": "both"}).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="run_price_refresh"))
        self.client.force_login(User.objects.get(pk=user.pk))
        job.status = "success"
        job.save()
        with patch("catalog.admin.validate_worker_database"), patch("catalog.admin.launch_refresh"):
            self.assertEqual(self.client.post(self.start, {"source": "jalal-sons"}).status_code, 302)

    def test_anonymous_nonstaff_missing_permissions_and_csrf_cannot_trigger_collection(self):
        job = self.job()
        detail = reverse("admin:catalog_refresh_detail", args=[job.pk])
        anonymous = Client()
        self.assertEqual(anonymous.get(detail).status_code, 302)
        self.assertEqual(anonymous.post(self.start, {"source": "both"}).status_code, 302)
        self.client.force_login(User.objects.create_user("nonstaff"))
        self.assertEqual(self.client.get(detail).status_code, 302)
        self.client.force_login(User.objects.create_user("staff", is_staff=True))
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(self.client.post(self.start, {"source": "both"}).status_code, 403)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.operator)
        self.assertEqual(protected.post(self.start, {"source": "both"}).status_code, 403)

    def test_invalid_source_and_disabled_or_invalid_contact_do_not_create_jobs(self):
        with patch("catalog.admin.validate_worker_database"), patch("catalog.admin.launch_refresh") as launch:
            self.assertEqual(self.client.post(self.start, {"source": "naheed"}).status_code, 400)
            with override_settings(SCRAPING_ENABLED=False):
                self.assertEqual(self.client.post(self.start, {"source": "both"}).status_code, 400)
            with override_settings(SCRAPER_CONTACT=""):
                self.assertEqual(self.client.post(self.start, {"source": "both"}).status_code, 400)
            launch.assert_not_called()
        self.assertFalse(AdminPriceRefresh.objects.exists())

    def test_source_gates_active_cli_run_cap_and_unreviewed_urls_are_respected(self):
        source = Retailer.objects.get(slug="jalal-sons")
        source.collection_enabled = False
        source.save()
        with self.assertRaises(ValidationError):
            validate_refresh(["jalal-sons"])
        source.collection_enabled = True
        source.save()
        with patch.object(JalalSonsAdapter, "enabled", False), self.assertRaises(ValidationError):
            validate_refresh(["jalal-sons"])
        run = ScrapeRun.objects.create(retailer=source)
        with self.assertRaises(ValidationError):
            validate_refresh(["jalal-sons"])
        run.status = "failed"
        run.save()
        listing = RetailerListing.objects.get(retailer=source, is_demo=False)
        listing.url = "https://www.jalalsons.com.pk/product/nestle-everyday-milk-180ml-2809387"
        listing.save()
        validate_refresh(["jalal-sons"])
        from catalog.management.commands.scrape import Command as ScrapeCommand
        collector = ScrapeCommand(stdout=StringIO())
        collector.reviewed_only = True
        with patch("catalog.management.commands.scrape.PoliteClient") as client:
            call_command(collector, "jalal-sons", refresh_existing=True, stale_only=True, dry_run=True)
        client.assert_not_called()
        listing.url = "https://www.jalalsons.com.pk/product/unreviewed-milk-12345"
        listing.save()
        with self.assertRaisesMessage(ValidationError, "outside the reviewed catalog"):
            validate_refresh(["jalal-sons"])
        with patch("catalog.services.admin_refresh.ScrapeCommand.get_targets", side_effect=CommandError("At most 10 URLs")):
            with self.assertRaisesMessage(ValidationError, "At most 10"):
                validate_refresh(["cartpk"])

    def test_in_memory_database_cannot_launch_a_separate_worker(self):
        with patch("catalog.services.admin_refresh.settings") as configuration:
            configuration.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
            with self.assertRaisesMessage(ValidationError, "file-based"):
                validate_worker_database()

    def test_worker_rechecks_configuration_before_collecting(self):
        job = self.job()
        with override_settings(SCRAPING_ENABLED=False), patch("catalog.management.commands.scrape.PoliteClient") as client:
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertFalse(ScrapeRun.objects.exists())
        client.assert_not_called()

    def test_worker_sequential_progress_exact_run_ownership_and_duplicate_execution(self):
        job = self.job()
        snapshots = []

        def factory(origin):
            stored = AdminPriceRefresh.objects.get(pk=job.pk)
            snapshots.append(deepcopy(stored.results))
            return self.client_factory(origin)

        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            self.assertTrue(run_refresh(job.pk))
            self.assertFalse(run_refresh(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "success")
        self.assertEqual(self.events, ["open:jalal-sons", "close:jalal-sons", "open:cartpk", "close:cartpk"])
        self.assertIsNotNone(snapshots[0][0]["run_id"])
        self.assertEqual(snapshots[1][0]["outcome"], "success")
        self.assertEqual(snapshots[1][0]["products_collected"], 1)
        self.assertEqual(job.results[0]["run_id"], snapshots[0][0]["run_id"])
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 4)
        self.assertEqual(ScrapeRun.objects.count(), 2)
        self.assertIsNotNone(job.worker_pid)
        data = refresh_progress(job)
        self.assertFalse(data["is_active"])
        self.assertEqual(data["sources"][0]["finished_count"], 1)
        self.assertEqual(data["sources"][0]["request_count"], 2)

    def test_fresh_sources_skip_without_requests_runs_or_history(self):
        RetailerListing.objects.filter(is_demo=False).update(last_checked=timezone.now())
        before = PriceHistory.objects.count()
        job = self.job()
        with patch("catalog.management.commands.scrape.PoliteClient") as client:
            run_refresh(job.pk)
        job.refresh_from_db()
        client.assert_not_called()
        self.assertEqual(job.status, "success")
        self.assertEqual([row["outcome"] for row in job.results], ["no_work", "no_work"])
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertEqual(PriceHistory.objects.count(), before)

    def test_denied_source_does_not_retry_and_other_source_can_succeed(self):
        job = self.job()

        def factory(origin):
            client = self.client_factory(origin)
            if origin == "https://www.jalalsons.com.pk":
                client.get_html.side_effect = CollectionError("HTTP 403", code="http_error", http_status=403)
            return client

        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "partial")
        self.assertEqual([row["outcome"] for row in job.results], ["blocked", "success"])
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 3)
        self.assertEqual(len(self.events), 4)

    def test_unexpected_exception_is_sanitized_and_no_new_attempt_is_started(self):
        job = self.job()
        with patch("catalog.services.admin_refresh.call_command", side_effect=RuntimeError("secret-password")):
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertNotIn("secret-password", job.error)
        self.assertFalse(ScrapeRun.objects.exists())

    def test_progress_get_is_read_only_and_error_text_is_escaped(self):
        job = self.job(error='<script>alert("x")</script>')
        before = (ScrapeRun.objects.count(), PriceHistory.objects.count(), list(RetailerListing.objects.values()))
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No network")):
            response = self.client.get(reverse("admin:catalog_refresh_status", args=[job.pk]))
            page = self.client.get(reverse("admin:catalog_refresh_detail", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(page, "&lt;script&gt;")
        self.assertNotContains(page, '<script>alert("x")</script>')
        self.assertEqual(before, (ScrapeRun.objects.count(), PriceHistory.objects.count(), list(RetailerListing.objects.values())))

    def test_unfinalized_owned_run_keeps_job_locked_for_operator_recovery(self):
        job = self.job()

        def fail(command, **kwargs):
            run = ScrapeRun.objects.create(retailer=Retailer.objects.get(slug="jalal-sons"))
            command.results = deepcopy(job.results)
            command.results[0].update(run_id=run.pk, run_status="running", outcome="running")
            command.progress_callback(command.results)
            raise RuntimeError("worker interrupted")

        with patch("catalog.services.admin_refresh.call_command", side_effect=fail):
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertTrue(job.is_active)
        self.assertTrue(refresh_progress(job)["needs_attention"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.job()

    def test_launch_failure_finalizes_queued_job_without_collection(self):
        job = self.job()
        with patch("catalog.services.admin_refresh.subprocess.Popen", side_effect=OSError("sensitive details")):
            launch_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertNotIn("sensitive details", job.error)

    def test_launch_uses_argument_list_current_settings_and_no_visible_console(self):
        job = self.job()
        with patch("catalog.services.admin_refresh.subprocess.Popen") as launch, patch("catalog.services.admin_refresh.threading.Thread") as thread:
            launch_refresh(job.pk)
        args, kwargs = launch.call_args
        self.assertEqual(args[0][-2:], ["run_admin_refresh", str(job.pk)])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["env"]["DJANGO_SETTINGS_MODULE"], "config.ci")
        self.assertEqual(kwargs["stdin"], -3)  # subprocess.DEVNULL
        thread.return_value.start.assert_called_once()

    def test_stopped_worker_recovery_requires_confirmation_and_only_finalizes_owned_runs(self):
        job = self.job(status="running")
        own = ScrapeRun.objects.create(retailer=Retailer.objects.get(slug="jalal-sons"), products_collected=1)
        other = ScrapeRun.objects.create(retailer=Retailer.objects.get(slug="cartpk"))
        job.results[0].update(run_id=own.pk, outcome="running")
        job.save()
        before = PriceHistory.objects.count()
        with self.assertRaises(CommandError):
            call_command("recover_admin_refresh", job.pk, stdout=StringIO())
        call_command("recover_admin_refresh", job.pk, confirm_worker_stopped=True, stdout=StringIO())
        own.refresh_from_db()
        other.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual((job.status, own.status, other.status), ("stopped", "partial", "running"))
        self.assertEqual(before, PriceHistory.objects.count())
        with self.assertRaises(CommandError):
            call_command("recover_admin_refresh", job.pk, confirm_worker_stopped=True, stdout=StringIO())
