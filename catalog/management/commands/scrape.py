import json
import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import Category, Retailer, RetailerListing, ScrapeRun
from catalog.matching.normalization import identify
from catalog.scraping.adapters import ADAPTERS
from catalog.scraping.batches import BATCHES, reviewed_urls
from catalog.scraping.client import PoliteClient
from catalog.scraping.reviewed import COLLECTION_CATEGORIES, REVIEWED_BY_SOURCE
from catalog.scraping.types import CollectionError
from catalog.services.ingestion import ingest
from catalog.services.catalog_import import missing_import_urls

logger = logging.getLogger("catalog")


class Command(BaseCommand):
    help = "Manually collect up to ten reviewed public product URLs. No scheduling or catalog crawling."
    # Exact records owned by this invocation, also used by the sequential wrapper.
    scrape_run = None
    report_path = None
    progress_callback = None
    reviewed_only = False
    permitted_urls = None

    def publish_progress(self, run):
        if self.progress_callback:
            self.progress_callback(run)

    def add_arguments(self, parser):
        parser.add_argument("retailer", choices=list(ADAPTERS))
        targets = parser.add_mutually_exclusive_group()
        targets.add_argument("--url", action="append", default=[], help="Explicit reviewed URL; repeat up to 10 times.")
        targets.add_argument("--batch", choices=list(BATCHES), help="A saved reviewed URL batch.")
        targets.add_argument("--refresh-existing", action="store_true", help="Refresh this retailer's existing non-demo product URLs.")
        parser.add_argument("--stale-only", action="store_true", help="With --refresh-existing, select observations older than PRICE_STALE_HOURS.")
        parser.add_argument("--missing-only", action="store_true", help="With --batch, import only missing non-demo listings; never refresh existing records.")
        parser.add_argument("--dry-run", action="store_true", help="Validate and list targets without network requests or database writes.")
        parser.add_argument("--report-dir", type=Path, help="Write a JSON report as scrape-<run-id>.json in this directory.")

    def get_targets(self, retailer, options):
        if sum(bool(options[key]) for key in ["url", "batch", "refresh_existing"]) != 1:
            raise CommandError("Choose exactly one of --url, --batch, or --refresh-existing.")
        if options["stale_only"] and not options["refresh_existing"]:
            raise CommandError("--stale-only requires --refresh-existing.")
        if options.get("missing_only") and not options["batch"]:
            raise CommandError("--missing-only requires a saved --batch.")
        if options["batch"]:
            batch = BATCHES[options["batch"]]
            if batch["retailer"] != retailer.slug:
                raise CommandError("This saved batch belongs to a different retailer.")
            urls = batch["urls"]
        elif options["refresh_existing"]:
            listings = RetailerListing.objects.filter(retailer=retailer, is_demo=False, product__is_demo=False).exclude(url="")
            if options["stale_only"]:
                listings = listings.filter(last_checked__lt=timezone.now() - timedelta(hours=settings.PRICE_STALE_HOURS))
            urls = list(listings.order_by("last_checked", "pk").values_list("url", flat=True))
        else:
            urls = options["url"]
        urls = list(dict.fromkeys(urls))
        if self.permitted_urls is not None:
            urls = [url for url in urls if url in self.permitted_urls]
        if options.get("missing_only"):
            urls = missing_import_urls(retailer, urls)
        if len(urls) > 10:
            raise CommandError("At most 10 distinct URLs may be collected in one manual run; select a smaller batch.")
        return urls

    def save_report(self, run, directory):
        if directory is None:
            return
        path = directory / f"scrape-{run.pk}.json"
        data = {
            "run_id": run.pk, "retailer": run.retailer.slug, "status": run.status,
            "started_at": run.started_at.isoformat(), "completed_at": run.completed_at.isoformat(),
            "products_collected": run.products_collected, "request_count": run.request_count,
            "error_code": run.error_code, "error": run.error, "results": run.results,
        }
        try:
            with path.open("x", encoding="utf-8") as report:
                json.dump(data, report, indent=2, ensure_ascii=False)
                report.write("\n")
        except OSError as exc:
            raise CommandError(f"Run #{run.pk} is saved in the database, but its JSON report could not be written ({type(exc).__name__}).") from exc
        self.report_path = path
        self.stdout.write(f"Report: {path}")

    def handle(self, *args, **options):
        self.scrape_run = None
        self.report_path = None
        try:
            retailer = Retailer.objects.get(slug=options["retailer"])
        except Retailer.DoesNotExist:
            raise CommandError("Retailer is not configured. Run python manage.py seed_retailers first.") from None
        urls = self.get_targets(retailer, options)
        adapter = ADAPTERS[retailer.slug]()
        if self.reviewed_only:
            for url in urls:
                try:
                    adapter.validate_url(url)
                except CollectionError as exc:
                    raise CommandError(str(exc)) from None
                if url not in reviewed_urls(retailer.slug):
                    raise CommandError("Admin refresh supports only the saved reviewed product URLs.")
        if options["dry_run"]:
            if options["report_dir"]:
                raise CommandError("--report-dir cannot be used with --dry-run.")
            if not adapter.enabled:
                raise CommandError(adapter.reason)
            for url in urls:
                try:
                    adapter.validate_url(url)
                except CollectionError as exc:
                    raise CommandError(str(exc)) from exc
                self.stdout.write(url)
            self.stdout.write(f"Dry run: {len(urls)} URL(s); no requests or observations created.")
            return
        if not urls:
            self.stdout.write("No matching URLs to refresh; no requests or observations created.")
            return
        if options["report_dir"]:
            try:
                options["report_dir"].mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise CommandError(f"Cannot prepare report directory ({type(exc).__name__}).") from exc
        try:
            with transaction.atomic():
                run = ScrapeRun.objects.create(retailer=retailer, results=[{"url": url, "status": "pending"} for url in urls])
        except IntegrityError as exc:
            active = ScrapeRun.objects.filter(retailer=retailer, status="running").first()
            if active is None:
                raise
            raise CommandError(f"Run #{active.pk} is already running for {retailer.name}. Inspect it before starting another collection.") from exc
        self.scrape_run = run
        client = None
        failure = None
        current_result = None
        try:
            self.publish_progress(run)
            if not adapter.enabled:
                raise CollectionError(adapter.reason, code="source_unavailable")
            if not settings.SCRAPING_ENABLED or not retailer.collection_enabled or retailer.status != "enabled":
                raise CollectionError("Collection is disabled. Source review and explicit configuration are required.", code="configuration")
            for url in urls:
                adapter.validate_url(url)
            client = PoliteClient(retailer.website)
            for result in run.results:
                current_result = result
                if options.get("missing_only") and not missing_import_urls(retailer, [result["url"]]):
                    result.update(status="skipped_existing")
                    run.save(update_fields=["results"])
                    self.publish_progress(run)
                    continue
                try:
                    item = adapter.collect(client, result["url"])
                except CollectionError as exc:
                    result.update(status="failed", error_code=exc.code, error=str(exc), http_status=exc.http_status)
                    raise
                # Classification comes from reviewed URL metadata; no broad pantry keyword guesses.
                profile = REVIEWED_BY_SOURCE.get(retailer.slug, {}).get(urlparse(item.url).path)
                category_slug = profile["category"] if profile else "dairy" if {"milk", "milkpak"} & set(identify(item.title).name.split()) else None
                category = None
                if category_slug:
                    name, icon = COLLECTION_CATEGORIES[category_slug]
                    category, _ = Category.objects.get_or_create(slug=category_slug, defaults={"name": name, "icon": icon})
                listing, created = ingest(retailer, item, category=category,
                                    illustration=profile["illustration"] if profile else None,
                                    create_only=options.get("missing_only", False))
                if options.get("missing_only") and not created:
                    result.update(status="skipped_existing", listing_id=listing.pk)
                    run.save(update_fields=["results"])
                    self.publish_progress(run)
                    continue
                run.products_collected += 1
                result.update(status="stored", listing_id=listing.pk, price=str(listing.current_price), checked_at=listing.last_checked.isoformat())
                count = getattr(client, "request_count", 0)
                run.request_count = count if isinstance(count, int) else 0
                run.save(update_fields=["results", "products_collected", "request_count"])
                self.publish_progress(run)
                self.stdout.write(f"{listing.original_title} | PKR {listing.current_price:.2f} | {listing.availability} | {listing.url}")
            run.status = ScrapeRun.Status.SUCCESS
        except CollectionError as exc:
            blocked = exc.code in {"source_unavailable", "configuration", "robots_disallowed", "robots_unverified", "http_error", "access_challenge", "invalid_input"}
            run.status = ScrapeRun.Status.PARTIAL if run.products_collected else ScrapeRun.Status.BLOCKED if blocked else ScrapeRun.Status.FAILED
            run.error = str(exc)
            run.error_code = exc.code
            failure = str(exc)
        except Exception as exc:
            run.status = ScrapeRun.Status.PARTIAL if run.products_collected else ScrapeRun.Status.FAILED
            run.error = f"{type(exc).__name__}: collection failed; inspect local logs."
            run.error_code = "internal_error"
            if current_result is not None and current_result["status"] == "pending":
                current_result.update(status="failed", error_code=run.error_code, error=run.error)
            logger.exception("Retailer collection failed: %s", retailer.slug)
            failure = run.error
        except KeyboardInterrupt:
            run.status = ScrapeRun.Status.PARTIAL if run.products_collected else ScrapeRun.Status.FAILED
            run.error_code, run.error = "interrupted", "Collection interrupted by operator."
            raise
        finally:
            if client:
                count = getattr(client, "request_count", 0)
                run.request_count = count if isinstance(count, int) else 0
                client.close()
            run.completed_at = timezone.now()
            run.save()
            self.publish_progress(run)
        self.save_report(run, options["report_dir"])
        if failure:
            raise CommandError(f"Run #{run.pk} ({run.status}, {run.error_code}): {failure}")
        self.stdout.write(self.style.SUCCESS(f"Run #{run.pk}: stored {run.products_collected} observations in {run.request_count} HTTP request(s)."))
