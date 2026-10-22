"""Read-only collection diagnostics; never contact or enable a source."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.utils import timezone

from catalog.models import Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import ADAPTERS

ISSUE_LIMIT = 20


def can_view_collection_health(user):
    return all(user.has_perm(f"catalog.view_{model}") or user.has_perm(f"catalog.change_{model}")
               for model in ("retailer", "retailerlisting", "product", "scraperun"))


def collection_health(*, retailer_slug="", now=None):
    as_of = now if now is not None else timezone.now()
    cutoff = as_of - timedelta(hours=settings.PRICE_STALE_HOURS)
    live = Q(listings__is_demo=False, listings__product__is_demo=False)
    runs = ScrapeRun.objects.filter(retailer_id=OuterRef("pk"))
    latest = runs.order_by("-started_at", "-pk")
    successful = runs.filter(status="success", completed_at__isnull=False).order_by("-completed_at", "-pk")
    active = runs.filter(status="running").order_by("-started_at", "-pk")
    retailers = Retailer.objects.annotate(
        live_count=Count("listings", filter=live),
        fresh_count=Count("listings", filter=live & Q(listings__last_checked__gte=cutoff)),
        stale_count=Count("listings", filter=live & Q(listings__last_checked__lt=cutoff)),
        last_checked=Max("listings__last_checked", filter=live),
        last_success_id=Subquery(successful.values("pk")[:1]),
        last_success_at=Subquery(successful.values("completed_at")[:1]),
        latest_run_id=Subquery(latest.values("pk")[:1]),
        latest_run_status=Subquery(latest.values("status")[:1]),
        latest_run_at=Subquery(latest.values("started_at")[:1]),
        active_run_id=Subquery(active.values("pk")[:1]),
    ).order_by("name", "pk")
    listings = RetailerListing.objects.filter(is_demo=False, product__is_demo=False, last_checked__lt=cutoff)
    issues = ScrapeRun.objects.filter(status__in=("failed", "blocked", "partial"))
    if retailer_slug:
        retailers = retailers.filter(slug=retailer_slug)
        listings = listings.filter(retailer__slug=retailer_slug)
        issues = issues.filter(retailer__slug=retailer_slug)

    rows = []
    totals = {"live": 0, "fresh": 0, "stale": 0, "running": 0}
    for retailer in retailers:
        adapter = ADAPTERS.get(retailer.slug)
        reasons = []
        if adapter is None:
            reasons.append("No collection adapter is configured.")
        elif not adapter.enabled:
            reasons.append(getattr(adapter, "reason", "The source adapter is paused."))
        if not settings.SCRAPING_ENABLED:
            reasons.append("The global collection switch is off.")
        if not retailer.collection_enabled:
            reasons.append("The retailer collection switch is off.")
        if retailer.status != Retailer.Status.ENABLED:
            reasons.append(f"Source status: {retailer.get_status_display()}.")
        if retailer.active_run_id:
            reasons.append("A run is marked running. Inspect its process and outcomes before starting another.")
        rows.append({"retailer": retailer, "manual_ready": not reasons, "reasons": reasons,
                     "latest_status_label": dict(ScrapeRun.Status.choices).get(retailer.latest_run_status, "No runs")})
        totals["live"] += retailer.live_count
        totals["fresh"] += retailer.fresh_count
        totals["stale"] += retailer.stale_count
        totals["running"] += bool(retailer.active_run_id)

    return {
        "source_rows": rows, "totals": totals, "as_of": as_of, "cutoff": cutoff,
        "stale_hours": settings.PRICE_STALE_HOURS, "issue_limit": ISSUE_LIMIT,
        "recent_issues": list(issues.select_related("retailer").order_by("-started_at", "-pk")[:ISSUE_LIMIT]),
        "stale_listings": listings.select_related("retailer", "product").order_by("last_checked", "pk"),
    }
