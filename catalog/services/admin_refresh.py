"""Explicit admin requests launch finite local workers, never a scheduler."""
from io import StringIO
import os
import subprocess
import sys
import threading

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.validators import URLValidator, validate_email
from django.db import close_old_connections
from django.utils import timezone

from catalog.management.commands.refresh_prices import Command as RefreshCommand, REVIEWED_RETAILERS
from catalog.management.commands.scrape import Command as ScrapeCommand
from catalog.models import AdminPriceRefresh, Retailer, ScrapeRun
from catalog.scraping.adapters import ADAPTERS
from catalog.scraping.batches import reviewed_urls
from catalog.scraping.types import CollectionError
from catalog.services.collection_health import can_view_collection_health

OUTCOME_LABELS = {
    "not_attempted": "Not attempted", "running": "In progress", "success": "Completed",
    "partial": "Partially completed", "failed": "Failed", "blocked": "Blocked",
    "no_work": "Skipped — fresh or empty", "error": "Could not start", "report_error": "Report export failed",
    "interrupted": "Interrupted", "stopped": "Stopped",
}


def can_start_refresh(user):
    return can_view_collection_health(user) and user.has_perm("catalog.run_price_refresh")


def validate_worker_database():
    database = settings.DATABASES["default"]
    if database["ENGINE"] not in {"django.db.backends.sqlite3", "django.db.backends.postgresql"}:
        raise ValidationError("Admin refresh requires SQLite or PostgreSQL.")
    name = str(database["NAME"])
    if database["ENGINE"].endswith("sqlite3") and (not name or ":memory:" in name or "mode=memory" in name):
        raise ValidationError("A separate refresh worker needs a file-based SQLite or PostgreSQL database.")


def validate_refresh(sources):
    if not sources or any(source not in REVIEWED_RETAILERS for source in sources) or len(set(sources)) != len(sources):
        raise ValidationError("Choose only the reviewed Jalal Sons and Cartpk sources.")
    if not settings.SCRAPING_ENABLED:
        raise ValidationError("Collection is disabled. Configure SCRAPING_ENABLED in the local environment first.")
    try:
        contact = settings.SCRAPER_CONTACT.strip()
        if contact.startswith("https://"):
            URLValidator(schemes=["https"])(contact)
        else:
            validate_email(contact)
    except ValidationError:
        raise ValidationError("Configure SCRAPER_CONTACT with a monitored email or public HTTPS contact URL first.") from None
    if ScrapeRun.objects.filter(retailer__slug__in=sources, status="running").exists():
        raise ValidationError("A selected retailer already has a running collection. Inspect that run first.")
    collector = ScrapeCommand()
    for source in sources:
        retailer = Retailer.objects.filter(slug=source).first()
        if not retailer:
            raise ValidationError("Configure the reviewed retailers before starting a refresh.")
        adapter = ADAPTERS[source]()
        if not adapter.enabled or not retailer.collection_enabled or retailer.status != "enabled":
            raise ValidationError(f"{retailer.name}: collection switches and validated source status must be enabled first.")
        try:
            targets = collector.get_targets(retailer, {"url": [], "batch": None, "refresh_existing": True, "stale_only": True})
            for url in targets:
                adapter.validate_url(url)
                if url not in reviewed_urls(source):
                    raise ValidationError(f"{retailer.name}: a stale listing URL is outside the reviewed catalog; inspect it first.")
        except (CommandError, CollectionError) as exc:
            raise ValidationError(f"{retailer.name}: {exc}") from None


def launch_refresh(job_id):
    """Called only after the job reservation commits. Never pass URLs or secrets as arguments."""
    module = settings.SETTINGS_MODULE or os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")
    environment = {**os.environ, "DJANGO_SETTINGS_MODULE": module, "PYTHONUNBUFFERED": "1"}
    try:
        process = subprocess.Popen(
            [sys.executable, str(settings.BASE_DIR / "manage.py"), "run_admin_refresh", str(job_id)],
            cwd=settings.BASE_DIR, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError:
        AdminPriceRefresh.objects.filter(pk=job_id, status="queued").update(
            status="failed", completed_at=timezone.now(), updated_at=timezone.now(),
            error="The local refresh worker could not be started. Inspect the local Python setup before retrying.")
        return

    def reap():
        process.wait()
        close_old_connections()
        try:
            # A process that never claimed its job cannot own a scrape run.
            AdminPriceRefresh.objects.filter(pk=job_id, status="queued").update(
                status="failed", completed_at=timezone.now(), updated_at=timezone.now(),
                error="The worker exited before starting. Check the local settings and database configuration.")
            # Do not unlock a claimed job or clear its running collection merely by age/exit.
            AdminPriceRefresh.objects.filter(pk=job_id, status="running").update(
                updated_at=timezone.now(), error="The worker exited before finalizing. Confirm it has stopped, inspect its runs, then use recover_admin_refresh.")
        finally:
            close_old_connections()

    threading.Thread(target=reap, name=f"refresh-reaper-{job_id}", daemon=True).start()


def run_refresh(job_id):
    claimed = AdminPriceRefresh.objects.filter(pk=job_id, status="queued").update(
        status="running", started_at=timezone.now(), updated_at=timezone.now(), worker_pid=os.getpid())
    if not claimed:
        return False
    job = AdminPriceRefresh.objects.get(pk=job_id)
    command = RefreshCommand(stdout=StringIO(), stderr=StringIO())
    command.retailer_slugs = tuple(job.sources)
    command.reviewed_only = True

    def progress(rows):
        AdminPriceRefresh.objects.filter(pk=job_id, status="running").update(results=rows, updated_at=timezone.now())

    command.progress_callback = progress
    status, error = "success", ""
    try:
        validate_refresh(job.sources)
        call_command(command, no_color=True)
    except ValidationError as exc:
        status, error = "failed", " ".join(exc.messages)
    except CommandError:
        status = "partial" if any(row["products_collected"] for row in command.results) else "failed"
        error = "Refresh finished with source errors. Inspect the source results and collection run records."
    except BaseException as exc:
        # No exception details/credentials are exposed; owned audit records remain inspectable.
        status, error = "failed", f"Refresh stopped unexpectedly ({type(exc).__name__}). Inspect the local worker and collection runs before retrying."
    finally:
        results = getattr(command, "results", job.results)
        run_ids = [row["run_id"] for row in results if row.get("run_id")]
        active = ScrapeRun.objects.filter(pk__in=run_ids, status="running").exists()
        if active:
            # Keep the job lock if an unexpected failure left an owned run active.
            AdminPriceRefresh.objects.filter(pk=job_id, status="running").update(
                results=results, error=error or "Inspect the active collection before recovery.", updated_at=timezone.now())
        else:
            AdminPriceRefresh.objects.filter(pk=job_id, status="running").update(
                results=results, status=status, error=error, completed_at=timezone.now(), updated_at=timezone.now())
    return True


def refresh_progress(job):
    run_ids = [row.get("run_id") for row in job.results if row.get("run_id")]
    runs = {run.pk: run for run in ScrapeRun.objects.filter(pk__in=run_ids)}
    sources = []
    for saved in job.results:
        row = dict(saved)
        row["outcome_label"] = OUTCOME_LABELS.get(row["outcome"], row["outcome"])
        run = runs.get(row.get("run_id"))
        row["url_results"] = run.results if run else []
        if run:
            row.update(products_collected=run.products_collected, request_count=run.request_count, run_status=run.status)
        row["finished_count"] = sum(result.get("status") in {"stored", "failed"} for result in row["url_results"])
        row["target_count"] = len(row["url_results"])
        sources.append(row)
    return {"id": job.pk, "status": job.status, "status_label": job.get_status_display(),
            "is_active": job.is_active, "needs_attention": job.is_active and bool(job.error),
            "error": job.error, "sources": sources, "updated_at": job.updated_at.isoformat()}
