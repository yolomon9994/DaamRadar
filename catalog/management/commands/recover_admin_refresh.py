from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import AdminPriceRefresh, ScrapeRun


class Command(BaseCommand):
    help = "Release an interrupted admin refresh only after independently confirming its worker has stopped."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--confirm-worker-stopped", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_worker_stopped"]:
            raise CommandError("Inspect the worker PID and owned runs, stop the worker if necessary, then supply --confirm-worker-stopped.")
        with transaction.atomic():
            try:
                job = AdminPriceRefresh.objects.select_for_update().get(pk=options["job_id"])
            except AdminPriceRefresh.DoesNotExist:
                raise CommandError("Admin refresh request does not exist.") from None
            if not job.is_active:
                raise CommandError("This refresh is already finalized; nothing was changed.")
            for row in job.results:
                if not row.get("run_id"):
                    continue
                run = ScrapeRun.objects.filter(pk=row["run_id"], retailer__slug=row["retailer"], status="running").first()
                if run:
                    run.status = "partial" if run.products_collected else "failed"
                    run.completed_at = timezone.now()
                    run.error_code, run.error = "operator_stopped", "Operator confirmed the admin refresh worker has stopped."
                    run.save(update_fields=["status", "completed_at", "error_code", "error"])
                row["outcome"] = "stopped" if row["outcome"] in {"running", "not_attempted"} else row["outcome"]
            job.status, job.completed_at, job.updated_at = "stopped", timezone.now(), timezone.now()
            job.error = "Operator confirmed the worker has stopped; owned active runs were finalized without changing observations."
            job.save(update_fields=["status", "results", "completed_at", "updated_at", "error"])
        self.stdout.write(f"Refresh #{job.pk} marked stopped. No observations were added or removed.")
