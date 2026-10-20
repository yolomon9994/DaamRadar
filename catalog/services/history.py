"""Bounded, read-only chart geometry from actual listing observations."""
from collections import Counter, defaultdict
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from zoneinfo import ZoneInfo

from django.db.models import F, Window
from django.db.models.functions import RowNumber

from catalog.models import PriceHistory

HISTORY_LIMIT = 120
PKT = ZoneInfo("Asia/Karachi")
STYLES = (("#174d39", ""), ("#995021", "8 4"), ("#275d9f", "3 4"),
          ("#794a88", "10 3 2 3"), ("#526418", "5 3"), ("#a03554", "2 3"))
LEFT, RIGHT, TOP, BOTTOM = 92, 892, 38, 262


def price_history_chart(product):
    # A product must never acquire another source's history through a bad listing.
    offers = sorted((offer for offer in product.offers if offer.is_demo == product.is_demo),
                    key=lambda offer: (offer.retailer.name, offer.pk))
    grouped = defaultdict(list)
    rows = PriceHistory.objects.filter(listing_id__in=[offer.pk for offer in offers]).annotate(
        position=Window(RowNumber(), partition_by=[F("listing_id")],
                        order_by=[F("checked_at").desc(), F("pk").desc()]),
    ).filter(position__lte=HISTORY_LIMIT + 1).order_by("listing_id", "-checked_at", "-pk")
    for row in rows:
        grouped[row.listing_id].append(row)

    retailer_counts = Counter(offer.retailer_id for offer in offers)
    series, records = [], []
    for index, offer in enumerate(offers):
        recent = grouped[offer.pk]
        truncated = len(recent) > HISTORY_LIMIT
        recent = list(reversed(recent[:HISTORY_LIMIT]))
        label = offer.retailer.name
        if retailer_counts[offer.retailer_id] > 1:
            label += f" · {offer.delivery_area or 'Area unspecified'} · listing {offer.pk}"
        color, dash = STYLES[index % len(STYLES)]
        item = {"id": f"history-series-{offer.pk}", "listing_id": offer.pk, "label": label,
                "area": offer.delivery_area, "color": color, "dash": dash,
                "points": [], "truncated": truncated}
        for row in recent:
            record = {"price": row.price, "checked_at": row.checked_at.astimezone(PKT), "label": label,
                      "series_id": item["id"], "pk": row.pk}
            item["points"].append(record)
            records.append(record)
        series.append(item)

    chart = {"series": series, "records": sorted(records, key=lambda row: (row["checked_at"], row["pk"])),
             "count": len(records), "limit": HISTORY_LIMIT, "truncated": any(s["truncated"] for s in series),
             "price_ticks": [], "time_ticks": [], "left": LEFT, "right": RIGHT, "top": TOP, "bottom": BOTTOM}
    if not records:
        return chart

    prices = [row["price"] for row in records]
    padding = max(Decimal("1"), (max(prices) - min(prices)) / 10)
    low = max(Decimal("0"), (min(prices) - padding).to_integral_value(rounding=ROUND_FLOOR))
    high = (max(prices) + padding).to_integral_value(rounding=ROUND_CEILING)
    start = min(row["checked_at"].timestamp() for row in records)
    end = max(row["checked_at"].timestamp() for row in records)
    for index in range(5):
        price = low + (high - low) * index / 4
        chart["price_ticks"].append({"label": f"{price:,.2f}", "y": BOTTOM - (BOTTOM - TOP) * index / 4})
    fractions = (0, 0.5, 1) if end != start else (0.5,)
    for fraction in fractions:
        stamp = start + (end - start) * fraction
        chart["time_ticks"].append({"date": datetime.fromtimestamp(stamp, datetime_timezone.utc).astimezone(PKT),
                                    "x": LEFT + (RIGHT - LEFT) * fraction})
    for item in series:
        for point in item["points"]:
            point["x"] = LEFT + (RIGHT - LEFT) * (point["checked_at"].timestamp() - start) / (end - start) if end != start else (LEFT + RIGHT) / 2
            point["y"] = BOTTOM - float((point["price"] - low) / (high - low)) * (BOTTOM - TOP)
        item["polyline"] = " ".join(f'{point["x"]:.3f},{point["y"]:.3f}' for point in item["points"])
    return chart
