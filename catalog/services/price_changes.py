"""Compare consecutive observations conservatively; do not infer savings or eligibility."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from catalog.models import PriceHistory
from catalog.services.observations import context_known, observation_context, same_context


def price_change(listing, records, *, product):
    result = {"status": "no_previous", "label": "No earlier price recorded", "amount": None, "percent": None,
              "previous_price": None, "previous_checked_at": None, "price": None, "checked_at": None}
    if len(records) < 2:
        return result
    latest, previous = records[:2]
    def unavailable(status, label):
        return {**result, "status": status, "label": label}
    if not context_known(latest.context) or not context_known(previous.context):
        return unavailable("context_unknown", "Historical context unknown")
    if latest.checked_at > timezone.now() or previous.checked_at >= latest.checked_at:
        return unavailable("invalid_time", "Earlier check time unavailable")
    current = observation_context(listing, product=product)
    if latest.price != listing.current_price or latest.checked_at != listing.last_checked or latest.context != current:
        return unavailable("unrecorded_changes", "Listing changed since its recorded check")
    if (current["is_demo"] != product.is_demo or current["product_is_demo"] != product.is_demo
            or not same_context(latest.context, previous.context)):
        return unavailable("context_changed", "Product or delivery context changed")
    if any(record.context["availability"] != "in_stock" for record in (latest, previous)):
        return unavailable("stock_unavailable", "Comparable in-stock history unavailable")
    delta = latest.price - previous.price
    amount = abs(delta)
    percentage = (amount / previous.price * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    status = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
    label = (f"Recorded {'increase' if delta > 0 else 'decrease'}: Rs. {amount:,.2f}"
             if delta else "Recorded price unchanged")
    return {**result, "status": status, "label": label, "amount": format(amount, ".2f"),
            "percent": format(percentage, ".2f"), "previous_price": format(previous.price, ".2f"),
            "previous_checked_at": previous.checked_at.isoformat(), "price": format(latest.price, ".2f"),
            "checked_at": latest.checked_at.isoformat()}


def attach_price_changes(products):
    pairs = [(product, offer) for product in products for offer in product.offers]
    if not pairs:
        return
    grouped = defaultdict(list)
    rows = PriceHistory.objects.filter(listing_id__in=[offer.pk for _, offer in pairs]).annotate(
        position=Window(RowNumber(), partition_by=[F("listing_id")],
                        order_by=[F("checked_at").desc(), F("pk").desc()])
    ).filter(position__lte=2).order_by("listing_id", "-checked_at", "-pk")
    for row in rows:
        grouped[row.listing_id].append(row)
    for product, offer in pairs:
        offer.price_change = price_change(offer, grouped[offer.pk], product=product)
