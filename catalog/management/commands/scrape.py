import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import Category, Retailer, ScrapeRun
from catalog.matching.normalization import identify
from catalog.scraping.adapters import ADAPTERS
from catalog.scraping.client import PoliteClient
from catalog.scraping.types import CollectionError
from catalog.services.ingestion import ingest

logger = logging.getLogger("catalog")


class Command(BaseCommand):
    help = "Manually collect up to ten reviewed public product URLs. No scheduling or catalog crawling."

    def add_arguments(self, parser):
        parser.add_argument("retailer", choices=list(ADAPTERS))
        parser.add_argument("--url", action="append", default=[], help="Explicit authorized product URL; repeat up to 10 times.")

    def handle(self, *args, **options):
        try:
            retailer = Retailer.objects.get(slug=options["retailer"])
        except Retailer.DoesNotExist:
            raise CommandError("Retailer is not configured. Run python manage.py seed_retailers first.") from None
        run = ScrapeRun.objects.create(retailer=retailer)
        client = None
        try:
            adapter = ADAPTERS[retailer.slug]()
            if not adapter.enabled:
                raise CollectionError(adapter.reason)
            if not settings.SCRAPING_ENABLED or not retailer.collection_enabled or retailer.status != "enabled":
                raise CollectionError("Collection is disabled. Source review and explicit configuration are required.")
            if not 1 <= len(options["url"]) <= 10:
                raise CollectionError("Provide between 1 and 10 explicitly authorized product URLs.")
            client = PoliteClient(retailer.website)
            for url in dict.fromkeys(options["url"]):
                item = adapter.collect(client, url)
                # A narrow initial classification; unfamiliar products remain uncategorized.
                category = Category.objects.filter(slug="dairy").first() if "milk" in identify(item.title).name.split() else None
                listing, _ = ingest(retailer, item, category=category)
                run.products_collected += 1
                self.stdout.write(f"{listing.original_title} | PKR {listing.current_price:.2f} | {listing.availability} | {listing.url}")
            run.status = ScrapeRun.Status.SUCCESS
        except CollectionError as exc:
            run.status = ScrapeRun.Status.PARTIAL if run.products_collected else ScrapeRun.Status.BLOCKED
            run.error = str(exc)
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            run.status = ScrapeRun.Status.PARTIAL if run.products_collected else ScrapeRun.Status.FAILED
            run.error = f"{type(exc).__name__}: collection failed; inspect local logs."
            logger.exception("Retailer collection failed: %s", retailer.slug)
            raise CommandError(run.error) from exc
        finally:
            if client:
                client.close()
            run.completed_at = timezone.now()
            run.save()
        self.stdout.write(self.style.SUCCESS(f"Stored {run.products_collected} observations."))
