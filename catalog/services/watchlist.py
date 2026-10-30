"""Read-only target checks against individual, dated pack-price observations."""
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from catalog.models import Product, RetailerListing
from catalog.services.unit_pricing import standard_unit_price
from catalog.services.list_transfer import product_descriptor
from catalog.services.snapshots import snapshot_metadata


def check_targets(items, source, unresolved=()):
    now = timezone.now()
    window = timedelta(hours=settings.PRICE_STALE_HOURS)
    demo = source == "demo"
    products = {p.slug: p for p in Product.objects.filter(slug__in=[slug for slug, _ in items], is_demo=demo).exclude(slug__in=unresolved)}
    offers = defaultdict(list)
    for offer in RetailerListing.objects.filter(product__in=products.values(), is_demo=demo).select_related("retailer").order_by("retailer__name", "pk"):
        offers[offer.product_id].append(offer)
    results = []
    for slug, target in items:
        product = products.get(slug)
        observations = offers[product.pk] if product else []
        fresh = [o for o in observations if now - window <= o.last_checked <= now]
        eligible = [o for o in fresh if o.availability == "in_stock"]
        price = min((o.current_price for o in eligible), default=None)
        if price is not None:
            met = price <= target
            status = "target_met" if met else "above_target"
            message = "A fresh in-stock observation meets your target. Confirm stock, delivery coverage and final checkout costs." if met else "Fresh in-stock observations are above your target."
        elif product is None:
            status, message = "product_unavailable", "Product removed or unavailable in this catalog."
        elif not observations:
            status, message = "not_listed", "No retailer observations are stored for this product."
        elif not fresh:
            if all(o.last_checked < now - window for o in observations):
                status, message = "stale", "Only stale observations are available. Collect new prices before checking this target."
            else:
                status, message = "unavailable", "No observation has a valid current check time."
        elif any(o.availability == "unknown" for o in fresh):
            status, message = "availability_unknown", "Stock is unknown. This target cannot be checked yet."
        else:
            status, message = "out_of_stock", "Fresh observations are out of stock. No target alert is shown."
        rows, scopes = [], set()
        for offer in eligible:
            verified = offer.area_is_verified
            scopes.add(("verified", offer.delivery_area_key) if verified else ("label", offer.delivery_area.strip()))
            rows.append({"retailer": offer.retailer.name, "price": format(offer.current_price, ".2f"),
                         "meets_target": offer.current_price <= target, "last_checked": offer.last_checked.isoformat(),
                         "delivery_area": offer.delivery_area, "area_is_verified": verified})
        results.append({"slug": slug, "target": format(target, ".2f"), "available": product is not None,
                        "name": product.canonical_name if product else None, "size": product.size_label if product else None,
                        "product": product_descriptor(product) if product else None,
                        "status": status, "message": message, "observed_price": format(price, ".2f") if price is not None else None,
                        "standard_unit_price": standard_unit_price(product, price),
                        "last_observed_at": max(o.last_checked for o in observations).isoformat() if observations else None,
                        "has_unverified_areas": not demo and any(not o.area_is_verified for o in eligible),
                        "has_mixed_areas": len(scopes) > 1, "offers": rows})
    return {"source": source, "currency": "PKR", "evaluated_at": now.isoformat(),
            **snapshot_metadata((o.last_checked for group in offers.values() for o in group), now=now), "items": results}
