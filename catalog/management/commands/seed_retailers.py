from django.core.management.base import BaseCommand
from catalog.models import Retailer

SOURCES = [
    ("naheed", "Naheed", "https://www.naheed.pk", "Homepage returned HTTP 403. robots.txt could not be verified. Terms reviewed via public search; no licensed product feed verified. Live collection unavailable."),
    ("springs", "Springs", "https://springs.com.pk", "Homepage redirects to branch/location selection. robots.txt and terms could not be fully verified. No approved location-specific feed verified. Live collection unavailable."),
    ("alfatah", "Al-Fatah", "https://alfatah.pk", "Public storefront and robots.txt inspected. Terms restrict reuse to personal shopping. Written permission or a licensed feed is needed for comparison-platform collection. Live collection unavailable."),
]


class Command(BaseCommand):
    help = "Create initial retailer records without enabling any live collection."

    def handle(self, *args, **options):
        for slug, name, website, notes in SOURCES:
            Retailer.objects.get_or_create(slug=slug, defaults={"name": name, "website": website,
                "status": "unavailable", "collection_enabled": False, "access_notes": notes})
        self.stdout.write("Initial retailer records are configured; live collection remains disabled.")
