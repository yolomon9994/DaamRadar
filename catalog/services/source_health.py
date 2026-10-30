"""Public stored-data summaries; never expose operator logs or fetch a retailer."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db.models import Count, Exists, Max, Min, OuterRef, Q, Subquery
from catalog.services.snapshots import snapshot_metadata
from django.utils import timezone

from catalog.models import Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import ADAPTERS
from catalog.services.delivery_review import DELIVERY_REVIEWS

OUTCOMES = {"success": "Selected URLs completed", "partial": "Selected URLs partially completed",
            "failed": "Collection attempt failed", "blocked": "Collection attempt blocked",
            "running": "Collection marked running"}


def contact_configured():
    """Return only validity; the configured address stays private."""
    contact = settings.SCRAPER_CONTACT.strip()
    try:
        if contact.startswith("https://"):
            URLValidator(schemes=["https"])(contact)
        else:
            validate_email(contact)
    except ValidationError:
        return False
    return True


def source_health(*, now=None):
    as_of = now if now is not None else timezone.now()
    cutoff = as_of - timedelta(hours=settings.PRICE_STALE_HOURS)
    live = Q(listings__is_demo=False, listings__product__is_demo=False)
    valid_time = Q(listings__last_checked__lte=as_of)
    fresh = valid_time & Q(listings__last_checked__gte=cutoff)
    runs = ScrapeRun.objects.filter(retailer_id=OuterRef("pk"))
    latest = runs.order_by("-started_at", "-pk")
    successful = runs.filter(status="success", completed_at__isnull=False).order_by("-completed_at", "-pk")
    # Run error text, per-URL results, worker IDs and account details stay in admin.
    retailers = Retailer.objects.annotate(
        collected_count=Count("listings", filter=live),
        fresh_count=Count("listings", filter=live & fresh),
        stale_count=Count("listings", filter=live & Q(listings__last_checked__lt=cutoff)),
        future_count=Count("listings", filter=live & Q(listings__last_checked__gt=as_of)),
        last_checked=Max("listings__last_checked", filter=live & valid_time),
        earliest_fresh=Min("listings__last_checked", filter=live & fresh),
        earliest_future=Min("listings__last_checked", filter=live & Q(listings__last_checked__gt=as_of)),
        latest_outcome=Subquery(latest.values("status")[:1]),
        latest_attempt_at=Subquery(latest.values("started_at")[:1]),
        last_success_at=Subquery(successful.values("completed_at")[:1]),
        has_running_record=Exists(runs.filter(status="running")),
    ).order_by("name", "pk")
    totals = {"live": 0, "fresh": 0, "stale": 0, "future": 0}
    rows = []
    contact_ready = contact_configured()
    for retailer in retailers:
        if not retailer.collected_count:
            freshness = "No collected observations"
        elif retailer.future_count:
            freshness = "Check timestamps need review"
        elif retailer.stale_count == retailer.collected_count:
            freshness = "All observations stale"
        elif retailer.stale_count:
            freshness = "Some observations stale"
        else:
            freshness = "Recent checks recorded"
        adapter = ADAPTERS.get(retailer.slug)
        if adapter is None or not adapter.enabled or retailer.status == Retailer.Status.UNAVAILABLE:
            collection_state = "Collection unavailable"
        elif retailer.status != Retailer.Status.ENABLED:
            collection_state = "Source under review"
        elif not settings.SCRAPING_ENABLED or not retailer.collection_enabled or not contact_ready:
            collection_state = "Manual collection paused"
        else:
            collection_state = "Manual collection configured"
        retailer.delivery_review = DELIVERY_REVIEWS.get(retailer.slug)
        rows.append({"retailer": retailer, "freshness": freshness, "collection_state": collection_state,
                     "latest_outcome": OUTCOMES.get(retailer.latest_outcome, "No collection attempts recorded")})
        for total, field in (("live", "collected_count"), ("fresh", "fresh_count"),
                             ("stale", "stale_count"), ("future", "future_count")):
            totals[total] += getattr(retailer, field)
    products = RetailerListing.objects.filter(is_demo=False, product__is_demo=False).aggregate(
        count=Count("product_id", distinct=True))["count"]
    return {"source_rows": rows, "totals": totals, "product_count": products,
            "snapshot": snapshot_metadata((checked for row in rows for checked in
                (row["retailer"].earliest_fresh, row["retailer"].earliest_future) if checked is not None), now=as_of),
            "as_of": as_of, "cutoff": cutoff, "stale_hours": settings.PRICE_STALE_HOURS}
