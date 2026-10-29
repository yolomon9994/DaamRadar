"""Conservative size families and dated unit-rate comparisons, without substitution."""
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Exists, OuterRef
from django.utils import timezone

from catalog.matching.normalization import identify, normalize_text
from catalog.models import Product, RetailerListing
from catalog.services.list_transfer import product_descriptor
from catalog.services.unit_pricing import BASES, standard_unit_price

CANDIDATE_LIMIT = 1000
PRODUCT_LIMIT = 30
LISTING_LIMIT = 200
SORTS = {"size": "Total pack contents", "unit_price": "Eligible unit rate", "pack_price": "Recorded pack price"}


def family_key(product):
    """Ignore size/count only; never use fuzzy similarity or barcode equivalence."""
    title = identify(product.canonical_name, product.brand)
    inferred = identify(product.canonical_name)
    if (not title.brand or not title.name or title.quantity is None
            or (inferred.brand and inferred.brand != title.brand)
            or (title.quantity, title.unit, title.pack_count) != (product.quantity, product.unit, product.pack_count)
            or standard_unit_price(product, Decimal("1")) is None):
        return None
    variants = title.variants | set(normalize_text(product.variant).split())
    packaging = title.packaging | set(normalize_text(product.packaging).split())
    if title.packaging and product.packaging and title.packaging != set(normalize_text(product.packaging).split()):
        return None
    return (title.brand, tuple(sorted(title.name.split())), product.unit,
            tuple(sorted(variants)), tuple(sorted(packaging)), product.category_id)


def dimension(product):
    return (product.quantity, product.unit, product.pack_count)


def total_contents(product):
    if family_key(product) is None:
        return None
    factor, label = BASES[product.unit]
    total = product.quantity * product.pack_count / factor
    return f"{total.normalize():f} {label}"


def listing_identity_matches(listing, product):
    title = identify(listing.original_title, product.brand)
    inferred = identify(listing.original_title)
    canonical = identify(product.canonical_name, product.brand)
    return (not inferred.brand or inferred.brand == canonical.brand) and (
        title.brand, tuple(sorted(title.name.split())), title.quantity, title.unit,
        title.pack_count, title.variants, title.packaging) == (
        canonical.brand, tuple(sorted(canonical.name.split())), canonical.quantity, canonical.unit,
        canonical.pack_count, canonical.variants, canonical.packaging)


def public_listing_url(listing):
    if listing.is_demo:
        return ""
    try:
        URLValidator(schemes=["https"])(listing.url)
        target, origin = urlparse(listing.url), urlparse(listing.retailer.website)
        if target.netloc == origin.netloc and not target.username and not target.password:
            return listing.url
    except (ValidationError, ValueError):
        pass
    return ""


def pack_comparison(reference, *, sort="size", now=None):
    if sort not in SORTS:
        raise ValueError("Choose a supported pack comparison sort.")
    as_of = now if now is not None else timezone.now()
    cutoff = as_of - timedelta(hours=settings.PRICE_STALE_HOURS)
    key = family_key(reference)
    products, notice = [reference], ""
    if key is not None:
        has_listing = RetailerListing.objects.filter(product_id=OuterRef("pk"), is_demo=reference.is_demo)
        candidates = list(Product.objects.filter(is_demo=reference.is_demo, unit=reference.unit)
                          .annotate(has_listing=Exists(has_listing)).filter(has_listing=True)
                          .order_by("pk")[:CANDIDATE_LIMIT + 1])
        if len(candidates) > CANDIDATE_LIMIT:
            notice = "Too many catalog candidates to verify a complete size family. Only the selected product is shown."
        else:
            peers = [p for p in candidates if p.pk != reference.pk and family_key(p) == key
                     and not (dimension(p) == dimension(reference) and p.gtin and reference.gtin and p.gtin != reference.gtin)]
            if len(peers) >= PRODUCT_LIMIT:
                notice = "Too many compatible products for a complete comparison. Only the selected product is shown."
            else:
                products += peers
                codes = {}
                for product in products:
                    if product.gtin:
                        codes.setdefault(dimension(product), set()).add(product.gtin)
                if any(len(values) > 1 for values in codes.values()):
                    notice = "Conflicting barcodes for the same pack format need review. No lowest unit rate is highlighted."
    else:
        notice = "The selected product's identity or pack contents need review. No automatic size family or unit-rate highlight is available."

    offers = list(RetailerListing.objects.filter(product_id__in=[p.pk for p in products], is_demo=reference.is_demo,
                  product__is_demo=reference.is_demo).select_related("retailer").order_by("product_id", "pk")[:LISTING_LIMIT + 1])
    overflow = len(offers) > LISTING_LIMIT
    if overflow:
        notice = "The listing display limit was reached. This selection is incomplete; no lowest unit rate is highlighted."
        offers = offers[:LISTING_LIMIT]
    by_product = {p.pk: [] for p in products}
    for offer in offers:
        by_product[offer.product_id].append(offer)
    rows = []
    for product in products:
        valid_product = family_key(product) is not None
        for listing in by_product[product.pk] or [None]:
            row = {"product_id": product.pk, "product_slug": product.slug, "product_name": product.canonical_name,
                   "brand": product.brand, "pack_size": product.size_label, "total_contents": total_contents(product),
                   "quantity": str(product.quantity) if product.quantity is not None else None,
                   "unit": product.unit, "pack_count": product.pack_count, "variant": product.variant, "gtin": product.gtin,
                   "packaging": product.packaging or " ".join(sorted(identify(product.canonical_name).packaging)),
                   "is_reference": product.pk == reference.pk, "is_demo": reference.is_demo,
                   "listing_id": listing.pk if listing else None, "retailer": listing.retailer.name if listing else None,
                   "retailer_slug": listing.retailer.slug if listing else None,
                   "price": format(listing.current_price, ".2f") if listing else None,
                   "availability": listing.availability if listing else None,
                   "last_checked": listing.last_checked.isoformat() if listing else None,
                   "delivery_area": listing.delivery_area if listing else "", "area_is_verified": False,
                   "area_evidence_url": "", "url": public_listing_url(listing) if listing else "",
                   "standard_unit_price": None, "eligible": False, "is_lowest_unit_rate": False, "exclusions": [],
                   "_size": product.quantity * product.pack_count if valid_product else Decimal("Infinity"),
                   "_dimension": dimension(product), "_rate": None, "_scope": None}
            if listing is None:
                row["exclusions"].append("Not shown within display limit" if overflow else "No collected listings" if not reference.is_demo else "No sample listings")
            else:
                identity_ok = valid_product and listing_identity_matches(listing, product)
                if not identity_ok:
                    row["exclusions"].append("Product or listing identity needs review")
                if listing.currency != "PKR":
                    row["exclusions"].append("Currency needs review")
                if identity_ok and listing.currency == "PKR":
                    row["standard_unit_price"] = standard_unit_price(product, listing.current_price)
                    if row["standard_unit_price"] is not None:
                        row["_rate"] = Fraction(listing.current_price * BASES[product.unit][0]) / Fraction(product.quantity * product.pack_count)
                if row["_rate"] is None:
                    row["exclusions"].append("Unit price unavailable")
                if listing.last_checked < cutoff:
                    row["exclusions"].append("Stale observation")
                if listing.last_checked > as_of:
                    row["exclusions"].append("Future check time needs review")
                if listing.availability != "in_stock":
                    row["exclusions"].append(listing.get_availability_display())
                row["eligible"] = not row["exclusions"]
                row["area_is_verified"] = bool(listing.area_is_verified and listing.area_verified_at <= as_of)
                row["area_evidence_url"] = listing.area_evidence_url if row["area_is_verified"] else ""
                if reference.is_demo:
                    area = " ".join(listing.delivery_area.split()).casefold()
                    if area and not re.search(r"\b(unverified|unknown|unspecified)\b", area):
                        row["_scope"] = area
                elif row["area_is_verified"]:
                    row["_scope"] = (listing.delivery_area_key, " ".join(listing.delivery_area.split()).casefold())
            rows.append(row)

    eligible = [row for row in rows if row["eligible"]]
    ranking_available, comparison_area = False, ""
    if notice:
        ranking_note = notice
    elif len({row["_dimension"] for row in eligible}) < 2:
        ranking_note = "At least two different pack formats with fresh, in-stock observations are needed for a unit-rate highlight."
    elif any(row["_scope"] is None for row in eligible) or len({row["_scope"] for row in eligible}) != 1:
        ranking_note = ("The eligible observations do not share one known sample area. No sample unit-rate highlight is shown."
                        if reference.is_demo else "Delivery areas differ or are unverified. No lowest unit rate is highlighted; confirm the observations with each retailer.")
    else:
        minimum = min(row["_rate"] for row in eligible)
        lowest = [row for row in eligible if row["_rate"] == minimum]
        display = lowest[0]["standard_unit_price"]["display"]
        if any(row["_rate"] != minimum and row["standard_unit_price"]["display"] == display for row in eligible):
            ranking_note = "Rounded unit rates overlap. No lowest unit rate is highlighted at this display precision."
        else:
            ranking_available = True
            comparison_area = eligible[0]["delivery_area"]
            for row in lowest:
                row["is_lowest_unit_rate"] = True
            ranking_note = ("Lowest sample unit rate uses fictional observations in the same sample area."
                            if reference.is_demo else "Lowest comparable unit rate uses fresh, in-stock observations with evidence for the same delivery scope. Delivery and checkout charges are excluded.")
    def size_order(row):
        return (row["_size"], row["pack_count"], row["product_name"], row["retailer"] or "", row["listing_id"] or 0)
    if sort == "unit_price":
        rows.sort(key=lambda row: (not row["eligible"], row["_rate"] is None, row["_rate"] or 0, size_order(row)))
    elif sort == "pack_price":
        rows.sort(key=lambda row: (row["price"] is None, Decimal(row["price"] or 0), size_order(row)))
    else:
        rows.sort(key=size_order)
    for row in rows:
        for internal in ("_size", "_dimension", "_rate", "_scope"):
            del row[internal]
    dimensions = {dimension(p) for p in products}
    return {"source": "demo" if reference.is_demo else "live", "reference": product_descriptor(reference),
            "reference_slug": reference.slug, "as_of": as_of.isoformat(), "stale_hours": settings.PRICE_STALE_HOURS,
            "sort": sort, "rows": rows, "displayed_product_count": len(products),
            "alternative_pack_count": len(dimensions - {dimension(reference)}), "limited": bool(notice),
            "notice": notice, "ranking_available": ranking_available, "ranking_note": ranking_note,
            "comparison_area": comparison_area, "packaging_unspecified": bool(key is not None and not key[4])}
