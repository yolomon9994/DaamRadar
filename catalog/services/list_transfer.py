"""Portable list identities and conservative, read-only local catalog resolution."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from catalog.matching.normalization import identify, normalize_text
from catalog.models import Product

CANDIDATE_LIMIT = 1000


def product_descriptor(product):
    return {"name": product.canonical_name, "brand": product.brand,
            "quantity": format(product.quantity, ".3f") if product.quantity is not None else None,
            "unit": product.unit, "pack_count": product.pack_count, "variant": product.variant,
            "packaging": product.packaging, "gtin": product.gtin, "size": product.size_label}


def normalized_descriptor(data):
    product = Product(canonical_name=data["name"], brand=data["brand"], quantity=data["quantity"],
                      unit=data["unit"], pack_count=data["pack_count"], variant=data["variant"],
                      packaging=data["packaging"], gtin=data["gtin"])
    return product_descriptor(product)


def identity_key(data):
    if data is None or data["quantity"] is None or not data["brand"] or not data["unit"]:
        return None
    title = identify(data["name"], data["brand"], data["gtin"])
    if title.quantity is not None and (title.quantity, title.unit, title.pack_count) != (
            Decimal(data["quantity"]), data["unit"], data["pack_count"]):
        return None
    if not title.name:
        return None
    # Use exact normalized identity, never fuzzy similarity or a cheapest substitute.
    return (title.brand, tuple(sorted(title.name.split())), str(data["quantity"]), data["unit"],
            data["pack_count"], tuple(sorted(title.variants | set(normalize_text(data["variant"]).split()))),
            tuple(sorted(title.packaging | set(normalize_text(data["packaging"]).split()))), data["gtin"])


def resolve_list(document):
    entries, source = document["items"], document["source"]
    catalog = Product.objects.filter(is_demo=source == "demo")
    hints = {product.slug: product for product in catalog.filter(slug__in=[item["slug"] for item in entries])}
    descriptors = [normalized_descriptor(item["product"]) if item["product"] is not None else None for item in entries]
    query = Q(pk__in=[])
    for descriptor in descriptors:
        if identity_key(descriptor) is not None:
            query |= Q(quantity=descriptor["quantity"], unit=descriptor["unit"], pack_count=descriptor["pack_count"])
    candidates = list(catalog.filter(query).order_by("pk")[:CANDIDATE_LIMIT + 1])
    overflow = len(candidates) > CANDIDATE_LIMIT
    identities = defaultdict(list)
    if not overflow:
        for product in candidates:
            key = identity_key(product_descriptor(product))
            if key is not None:
                identities[key].append(product)
    result = []
    for entry, descriptor in zip(entries, descriptors):
        hint = hints.get(entry["slug"])
        matched, status, reason = None, "unavailable", "No clear local catalog match. Kept as an unpriced item."
        key = identity_key(descriptor)
        if descriptor is None:
            reason = "No product identity was saved. Kept as an unpriced item."
        elif hint is not None and product_descriptor(hint) == descriptor:
            matched = hint
        elif key is not None:
            options = identities.get(key, [])
            if overflow:
                reason = "Too many compatible catalog candidates to resolve safely. Review this unpriced item."
            elif len(options) == 1:
                matched = options[0]
            elif len(options) > 1:
                status, reason = "ambiguous", "Multiple local products have this identity. Kept unpriced; choose a product manually."
        else:
            reason = "Brand, size or title needs review. No portable match was made; this item stays unpriced."
        if matched:
            status, reason = "matched", "Matched to the local catalog. Prices will be read from this database."
        result.append({"original_slug": entry["slug"], "quantity": entry["quantity"],
                       "imported_name": descriptor["name"] if descriptor else entry["slug"],
                       "slug": matched.slug if matched else None, "status": status, "reason": reason,
                       "product": product_descriptor(matched) if matched else descriptor})
    # Distinct source aliases cannot silently collapse into one local product/quantity.
    slugs = [row["slug"] for row in result if row["slug"]]
    if len(slugs) != len(set(slugs)):
        raise ValidationError("Multiple file entries resolve to the same product. Combine them in the file before importing.")
    return {"source": source, "items": result}
