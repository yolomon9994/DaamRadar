import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.management.commands.refresh_prices import Command
from catalog.management.commands.scrape import Command as ScrapeCommand
from catalog.models import PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import CartpkAdapter, JalalSonsAdapter
from catalog.scraping.types import CollectionError
from catalog.services.ingestion import ingest

FIXTURES = Path(__file__).parent / "fixtures"
JALAL_URL = "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398"
CARTPK_URL = "https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr"
JALAL_HTML = (FIXTURES / "jalal_milk.html").read_text(encoding="utf-8")
CARTPK_HTML = (FIXTURES / "cartpk_milk.html").read_text(encoding="utf-8")


@override_settings(SCRAPING_ENABLED=True)
class RefreshPricesTests(TestCase):
    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        Retailer.objects.filter(slug__in=("jalal-sons", "cartpk")).update(status="enabled", collection_enabled=True)
        self.listings = {}
        for slug, adapter, url, html in (("jalal-sons", JalalSonsAdapter(), JALAL_URL, JALAL_HTML),
                                          ("cartpk", CartpkAdapter(), CARTPK_URL, CARTPK_HTML)):
            client = MagicMock()
            client.get_html.return_value = html
            self.listings[slug], _ = ingest(Retailer.objects.get(slug=slug), adapter.collect(client, url))
        self.past = timezone.now() - timedelta(days=3)
        RetailerListing.objects.filter(is_demo=False).update(last_checked=self.past)
        self.clients = {}
        self.events = []

    def client_factory(self, origin):
        slug = "cartpk" if origin == "https://www.cartpk.com" else "jalal-sons"
        self.events.append(f"start:{slug}")
        client = MagicMock()
        client.request_count = 2
        html = CARTPK_HTML if slug == "cartpk" else JALAL_HTML

        def fetch(url):
            self.events.append(f"fetch:{slug}")
            return html

        client.get_html.side_effect = fetch
        client.close.side_effect = lambda: self.events.append(f"close:{slug}")
        self.clients[slug] = client
        return client

    def invoke(self, **kwargs):
        output, errors = StringIO(), StringIO()
        command = Command(stdout=output, stderr=errors)
        call_command(command, **kwargs)
        return command, output.getvalue(), errors.getvalue()

    def test_sequential_refresh_keeps_exact_run_ids_and_separate_reports(self):
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            command, output, errors = self.invoke(report_dir=Path(directory))
            self.assertEqual(self.events, ["start:jalal-sons", "fetch:jalal-sons", "close:jalal-sons",
                                           "start:cartpk", "fetch:cartpk", "close:cartpk"])
            self.assertEqual([row["retailer"] for row in command.results], ["jalal-sons", "cartpk"])
            for row in command.results:
                run = ScrapeRun.objects.get(pk=row["run_id"])
                self.assertEqual(run.retailer.slug, row["retailer"])
                self.assertEqual((row["outcome"], row["products_collected"], row["request_count"]), ("success", 1, 2))
                report = json.loads(Path(row["report_path"]).read_text(encoding="utf-8"))
                self.assertEqual(report["run_id"], run.pk)
                self.assertEqual(report["results"], run.results)
                self.assertEqual(run.status, "success")
        self.assertIn("Total: 2 observations, 4 HTTP requests, 0 retailer errors.", output)
        self.assertEqual(errors, "")
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 2)
        self.assertEqual(Product.objects.filter(is_demo=False).count(), 1)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 4)
        self.assertEqual(Product.objects.filter(is_demo=True).count(), 12)
        for listing in self.listings.values():
            listing.refresh_from_db()
            self.assertFalse(listing.is_stale)

    def test_second_refresh_is_a_true_noop_without_new_audits_or_network(self):
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            self.invoke()
        before = (ScrapeRun.objects.count(), PriceHistory.objects.count())
        with patch("requests.Session.get") as get, patch("catalog.management.commands.scrape.PoliteClient") as factory:
            command, output, errors = self.invoke()
        factory.assert_not_called()
        get.assert_not_called()
        self.assertEqual([row["outcome"] for row in command.results], ["no_work", "no_work"])
        self.assertTrue(all(row["run_id"] is None and row["report_path"] is None for row in command.results))
        self.assertEqual(before, (ScrapeRun.objects.count(), PriceHistory.objects.count()))
        self.assertIn("Total: 0 observations, 0 HTTP requests, 0 retailer errors.", output)

    def test_mixed_freshness_skips_only_the_fresh_source(self):
        RetailerListing.objects.filter(pk=self.listings["jalal-sons"].pk).update(last_checked=timezone.now())
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            command, _, _ = self.invoke()
        self.assertEqual(self.events, ["start:cartpk", "fetch:cartpk", "close:cartpk"])
        self.assertEqual(command.results[0]["outcome"], "no_work")
        self.assertEqual(command.results[1]["outcome"], "success")
        self.assertEqual(ScrapeRun.objects.count(), 1)

    @override_settings(SCRAPING_ENABLED=False)
    def test_dry_run_lists_stale_targets_without_configuration_or_any_writes(self):
        before = (ScrapeRun.objects.count(), PriceHistory.objects.count())
        with patch("requests.Session.get") as get, patch("catalog.management.commands.scrape.PoliteClient") as factory:
            command, output, _ = self.invoke(dry_run=True)
        get.assert_not_called()
        factory.assert_not_called()
        self.assertIn(JALAL_URL, output)
        self.assertIn(CARTPK_URL, output)
        self.assertEqual([row["outcome"] for row in command.results], ["dry_run", "dry_run"])
        self.assertEqual(before, (ScrapeRun.objects.count(), PriceHistory.objects.count()))

    def test_dry_run_and_report_directory_are_rejected_before_any_action(self):
        with TemporaryDirectory() as directory, patch("requests.Session.get") as get:
            target = Path(directory) / "not-created"
            with self.assertRaisesMessage(CommandError, "--report-dir cannot be used with --dry-run"):
                self.invoke(dry_run=True, report_dir=target)
            self.assertFalse(target.exists())
        get.assert_not_called()
        self.assertEqual(ScrapeRun.objects.count(), 0)

    def test_access_denial_never_retries_but_second_source_still_refreshes(self):
        def factory(origin):
            client = self.client_factory(origin)
            if "jalalsons" in origin:
                client.get_html.side_effect = CollectionError("HTTP 403", code="http_error", http_status=403)
            return client

        output, errors = StringIO(), StringIO()
        command = Command(stdout=output, stderr=errors)
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            with self.assertRaisesMessage(CommandError, "retailer errors"):
                call_command(command, report_dir=Path(directory))
            for row in command.results:
                self.assertTrue(Path(row["report_path"]).is_file())
        self.assertEqual([row["outcome"] for row in command.results], ["blocked", "success"])
        self.clients["jalal-sons"].get_html.assert_called_once_with(JALAL_URL)
        self.clients["cartpk"].get_html.assert_called_once_with(CARTPK_URL)
        self.listings["jalal-sons"].refresh_from_db()
        self.assertEqual(self.listings["jalal-sons"].last_checked, self.past)
        self.assertEqual(self.listings["jalal-sons"].history.count(), 1)
        self.assertIn("HTTP 403", errors.getvalue())
        self.assertIn("1 retailer errors", output.getvalue())

    def test_partial_results_and_other_source_success_survive(self):
        url = "https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399"
        html = (FIXTURES / "jalal_olpers_1500.html").read_text(encoding="utf-8")
        client = MagicMock()
        client.get_html.return_value = html
        second, _ = ingest(Retailer.objects.get(slug="jalal-sons"), JalalSonsAdapter().collect(client, url))
        RetailerListing.objects.filter(pk=second.pk).update(last_checked=self.past + timedelta(seconds=1))

        def factory(origin):
            client = self.client_factory(origin)
            if "jalalsons" in origin:
                client.get_html.side_effect = [JALAL_HTML, CollectionError("Timeout", code="timeout")]
                client.request_count = 4  # robots, successful page, two timeout attempts
            return client

        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory), self.assertRaises(CommandError):
            call_command(command)
        self.assertEqual([row["outcome"] for row in command.results], ["partial", "success"])
        self.assertEqual(sum(row["products_collected"] for row in command.results), 2)
        self.assertEqual(second.history.count(), 1)
        self.assertEqual(self.listings["jalal-sons"].history.count(), 2)
        self.assertEqual(self.listings["cartpk"].history.count(), 2)

    def test_existing_running_run_is_not_attributed_to_the_wrapper(self):
        active = ScrapeRun.objects.create(retailer=Retailer.objects.get(slug="jalal-sons"))
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory), self.assertRaises(CommandError):
            call_command(command)
        self.assertEqual(command.results[0]["outcome"], "error")
        self.assertIsNone(command.results[0]["run_id"])
        self.assertIsNone(command.results[0]["report_path"])
        self.assertIn(f"Run #{active.pk} is already running", command.results[0]["error"])
        self.assertEqual(command.results[1]["outcome"], "success")
        active.refresh_from_db()
        self.assertEqual(active.status, "running")
        self.assertEqual(set(self.clients), {"cartpk"})

    @override_settings(SCRAPING_ENABLED=False)
    def test_global_gate_is_preserved_and_errors_exit_nonzero(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("catalog.management.commands.scrape.PoliteClient") as factory, self.assertRaises(CommandError):
            call_command(command)
        factory.assert_not_called()
        self.assertEqual([row["outcome"] for row in command.results], ["blocked", "blocked"])
        self.assertEqual(ScrapeRun.objects.filter(error_code="configuration").count(), 2)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 2)

    def test_code_level_disabled_adapter_is_not_bypassed(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch.object(CartpkAdapter, "enabled", False), \
             patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory), self.assertRaises(CommandError):
            call_command(command)
        self.assertEqual(command.results[0]["outcome"], "success")
        self.assertEqual(command.results[1]["outcome"], "blocked")
        self.assertEqual(set(self.clients), {"jalal-sons"})

    def test_source_flags_are_not_enabled_by_the_wrapper(self):
        source = Retailer.objects.get(slug="cartpk")
        for status, enabled in (("enabled", False), ("pending", True)):
            source.status, source.collection_enabled = status, enabled
            source.save()
            command = Command(stdout=StringIO(), stderr=StringIO())
            with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory), self.assertRaises(CommandError):
                call_command(command)
            self.assertEqual(command.results[1]["outcome"], "blocked")
            source.refresh_from_db()
            self.assertEqual((source.status, source.collection_enabled), (status, enabled))
        self.assertNotIn("cartpk", self.clients)

    def test_ten_url_limit_is_preserved_and_other_retailer_can_continue(self):
        listing = self.listings["jalal-sons"]
        RetailerListing.objects.bulk_create([
            RetailerListing(product=listing.product, retailer=listing.retailer, external_id=f"extra-{index}",
                original_title="Reviewed test listing", current_price="350", last_checked=self.past,
                url=f"https://www.jalalsons.com.pk/product/example-{index}")
            for index in range(10)
        ])
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory), self.assertRaises(CommandError):
            call_command(command)
        self.assertEqual(command.results[0]["outcome"], "error")
        self.assertIsNone(command.results[0]["run_id"])
        self.assertIn("At most 10", command.results[0]["error"])
        self.assertEqual(command.results[1]["outcome"], "success")
        self.assertEqual(set(self.clients), {"cartpk"})

    def test_interrupt_saves_audit_and_report_and_stops_before_second_source(self):
        def factory(origin):
            client = self.client_factory(origin)
            client.get_html.side_effect = KeyboardInterrupt
            return client

        command = Command(stdout=StringIO(), stderr=StringIO())
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient", side_effect=factory):
            with self.assertRaises(CommandError) as caught:
                call_command(command, report_dir=Path(directory))
            self.assertEqual(caught.exception.returncode, 130)
            self.assertEqual([row["outcome"] for row in command.results], ["interrupted", "not_attempted"])
            report = json.loads(Path(command.results[0]["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["error_code"], "interrupted")
            self.assertEqual(report["status"], "failed")
        self.assertEqual(set(self.clients), {"jalal-sons"})
        self.assertEqual(ScrapeRun.objects.count(), 1)
        self.assertFalse(ScrapeRun.objects.filter(status="running").exists())

    def test_report_export_failure_is_not_misreported_as_collection_failure_or_retried(self):
        original = ScrapeCommand.save_report

        def export(collector, run, directory):
            if run.retailer.slug == "jalal-sons":
                raise CommandError("Run is saved, but its JSON report could not be written.")
            return original(collector, run, directory)

        command = Command(stdout=StringIO(), stderr=StringIO())
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory), \
             patch.object(ScrapeCommand, "save_report", export), self.assertRaises(CommandError):
            call_command(command, report_dir=Path(directory))
        self.assertEqual([row["outcome"] for row in command.results], ["report_error", "success"])
        self.assertEqual(command.results[0]["run_status"], "success")
        self.assertIsNone(command.results[0]["report_path"])
        self.assertEqual(ScrapeRun.objects.filter(status="success").count(), 2)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 4)

    def test_reused_single_source_command_does_not_retain_a_previous_run_reference(self):
        collector = ScrapeCommand(stdout=StringIO())
        with TemporaryDirectory() as directory, patch("catalog.management.commands.scrape.PoliteClient", side_effect=self.client_factory):
            call_command(collector, "jalal-sons", refresh_existing=True, stale_only=True, report_dir=Path(directory))
            self.assertIsNotNone(collector.scrape_run)
            self.assertIsNotNone(collector.report_path)
            call_command(collector, "jalal-sons", refresh_existing=True, stale_only=True)
        self.assertIsNone(collector.scrape_run)
        self.assertIsNone(collector.report_path)

    def test_unexpected_preflight_error_prints_summary_and_propagates_without_starting_other_source(self):
        output = StringIO()
        command = Command(stdout=output, stderr=StringIO())
        with patch("catalog.management.commands.refresh_prices.call_command", side_effect=RuntimeError("Unexpected database failure")) as child:
            with self.assertRaises(RuntimeError):
                call_command(command)
        child.assert_called_once()
        self.assertEqual(command.results[1]["outcome"], "not_attempted")
        self.assertIn("Refresh summary", output.getvalue())


class EmptyRefreshPricesTests(TestCase):
    def test_missing_source_records_are_errors_without_seeding(self):
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("requests.Session.get") as get, self.assertRaises(CommandError):
            call_command(command)
        get.assert_not_called()
        self.assertEqual([row["outcome"] for row in command.results], ["error", "error"])
        self.assertFalse(Retailer.objects.exists())
        self.assertFalse(ScrapeRun.objects.exists())

    def test_empty_configured_catalog_is_no_work_without_first_time_imports(self):
        call_command("seed_retailers", stdout=StringIO())
        command = Command(stdout=StringIO(), stderr=StringIO())
        with patch("requests.Session.get") as get:
            call_command(command)
        get.assert_not_called()
        self.assertEqual([row["outcome"] for row in command.results], ["no_work", "no_work"])
        self.assertFalse(ScrapeRun.objects.exists())
        self.assertFalse(RetailerListing.objects.exists())
