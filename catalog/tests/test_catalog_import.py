from dataclasses import replace
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Permission, User
from django.core import signing
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import AdminPriceRefresh, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import JalalSonsAdapter
from catalog.scraping.batches import BATCHES
from catalog.scraping.types import CollectionError
from catalog.services.admin_refresh import run_refresh, refresh_progress
from catalog.services.catalog_import import plan_import
from catalog.services.ingestion import ingest

BATCH = "jalal-sons-milk-comparison"
URLS = BATCHES[BATCH]["urls"]
FIXTURES = Path(__file__).parent / "fixtures"
HTML = dict(zip(URLS, [(FIXTURES / name).read_text(encoding="utf-8") for name in [
    "jalal_milk.html", "jalal_olpers_1500.html", "jalal_milkpak_250.html", "jalal_nurpur_1000.html", "jalal_haleeb_1000.html"]]))


@override_settings(SCRAPING_ENABLED=True, SCRAPER_CONTACT="operator@example.invalid")
class CatalogImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.operator = User.objects.create_superuser("import-operator", password=None)
        Retailer.objects.filter(slug__in=["jalal-sons", "cartpk"]).update(status="enabled", collection_enabled=True)
        cls.retailer = Retailer.objects.get(slug="jalal-sons")

    def setUp(self):
        self.client.force_login(self.operator)
        self.preview_url = reverse("admin:catalog_import_preview")
        self.start_url = reverse("admin:catalog_import_start")
        self.fetched = []

    def item(self, url):
        client = MagicMock()
        client.get_html.return_value = HTML[url]
        return JalalSonsAdapter().collect(client, url)

    def existing(self, url):
        return ingest(self.retailer, self.item(url))[0]

    def preview(self, batch=BATCH):
        response = self.client.get(self.preview_url, {"batch": batch})
        self.assertEqual(response.status_code, 200)
        form = response.context["start_form"]
        return {"batch": batch, "preview_token": form.initial["preview_token"]}

    def job(self, targets=None):
        return AdminPriceRefresh.objects.create(requested_by=self.operator, kind="import", batch=BATCH,
            sources=["jalal-sons"], targets=list(URLS if targets is None else targets), results=[{
                "retailer": "jalal-sons", "outcome": "not_attempted", "run_id": None, "run_status": None,
                "products_collected": 0, "request_count": 0, "error": ""}])

    def client_factory(self, origin):
        self.assertEqual(origin, "https://www.jalalsons.com.pk")
        client = MagicMock()
        client.request_count = 0

        def get(url):
            self.fetched.append(url)
            client.request_count += 1
            return HTML[url]

        client.get_html.side_effect = get
        return client

    def test_fresh_demo_checkout_preview_is_read_only_and_shows_missing_real_listings(self):
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with patch("requests.sessions.Session.send", side_effect=AssertionError("No network")):
            response = self.client.get(self.preview_url, {"batch": BATCH})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.context["plan"]["missing_count"], response.context["plan"]["existing_count"]), (5, 0))
        self.assertContains(response, "Import 5 missing listings")
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))
        self.assertFalse(AdminPriceRefresh.objects.exists())
        self.assertFalse(ScrapeRun.objects.exists())

    def test_existing_stale_unavailable_or_different_area_records_are_skipped_by_url_or_id(self):
        first, second = self.existing(URLS[0]), self.existing(URLS[1])
        RetailerListing.objects.filter(pk=first.pk).update(last_checked=timezone.now() - timedelta(days=5), availability="out_of_stock", delivery_area="Other area")
        RetailerListing.objects.filter(pk=second.pk).update(url="")
        plan = plan_import(BATCH)
        self.assertEqual(plan["missing_urls"], URLS[2:])
        self.assertEqual(plan["existing_count"], 2)

    def test_disabled_or_missing_source_does_not_get_enabled_or_seeded_by_preview(self):
        self.retailer.collection_enabled = False
        self.retailer.save()
        response = self.client.get(self.preview_url, {"batch": BATCH})
        self.assertContains(response, "Collection setup needed")
        self.assertNotContains(response, "data-import-start")
        self.retailer.refresh_from_db()
        self.assertFalse(self.retailer.collection_enabled)
        self.retailer.delete()
        response = self.client.get(self.preview_url, {"batch": BATCH})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["plan"]["missing_count"], 5)
        self.assertFalse(Retailer.objects.filter(slug="jalal-sons").exists())

    def test_preview_permission_does_not_allow_import_and_csrf_still_applies(self):
        reader = User.objects.create_user("import-reader", is_staff=True)
        reader.user_permissions.set(Permission.objects.filter(content_type__app_label="catalog", codename__in=[
            "view_retailer", "view_retailerlisting", "view_product", "view_scraperun", "run_price_refresh"]))
        data = self.preview()
        self.client.force_login(reader)
        self.assertEqual(self.client.get(self.preview_url, {"batch": BATCH}).status_code, 200)
        self.assertEqual(self.client.post(self.start_url, data).status_code, 403)
        anonymous = Client()
        self.assertEqual(anonymous.get(self.preview_url).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.operator)
        self.assertEqual(csrf.post(self.start_url, data).status_code, 403)

    def test_post_after_preview_persists_approved_targets_and_launches_after_commit(self):
        self.existing(URLS[0])
        data = self.preview()
        with patch("catalog.admin.validate_worker_database"), patch("catalog.admin.launch_refresh") as launch:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.start_url, data)
        job = AdminPriceRefresh.objects.get()
        self.assertRedirects(response, reverse("admin:catalog_refresh_detail", args=[job.pk]))
        self.assertEqual((job.kind, job.batch, job.sources, job.targets), ("import", BATCH, ["jalal-sons"], URLS[1:]))
        launch.assert_called_once_with(job.pk)

    def test_unpreviewed_tampered_expired_and_other_account_tokens_are_refused(self):
        data = self.preview()
        for posted in [{"batch": BATCH}, {**data, "preview_token": "tampered"},
                       {**data, "batch": "cartpk-milk-comparison"}]:
            self.assertEqual(self.client.post(self.start_url, posted).status_code, 400)
        with patch("django.core.signing.time.time", return_value=1):
            expired = signing.dumps({"user_id": self.operator.pk, "batch": BATCH, "urls": URLS}, salt="catalog-admin-import")
        self.assertEqual(self.client.post(self.start_url, {"batch": BATCH, "preview_token": expired}).status_code, 400)
        self.client.force_login(User.objects.create_superuser("other-importer", password=None))
        self.assertEqual(self.client.post(self.start_url, data).status_code, 400)
        self.assertFalse(AdminPriceRefresh.objects.exists())
        self.assertEqual(self.client.get(self.start_url).status_code, 405)

    def test_changed_plan_requires_preview_again_and_full_batch_starts_no_job(self):
        data = self.preview()
        self.existing(URLS[0])
        self.assertEqual(self.client.post(self.start_url, data).status_code, 400)
        for url in URLS[1:]:
            self.existing(url)
        response = self.client.get(self.preview_url, {"batch": BATCH})
        self.assertContains(response, "All listings in this batch already exist")
        self.assertNotContains(response, "data-import-start")
        token = response.context["start_form"].initial["preview_token"]
        self.assertEqual(self.client.post(self.start_url, {"batch": BATCH, "preview_token": token}).status_code, 400)
        self.assertFalse(AdminPriceRefresh.objects.exists())

    def test_import_and_refresh_share_the_same_active_request_lock(self):
        data = self.preview()
        active = AdminPriceRefresh.objects.create(requested_by=self.operator, sources=["jalal-sons"])
        with patch("catalog.admin.validate_worker_database"), patch("catalog.admin.launch_refresh") as launch:
            self.assertEqual(self.client.post(self.start_url, data).status_code, 409)
            active.status = "success"
            active.save()
            self.job()
            self.assertEqual(self.client.post(reverse("admin:catalog_refresh_start"), {"source": "both"}).status_code, 409)
        launch.assert_not_called()

    def test_worker_imports_only_approved_missing_records_preserving_existing_history_and_evidence(self):
        existing = self.existing(URLS[0])
        RetailerListing.objects.filter(pk=existing.pk).update(last_checked=timezone.now() - timedelta(days=4),
            availability="unknown", delivery_area="Preserved area", delivery_area_key="preserved-scope",
            area_evidence_url="https://www.jalalsons.com.pk/delivery", area_verified_at=timezone.now())
        before = RetailerListing.objects.values().get(pk=existing.pk)
        history = list(existing.history.values())
        job = self.job(URLS[1:])
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            self.assertTrue(run_refresh(job.pk))
            self.assertFalse(run_refresh(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "success")
        self.assertEqual(self.fetched, URLS[1:])
        self.assertEqual(before, RetailerListing.objects.values().get(pk=existing.pk))
        self.assertEqual(history, list(existing.history.values()))
        self.assertEqual((Product.objects.filter(is_demo=False).count(), RetailerListing.objects.filter(is_demo=False).count()), (5, 5))
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 5)
        self.assertEqual(RetailerListing.objects.filter(is_demo=True).count(), 36)

    def test_worker_rechecks_missing_state_and_does_not_expand_to_newly_missing_urls(self):
        first = self.existing(URLS[0])
        self.existing(URLS[1])
        job = self.job(URLS[2:])
        first.delete()  # Was existing during preview; its URL was never authorized for this job.
        self.existing(URLS[2])  # Arrived after preview; skip it without fetching.
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            run_refresh(job.pk)
        self.assertEqual(self.fetched, URLS[3:])
        self.assertFalse(RetailerListing.objects.filter(url=URLS[0]).exists())

    def test_fully_imported_queued_batch_skips_without_network_audits_or_history(self):
        job = self.job()
        for url in URLS:
            self.existing(url)
        count = PriceHistory.objects.count()
        with patch("catalog.management.commands.scrape.PoliteClient") as client:
            run_refresh(job.pk)
        job.refresh_from_db()
        client.assert_not_called()
        self.assertEqual(job.results[0]["outcome"], "no_work")
        self.assertIn("already imported", refresh_progress(job)["sources"][0]["outcome_label"])
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertEqual(count, PriceHistory.objects.count())

    def test_record_created_during_fetch_is_not_overwritten_or_observed_twice(self):
        job = self.job([URLS[0]])
        preserved = {}

        def factory(origin):
            client = self.client_factory(origin)
            def get(url):
                listing = self.existing(url)
                preserved.update(RetailerListing.objects.values().get(pk=listing.pk))
                return HTML[url]
            client.get_html.side_effect = get
            return client

        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.results[0]["products_collected"], 0)
        run = ScrapeRun.objects.get()
        self.assertEqual(run.results[0]["status"], "skipped_existing")
        self.assertEqual(refresh_progress(job)["sources"][0]["finished_count"], 1)
        self.assertEqual(preserved, RetailerListing.objects.values().get(pk=preserved["id"]))
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 1)

    def test_partial_import_keeps_success_and_later_missing_only_retry_does_not_refresh_it(self):
        job = self.job()
        def factory(origin):
            client = self.client_factory(origin)
            original = client.get_html.side_effect
            client.get_html.side_effect = lambda url: (_ for _ in ()).throw(CollectionError("Stopped", code="http_error")) if url == URLS[1] else original(url)
            return client
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            run_refresh(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "partial")
        first = RetailerListing.objects.values().get(url=URLS[0])
        retry = self.job(URLS[1:])
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            run_refresh(retry.pk)
        self.assertEqual(first, RetailerListing.objects.values().get(url=URLS[0]))
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 5)

    def test_unknown_batch_or_outside_preview_targets_fail_without_requests(self):
        self.assertEqual(self.client.get(self.preview_url, {"batch": "unreviewed"}).status_code, 400)
        job = self.job(["https://www.jalalsons.com.pk/product/unknown-123"])
        with patch("catalog.management.commands.scrape.PoliteClient") as client:
            run_refresh(job.pk)
        client.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertFalse(ScrapeRun.objects.exists())

    def test_create_only_ingestion_returns_existing_listing_across_area_changes(self):
        item = self.item(URLS[0])
        listing = self.existing(URLS[0])
        RetailerListing.objects.filter(pk=listing.pk).update(delivery_area="Different delivery area")
        before = RetailerListing.objects.values().get(pk=listing.pk)
        count = PriceHistory.objects.count()
        returned, created = ingest(self.retailer, item, create_only=True)
        self.assertFalse(created)
        self.assertEqual(returned.pk, listing.pk)
        self.assertEqual(before, RetailerListing.objects.values().get(pk=listing.pk))
        self.assertEqual(count, PriceHistory.objects.count())

    def test_unique_key_race_rolls_back_new_canonical_product_without_changing_existing_listing(self):
        listing = self.existing(URLS[0])
        incoming = replace(self.item(URLS[0]), title="Different Pantry Product 750g", brand="Different")
        before = (Product.objects.count(), PriceHistory.objects.count(), RetailerListing.objects.values().get(pk=listing.pk))
        manager = RetailerListing.objects
        actual_query = manager.select_for_update()
        absent = MagicMock()
        absent.filter.return_value.filter.return_value.first.return_value = None
        with patch.object(manager, "select_for_update", side_effect=[absent, actual_query]), \
                patch.object(manager, "get_or_create", return_value=(listing, False)):
            returned, created = ingest(self.retailer, incoming, create_only=True)
        self.assertFalse(created)
        self.assertEqual(returned.pk, listing.pk)
        self.assertEqual(before, (Product.objects.count(), PriceHistory.objects.count(), RetailerListing.objects.values().get(pk=listing.pk)))
