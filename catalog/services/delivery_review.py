"""Dated public delivery claims, separate from verified listing price/stock context.

These summaries are editorial research. Loading a page never fetches a retailer.
"""
from datetime import date


DELIVERY_REVIEWS = {
    "jalal-sons": {
        "reviewed_on": date(2026, 10, 24),
        "summary": "The reviewed milk page refers to Lahore. Delivery terms say availability and charges depend on location. A shared delivery area for these price observations has not been established.",
        "evidence_url": "https://www.jalalsons.com.pk/terms-and-conditions",
        "evidence_label": "Delivery terms",
    },
    "cartpk": {
        "reviewed_on": date(2026, 10, 24),
        "summary": "The homepage advertises delivery in Karachi. The reviewed milk page also marks the item shippable outside Karachi, without identifying a destination or confirming its delivered price and stock. Confirm your address with the retailer.",
        "evidence_url": "https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr",
        "evidence_label": "Product shipping information",
    },
}
