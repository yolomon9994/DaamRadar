"""Factual, versioned context captured at the same time as a price observation."""
from catalog.services.list_transfer import product_descriptor


def observation_context(listing, *, product=None, retailer=None):
    product = product or listing.product
    retailer = retailer or listing.retailer
    return {"version": 1, "is_demo": listing.is_demo, "product_is_demo": product.is_demo,
            "product_id": product.pk, "product": product_descriptor(product),
            "retailer_id": retailer.pk, "retailer_slug": retailer.slug, "retailer_website": retailer.website,
            "external_id": listing.external_id, "original_title": listing.original_title, "url": listing.url,
            "currency": listing.currency, "availability": listing.availability,
            "delivery_area": listing.delivery_area, "delivery_area_key": listing.delivery_area_key,
            "area_evidence_url": listing.area_evidence_url,
            "area_verified_at": listing.area_verified_at.isoformat() if listing.area_verified_at else None,
            "area_is_verified": listing.area_is_verified}


def context_known(context):
    if not isinstance(context, dict) or type(context.get("version")) is not int or context["version"] != 1:
        return False
    if any(type(context.get(key)) is not bool for key in ("is_demo", "product_is_demo", "area_is_verified")):
        return False
    if any(type(context.get(key)) is not int or context[key] < 1 for key in ("product_id", "retailer_id")):
        return False
    strings = ("retailer_slug", "retailer_website", "external_id", "original_title", "url", "currency",
               "availability", "delivery_area", "delivery_area_key", "area_evidence_url")
    if any(not isinstance(context.get(key), str) for key in strings):
        return False
    if context["currency"] != "PKR" or context["availability"] not in {"in_stock", "out_of_stock", "unknown"}:
        return False
    if "area_verified_at" not in context or context["area_verified_at"] is not None and not isinstance(context["area_verified_at"], str):
        return False
    product = context.get("product")
    return (isinstance(product, dict) and all(isinstance(product.get(key), str)
            for key in ("name", "brand", "unit", "variant", "packaging", "gtin", "size"))
            and "quantity" in product and (product["quantity"] is None or isinstance(product["quantity"], str))
            and type(product.get("pack_count")) is int and product["pack_count"] > 0)


COMPARISON_KEYS = ("is_demo", "product_is_demo", "product_id", "product", "retailer_id", "retailer_slug",
                   "retailer_website", "external_id", "url", "currency", "delivery_area", "delivery_area_key", "area_is_verified")


def same_context(left, right):
    return (context_known(left) and context_known(right)
            and all(left[key] == right[key] for key in COMPARISON_KEYS))
