from django.core.management.base import BaseCommand
from catalog.models import Retailer

SOURCES = [
    ("naheed", "Naheed", "https://www.naheed.pk", "Review requests retrieved robots, terms and product HTML on 18 October 2026. The subsequent named collector returned HTTP 403. Parser retained for offline tests; live collection disabled without retries or identity switching. No prices imported."),
    ("jalal-sons", "Jalal Sons", "https://www.jalalsons.com.pk", "Public robots, terms and product HTML checked 18 October 2026. Product-page paths are crawlable; internal API routes are excluded. Limited manual factual-price adapter available. Delivery area unverified; no general reuse license claimed."),
    ("springs", "Springs", "https://springs.com.pk", "robots.txt and terms checked 18 October 2026. Terms restrict copying/distribution without written permission. Location-specific prices remain unvalidated. Collection disabled."),
    ("alfatah", "Al-Fatah", "https://alfatah.pk", "Public storefront and robots.txt inspected. Terms restrict reuse to personal shopping. Written permission or a licensed feed is needed for comparison-platform collection. Live collection unavailable."),
]


class Command(BaseCommand):
    help = "Create source records without enabling collection; update public access notes on existing records."

    def handle(self, *args, **options):
        for slug, name, website, notes in SOURCES:
            retailer, created = Retailer.objects.get_or_create(slug=slug, defaults={"name": name, "website": website,
                "status": "pending" if slug == "jalal-sons" else "unavailable", "collection_enabled": False, "access_notes": notes})
            if not created:
                retailer.access_notes = notes
                retailer.save(update_fields=["access_notes"])
        self.stdout.write("Retailer records are configured. Existing collection settings were preserved; new sources default to disabled.")
