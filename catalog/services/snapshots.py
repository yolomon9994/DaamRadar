"""Expiry for observed-data snapshots; no automatic collection or refresh."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

MAX_AGE_SECONDS = 300


def snapshot_metadata(check_times=(), *, now=None):
    as_of = now if now is not None else timezone.now()
    window = timedelta(hours=settings.PRICE_STALE_HOURS)
    deadline = as_of + timedelta(seconds=MAX_AGE_SECONDS)
    for checked in check_times:
        # A future timestamp can become current; an in-window check can age out.
        transition = checked if checked > as_of else checked + window
        if transition >= as_of:
            deadline = min(deadline, transition)
    return {"as_of": as_of.isoformat(), "expires_at": deadline.isoformat(), "max_age_seconds": MAX_AGE_SECONDS}
