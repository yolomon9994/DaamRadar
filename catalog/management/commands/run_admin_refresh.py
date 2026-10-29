from django.core.management.base import BaseCommand, CommandError

from catalog.models import AdminPriceRefresh
from catalog.services.admin_refresh import run_refresh


class Command(BaseCommand):
    help = "Execute one reserved admin price refresh. Not a scheduler or a source-enabling command."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, *args, **options):
        if not AdminPriceRefresh.objects.filter(pk=options["job_id"]).exists():
            raise CommandError("Admin refresh request does not exist.")
        run_refresh(options["job_id"])
