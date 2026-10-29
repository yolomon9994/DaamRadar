"""One manual, sequential entry point to the existing audited collectors."""
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from .scrape import Command as ScrapeCommand

REVIEWED_RETAILERS = ("jalal-sons", "cartpk")


class Command(BaseCommand):
    help = "Manually refresh stale existing Jalal Sons and Cartpk listings, sequentially. No scheduling or discovery."
    retailer_slugs = REVIEWED_RETAILERS
    progress_callback = None
    reviewed_only = False
    batch_key = None
    import_urls = None

    def publish_progress(self):
        if self.progress_callback:
            self.progress_callback(self.results)

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List stale targets without requests or database writes.")
        parser.add_argument("--report-dir", type=Path, help="Keep each retailer's scrape-<run-id>.json report here.")

    def handle(self, *args, **options):
        if options["dry_run"] and options["report_dir"]:
            raise CommandError("--report-dir cannot be used with --dry-run.")
        self.results = [{"retailer": slug, "outcome": "not_attempted", "run_id": None,
                         "run_status": None, "products_collected": 0, "request_count": 0,
                         "report_path": None, "error": ""} for slug in self.retailer_slugs]
        self.publish_progress()
        interrupted = False
        try:
            for row in self.results:
                self.stdout.write(f"\nRefreshing {row['retailer']} (stale existing listings only)")
                collector = ScrapeCommand(stdout=self.stdout, stderr=self.stderr)
                collector.reviewed_only = self.reviewed_only
                collector.permitted_urls = self.import_urls
                row["outcome"] = "running"
                self.publish_progress()

                def progress(run):
                    row.update(run_id=run.pk, run_status=run.status, products_collected=run.products_collected,
                               request_count=run.request_count)
                    self.publish_progress()

                collector.progress_callback = progress
                try:
                    targets = {"batch": self.batch_key, "missing_only": True} if self.batch_key else {
                        "refresh_existing": True, "stale_only": True}
                    call_command(collector, row["retailer"], **targets,
                                 dry_run=options["dry_run"], report_dir=options["report_dir"],
                                 no_color=options["no_color"], force_color=options["force_color"])
                except CommandError as exc:
                    row["error"] = str(exc)
                except KeyboardInterrupt:
                    interrupted = True
                    row["error"] = "Interrupted by operator; remaining retailers were not attempted."
                    # The collector has already finalized its database run in finally.
                    # Preserve an optional report before stopping, without a new attempt.
                    if collector.scrape_run is not None and options["report_dir"] and collector.report_path is None:
                        try:
                            collector.save_report(collector.scrape_run, options["report_dir"])
                        except CommandError as exc:
                            row["error"] += f" {exc}"
                except Exception:
                    row["error"] = "Unexpected error; inspect the traceback. Remaining retailers were not attempted."
                    raise
                finally:
                    run = collector.scrape_run
                    if run is not None:
                        row.update(run_id=run.pk, run_status=run.status,
                                   products_collected=run.products_collected, request_count=run.request_count)
                    row["report_path"] = str(collector.report_path) if collector.report_path is not None else None
                    if interrupted:
                        row["outcome"] = "interrupted"
                    elif row["error"]:
                        if run is None:
                            row["outcome"] = "error"
                        elif run.status == "success":
                            row["outcome"] = "report_error"
                        else:
                            row["outcome"] = run.status
                    elif run is not None:
                        row["outcome"] = run.status
                    elif options["dry_run"]:
                        row["outcome"] = "dry_run"
                    else:
                        row["outcome"] = "no_work"
                    self.publish_progress()
                if interrupted:
                    break
        finally:
            self.print_summary()
        if interrupted:
            raise CommandError("Refresh interrupted; inspect the summary and saved run before retrying.", returncode=130)
        if any(row["error"] for row in self.results):
            raise CommandError("Refresh finished with retailer errors; inspect the summary and individual run records.")

    def print_summary(self):
        self.stdout.write("\nRefresh summary")
        for row in self.results:
            run = f"run #{row['run_id']} ({row['run_status']})" if row["run_id"] is not None else "no new run"
            self.stdout.write(f"{row['retailer']}: {row['outcome']} | {row['products_collected']} stored | "
                              f"{row['request_count']} HTTP requests | {run}")
            if row["report_path"]:
                self.stdout.write(f"  Report: {row['report_path']}")
            if row["error"]:
                self.stderr.write(f"  {row['retailer']}: {row['error']}")
        self.stdout.write(f"Total: {sum(row['products_collected'] for row in self.results)} observations, "
                          f"{sum(row['request_count'] for row in self.results)} HTTP requests, "
                          f"{sum(bool(row['error']) for row in self.results)} retailer errors.")
