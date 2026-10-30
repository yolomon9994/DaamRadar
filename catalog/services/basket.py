"""Read-only basket estimates. Never rank incomplete or incompatible baskets."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from catalog.models import Product, Retailer, RetailerListing
from catalog.services.list_transfer import product_descriptor
from catalog.services.unit_pricing import standard_unit_price
from catalog.services.snapshots import snapshot_metadata


def money(value):
    return format(value, ".2f") if value is not None else None


def estimate_basket(items, source, unresolved=(), budget=None):
    """Items have already been validated as unique (slug, quantity) pairs."""
    demo = source == "demo"
    checked_at = timezone.now()
    cutoff = checked_at - timedelta(hours=settings.PRICE_STALE_HOURS)
    products = {p.slug: p for p in Product.objects.filter(slug__in=[s for s, _ in items], is_demo=demo).exclude(slug__in=unresolved)}
    offers = defaultdict(list)
    for offer in RetailerListing.objects.filter(product__in=products.values(), is_demo=demo).select_related("retailer"):
        offers[(offer.retailer_id, offer.product_id)].append(offer)
    # Include retailers with this catalog's observations, even if none cover this list.
    retailers = Retailer.objects.filter(listings__is_demo=demo, listings__product__is_demo=demo).distinct().order_by("name") if items else []
    result = {
        "source": source, "currency": "PKR", "estimated_at": checked_at.isoformat(), "budget": money(budget),
        "items": [{"slug": slug, "quantity": quantity,
                   "name": products[slug].canonical_name if slug in products else "Product unavailable in this catalog",
                   "size": products[slug].size_label if slug in products else "Size unavailable",
                   "product": product_descriptor(products[slug]) if slug in products else None,
                   "available": slug in products} for slug, quantity in items],
        "retailers": [],
        **snapshot_metadata((o.last_checked for group in offers.values() for o in group), now=checked_at),
    }
    for retailer in retailers:
        lines, subtotal, scopes = [], Decimal("0"), set()
        unverified = False
        for slug, quantity in items:
            product = products.get(slug)
            candidates = offers[(retailer.pk, product.pk)] if product else []
            fresh = [o for o in candidates if cutoff <= o.last_checked <= checked_at]
            eligible = [o for o in fresh if o.availability == "in_stock"]
            chosen = None
            if eligible:
                # Multiple locations cannot silently become a cheapest-location offer.
                verified_scopes = {o.delivery_area_key for o in eligible if o.area_is_verified}
                demo_scopes = {o.delivery_area for o in eligible}
                compatible = (len(demo_scopes) == 1 if demo else
                              len(verified_scopes) == 1 and all(o.area_is_verified for o in eligible))
                if len(eligible) > 1 and not compatible:
                    status = "area_ambiguous"
                else:
                    chosen = min(eligible, key=lambda o: (o.current_price, o.pk))
                    status = "included"
            elif not candidates:
                status = "missing" if product else "product_unavailable"
            elif not fresh:
                status = "check_time_invalid" if any(o.last_checked > checked_at for o in candidates) else "stale"
            elif any(o.availability == "unknown" for o in fresh):
                status = "availability_unknown"
            else:
                status = "out_of_stock"
            line_total = chosen.current_price * quantity if chosen else None
            if chosen:
                subtotal += line_total
                verified = chosen.area_is_verified
                # Different verified keys or different unverified labels need review.
                scopes.add(("verified", chosen.delivery_area_key) if verified else ("label", chosen.delivery_area.strip()))
                unverified |= not demo and not verified
            lines.append({"slug": slug, "quantity": quantity, "status": status,
                          "unit_price": money(chosen.current_price) if chosen else None,
                          "standard_unit_price": standard_unit_price(product, chosen.current_price) if chosen else None,
                          "line_total": money(line_total),
                          "last_checked": chosen.last_checked.isoformat() if chosen else None,
                          "last_observed_at": max(o.last_checked for o in candidates).isoformat() if candidates else None,
                          "delivery_area": chosen.delivery_area if chosen else "",
                          "area_is_verified": chosen.area_is_verified if chosen else False})
        covered = sum(line["status"] == "included" for line in lines)
        conflict = len(scopes) > 1
        complete = bool(items) and covered == len(items) and not conflict
        assessment = {"status": "not_set", "remaining": None, "over_by": None}
        if budget is not None:
            if not complete:
                assessment["status"] = "incomplete"
            elif subtotal > budget:
                assessment.update(status="over_budget", over_by=money(subtotal - budget))
            else:
                assessment.update(status="at_budget" if subtotal == budget else "within_budget", remaining=money(budget - subtotal))
        result["retailers"].append({
            "name": retailer.name, "slug": retailer.slug, "covered_count": covered,
            "item_count": len(items), "is_complete": complete,
            "subtotal": money(subtotal) if covered else None,
            "total": money(subtotal) if complete else None,
            "has_unverified_areas": unverified, "has_mixed_areas": conflict, "lines": lines,
            "budget_assessment": assessment,
        })
    return result
