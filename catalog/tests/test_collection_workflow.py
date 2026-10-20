import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from catalog.models import PriceHistory, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import JalalSonsAdapter
from catalog.scraping.client import PoliteClient
from catalog.scraping.types import CollectionError
from catalog.services.ingestion import ingest

URL = "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398"
HTML = (Path(__file__).parent / "fixtures" / "jalal_milk.html").read_text(encoding="utf-8")


@override_settings(SCRAPER_CONTACT="test@example.com", SCRAPER_DELAY_SECONDS=5,
                   SCRAPER_TIMEOUT_RETRIES=1, SCRAPER_RETRY_DELAY_SECONDS=10,
                   SCRAPER_CONNECT_TIMEOUT=10, SCRAPER_READ_TIMEOUT=20)
class TimeoutRecoveryTests(SimpleTestCase):
    def response(self, body=HTML):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.headers = {"Content-Type": "text/html"}
        response.encoding = "utf-8"
        response.iter_content.return_value = [body.encode()]
        return response

    def test_timeout_recovery_is_bounded_delayed_and_keeps_identity(self):
        for error in [requests.ConnectTimeout, requests.ReadTimeout]:
            with self.subTest(error=error):
                client = PoliteClient("https://www.jalalsons.com.pk")
                identity = client.session.headers["User-Agent"]
                with patch.object(client.session, "get", side_effect=[error(), self.response()]) as get, \
                     patch("catalog.scraping.client.time.monotonic", return_value=100), \
                     patch("catalog.scraping.client.time.sleep") as sleep:
                    self.assertEqual(client._request(URL)[0], HTML)
                self.assertEqual(get.call_count, 2)
                self.assertEqual(client.request_count, 2)
                sleep.assert_called_once_with(10)
                self.assertEqual(client.session.headers["User-Agent"], identity)
                self.assertEqual(get.call_args.kwargs["timeout"], (10, 20))
                self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_exhausted_robot_timeout_never_requests_product_page(self):
        client = PoliteClient("https://www.jalalsons.com.pk")
        with patch.object(client.session, "get", side_effect=requests.ConnectTimeout) as get, \
             patch("catalog.scraping.client.time.sleep"), self.assertRaises(CollectionError) as caught:
            client.get_html(URL)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertIn("/robots.txt", str(caught.exception))
        self.assertEqual(get.call_count, 2)
        self.assertTrue(all(call.args[0].endswith("/robots.txt") for call in get.call_args_list))

    def test_retry_delay_starts_after_a_slow_timeout(self):
        client = PoliteClient("https://www.jalalsons.com.pk")
        with patch.object(client.session, "get", side_effect=[requests.ConnectTimeout(), self.response()]), \
             patch("catalog.scraping.client.time.monotonic", side_effect=[0, 25, 35]), \
             patch("catalog.scraping.client.time.sleep") as sleep:
            client._request(URL)
        sleep.assert_called_once_with(10)

    def test_http_errors_and_challenges_never_retry(self):
        for status in [301, 403, 429, 500, 503]:
            with self.subTest(status=status):
                client = PoliteClient("https://www.jalalsons.com.pk")
                response = self.response()
                response.status_code = status
                with patch.object(client.session, "get", return_value=response) as get, self.assertRaises(CollectionError) as caught:
                    client._request(URL)
                self.assertEqual(caught.exception.code, "http_error")
                self.assertEqual(caught.exception.http_status, status)
                get.assert_called_once()
        client = PoliteClient("https://www.jalalsons.com.pk")
        with patch.object(client.session, "get", return_value=self.response("Verify you are human")) as get, self.assertRaises(CollectionError) as caught:
            client._request(URL)
        self.assertEqual(caught.exception.code, "access_challenge")
        get.assert_called_once()

    def test_connection_and_certificate_errors_are_not_retried(self):
        for error in [requests.ConnectionError, requests.exceptions.SSLError]:
            with self.subTest(error=error):
                client = PoliteClient("https://www.jalalsons.com.pk")
                with patch.object(client.session, "get", side_effect=error) as get, self.assertRaises(CollectionError) as caught:
                    client._request(URL)
                self.assertEqual(caught.exception.code, "network_error")
                get.assert_called_once()


@override_settings(SCRAPING_ENABLED=True)
class CollectionWorkflowTests(TestCase):
    def setUp(self):
        call_command("seed_retailers", stdout=StringIO())
        self.retailer = Retailer.objects.get(slug="jalal-sons")
        self.retailer.status, self.retailer.collection_enabled = "enabled", True
        self.retailer.save()

    def item(self):
        client = MagicMock()
        client.get_html.return_value = HTML
        return JalalSonsAdapter().collect(client, URL)

    @override_settings(SCRAPING_ENABLED=False)
    def test_saved_batch_dry_run_never_writes_or_makes_requests(self):
        output = StringIO()
        with patch("requests.Session.get") as get:
            call_command("scrape", "jalal-sons", batch="jalal-sons-basics", dry_run=True, stdout=output)
        get.assert_not_called()
        self.assertIn("Dry run: 3 URL(s)", output.getvalue())
        self.assertEqual(ScrapeRun.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    def test_all_targets_are_validated_before_any_fetch(self):
        with patch("requests.Session.get") as get, self.assertRaises(CommandError):
            call_command("scrape", "jalal-sons", url=[URL, "https://evil.test/product/milk-123"], stdout=StringIO())
        get.assert_not_called()
        run = ScrapeRun.objects.get()
        self.assertEqual(run.error_code, "invalid_input")
        self.assertEqual(run.request_count, 0)
        self.assertTrue(all(result["status"] == "pending" for result in run.results))

    def test_refresh_only_selects_stale_real_listings_then_becomes_noop(self):
        live, _ = ingest(self.retailer, self.item())
        demo, _ = ingest(self.retailer, self.item(), is_demo=True)
        past = timezone.now() - timedelta(days=3)
        RetailerListing.objects.update(last_checked=past)
        with patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.return_value = HTML
            call_command("scrape", "jalal-sons", refresh_existing=True, stale_only=True, stdout=StringIO())
            client_class.return_value.get_html.assert_called_once_with(URL)
        live.refresh_from_db()
        demo.refresh_from_db()
        self.assertFalse(live.is_stale)
        self.assertEqual(demo.last_checked, past)
        self.assertEqual(live.history.count(), 2)
        self.assertEqual(demo.history.count(), 1)
        with patch("requests.Session.get") as get:
            call_command("scrape", "jalal-sons", refresh_existing=True, stale_only=True, stdout=StringIO())
        get.assert_not_called()
        self.assertEqual(ScrapeRun.objects.count(), 1)
        self.assertEqual(PriceHistory.objects.count(), 3)

    def test_active_run_prevents_overlap(self):
        active = ScrapeRun.objects.create(retailer=self.retailer)
        with patch("requests.Session.get") as get, self.assertRaisesMessage(CommandError, f"Run #{active.pk} is already running"):
            call_command("scrape", "jalal-sons", url=[URL])
        get.assert_not_called()
        self.assertEqual(ScrapeRun.objects.count(), 1)

    def test_successful_report_contains_url_outcome_and_request_count(self):
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.return_value = HTML
            client_class.return_value.request_count = 2
            call_command("scrape", "jalal-sons", url=[URL], report_dir=Path(directory), stdout=StringIO())
            run = ScrapeRun.objects.get()
            report = json.loads((Path(directory) / f"scrape-{run.pk}.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["request_count"], 2)
        self.assertEqual(report["results"][0]["status"], "stored")
        self.assertEqual(report["results"][0]["url"], URL)
        self.assertEqual(report["results"][0]["price"], "350.00")
        self.assertEqual(run.results, report["results"])

    def test_timeout_report_records_failed_and_unattempted_urls(self):
        second = "https://www.jalalsons.com.pk/product/other-product-123"
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.side_effect = CollectionError("ConnectTimeout on /robots.txt", code="timeout")
            client_class.return_value.request_count = 2
            with self.assertRaises(CommandError):
                call_command("scrape", "jalal-sons", url=[URL, second], report_dir=Path(directory), stdout=StringIO())
            run = ScrapeRun.objects.get()
            report = json.loads((Path(directory) / f"scrape-{run.pk}.json").read_text(encoding="utf-8"))
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "timeout")
        self.assertEqual([result["status"] for result in report["results"]], ["failed", "pending"])
        self.assertEqual(PriceHistory.objects.count(), 0)

    def test_report_export_never_overwrites_existing_file(self):
        from catalog.management.commands.scrape import Command
        run = ScrapeRun.objects.create(retailer=self.retailer, status="success", completed_at=timezone.now())
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"scrape-{run.pk}.json"
            path.write_text("existing report", encoding="utf-8")
            with self.assertRaises(CommandError):
                Command(stdout=StringIO()).save_report(run, Path(directory))
            self.assertEqual(path.read_text(encoding="utf-8"), "existing report")

    def test_invalid_selection_and_wrong_source_batch_are_rejected(self):
        for args in [{}, {"url": [URL], "batch": "jalal-sons-basics"}, {"url": [URL], "stale_only": True}]:
            with self.subTest(args=args), self.assertRaises(CommandError):
                call_command("scrape", "jalal-sons", stdout=StringIO(), **args)
        with self.assertRaises(CommandError):
            call_command("scrape", "naheed", batch="jalal-sons-basics", stdout=StringIO())
        self.assertEqual(ScrapeRun.objects.count(), 0)

    def test_parser_failure_does_not_change_existing_price_or_check_time(self):
        listing, _ = ingest(self.retailer, self.item())
        before = (listing.current_price, listing.last_checked, listing.history.count())
        with patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.return_value = "<html><h1>New source layout</h1></html>"
            with self.assertRaises(CommandError):
                call_command("scrape", "jalal-sons", url=[URL], stdout=StringIO())
        listing.refresh_from_db()
        self.assertEqual((listing.current_price, listing.last_checked, listing.history.count()), before)
        run = ScrapeRun.objects.get()
        self.assertEqual(run.error_code, "parse_error")
        self.assertEqual(run.results[0]["status"], "failed")
