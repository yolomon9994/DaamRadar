"""Bounded, read-only identity diagnostics. Findings never authorize a merge."""
from collections import Counter, defaultdict
from itertools import combinations
import re
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from catalog.matching.normalization import VARIANT_WORDS, identify, match_score, normalize_text
from catalog.models import Product, RetailerListing

PRODUCT_LIMIT = 1000
LISTING_LIMIT = 5000
PAIR_LIMIT = 5000
FINDING_LIMIT = 1000
REFERENCE_LIMIT = 20
CHECKS = {
    "missing_size": "Missing pack size",
    "invalid_contents": "Invalid pack contents",
    "missing_brand": "Missing brand",
    "missing_category": "Missing category",
    "no_listings": "No consistent-catalog listings",
    "canonical_conflict": "Canonical title / metadata conflict",
    "canonical_uncertain": "Canonical identity needs review",
    "potential_duplicate": "Possible duplicate products",
    "barcode_conflict": "Conflicting barcodes for one identity",
    "shared_barcode": "Shared barcode needs review",
    "barcode_format": "Barcode format needs review",
    "source_mismatch": "Listing / product catalog mismatch",
    "listing_conflict": "Listing / product identity conflict",
    "listing_uncertain": "Listing match needs review",
    "similar_products": "Similar product identities need review",
}


def can_view_catalog_quality(user):
    return all(user.has_perm(f"catalog.view_{model}") or user.has_perm(f"catalog.change_{model}")
               for model in ("product", "retailerlisting", "retailer"))


def product_ref(product):
    return {"id": product.pk, "name": product.canonical_name, "slug": product.slug,
            "source": "demo" if product.is_demo else "live"}


def listing_ref(listing):
    return {"id": listing.pk, "title": listing.original_title, "retailer": listing.retailer.name,
            "product_id": listing.product_id, "source": "demo" if listing.is_demo else "live"}


def structured_variants(value):
    return identify(value).variants | (set(normalize_text(value).split()) - VARIANT_WORDS)


def product_identity(product):
    title = identify(product.canonical_name, product.brand)
    inferred = identify(product.canonical_name)
    problems, uncertain = [], []
    contents_valid = (product.quantity is not None and product.quantity > 0 and product.unit in {"ml", "g", "pc"}
                      and 1 <= product.pack_count <= 32767
                      and (product.unit != "pc" or product.quantity == product.quantity.to_integral_value()))
    if inferred.brand and title.brand != inferred.brand:
        problems.append("The brand named in the canonical title differs from the stored brand.")
    if contents_valid and title.quantity is not None and (
            title.quantity, title.unit, title.pack_count) != (product.quantity, product.unit, product.pack_count):
        problems.append("The canonical title's size/count differs from the stored contents.")
    if contents_valid and title.quantity is None:
        uncertain.append("The canonical title has no single parseable pack size/count to verify stored contents.")
    variants = structured_variants(product.variant)
    packaging = set(normalize_text(product.packaging).split())
    if title.variants and variants and title.variants != variants:
        problems.append("Explicit title variants differ from structured variant metadata.")
    if title.packaging and packaging and title.packaging != packaging:
        problems.append("Explicit title packaging differs from structured packaging metadata.")
    if not title.name:
        uncertain.append("The current normalizer cannot establish a product name from the canonical title.")
    if not product.brand.strip() and title.brand:
        uncertain.append("A brand is recognized in the title but is not stored explicitly.")
    key = None
    if contents_valid and title.brand and title.name and not problems and not uncertain and product.brand.strip():
        key = (title.brand, product.quantity, product.unit, product.pack_count,
               tuple(sorted(title.variants | variants)), tuple(sorted(title.packaging | packaging)),
               tuple(sorted(title.name.split())))
    return title, key, problems, uncertain, contents_valid


def catalog_quality(*, source="live", severity="all", check="all", now=None):
    if source not in {"live", "demo"} or severity not in {"all", "error", "warning"} or check not in {"all", *CHECKS}:
        raise ValueError("Choose a supported source, severity and check.")
    demo = source == "demo"
    product_query = Product.objects.filter(is_demo=demo).order_by("pk")
    listing_query = RetailerListing.objects.filter(Q(is_demo=demo) | Q(product__is_demo=demo)).order_by("pk")
    product_count, listing_count = product_query.count(), listing_query.count()
    consistent = RetailerListing.objects.filter(product_id=OuterRef("pk"), is_demo=demo)
    products = list(product_query.annotate(has_listing=Exists(consistent))[:PRODUCT_LIMIT])
    listings = list(listing_query.select_related("product", "retailer")[:LISTING_LIMIT])
    findings = []

    def add(code, level, detail, members=(), offers=(), **evidence):
        findings.append({"code": code, "severity": level, "title": CHECKS[code], "detail": detail,
                         "products": [product_ref(p) for p in members[:REFERENCE_LIMIT]],
                         "listings": [listing_ref(o) for o in offers[:REFERENCE_LIMIT]],
                         "product_count": len(members), "listing_count": len(offers),
                         "references_limited": len(members) > REFERENCE_LIMIT or len(offers) > REFERENCE_LIMIT,
                         "evidence": evidence})

    keys, identities = {}, {}
    exact, barcodes, buckets = defaultdict(list), defaultdict(list), defaultdict(list)
    for product in products:
        title, key, problems, uncertain, valid = product_identity(product)
        identities[product.pk], keys[product.pk] = title, key
        if product.quantity is None and not product.unit:
            add("missing_size", "warning", "Pack contents are unknown; verify the source instead of guessing a size.", [product])
        elif not valid:
            add("invalid_contents", "error", "Quantity/unit/count are inconsistent, unsupported, nonpositive or fractional for piece counts.", [product])
        if not product.brand.strip():
            add("missing_brand", "warning", "No explicit canonical brand is stored. A title alias alone is not a reviewed brand.", [product])
        if product.category_id is None:
            add("missing_category", "warning", "No grocery category is assigned.", [product])
        if not product.has_listing:
            add("no_listings", "warning", "No listing with the same Demo/Collected flag is attached to this product.", [product])
        if problems:
            add("canonical_conflict", "error", " ".join(problems), [product],
                stored_contents=f"{product.pack_count} x {product.quantity} {product.unit}",
                parsed_contents=f"{title.pack_count} x {title.quantity} {title.unit}")
        if uncertain:
            add("canonical_uncertain", "warning", " ".join(uncertain), [product])
        if product.gtin:
            barcodes[product.gtin].append(product)
            if not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", product.gtin):
                add("barcode_format", "warning", "The stored barcode is not an 8-, 12-, 13- or 14-digit value. No checksum or authenticity claim is made.", [product])
        if key is not None:
            exact[key].append(product)
            buckets[key[:-1]].append(product)
    for members in exact.values():
        if len(members) < 2:
            continue
        known = {p.gtin for p in members if p.gtin}
        if len(known) > 1:
            add("barcode_conflict", "error", "One normalized pack identity has different stored barcodes. Do not merge without source evidence.", members,
                barcodes=", ".join(sorted(known)[:REFERENCE_LIMIT]))
        else:
            add("potential_duplicate", "warning", "Distinct product records share a normalized exact pack identity. This is a review candidate, not permission to merge histories.", members)
    for barcode, members in barcodes.items():
        if len(members) > 1 and (any(keys[p.pk] is None for p in members) or len({keys[p.pk] for p in members}) > 1):
            known_keys = [keys[p.pk][:-1] for p in members if keys[p.pk] is not None]
            add("shared_barcode", "error" if len(set(known_keys)) > 1 else "warning",
                "The same barcode is stored on different or unverifiable product identities. Verify pack/brand/variant and the original source.", members, barcode=barcode)

    for listing in listings:
        product = listing.product
        if listing.is_demo != product.is_demo:
            add("source_mismatch", "error", "The listing and its product belong to different catalogs. Their observations must not be treated as consistent catalog coverage.", [product], [listing])
            continue
        canonical, key, problems, uncertain, valid = product_identity(product)
        title, inferred = identify(listing.original_title, product.brand), identify(listing.original_title)
        conflicts, doubts = [], []
        if inferred.brand and canonical.brand and inferred.brand != canonical.brand:
            conflicts.append("The listing title names a different known brand.")
        if valid and title.quantity is not None and (title.quantity, title.unit, title.pack_count) != (
                product.quantity, product.unit, product.pack_count):
            conflicts.append("The listing's parsed size/count differs from the canonical contents.")
        expected_variants = canonical.variants | structured_variants(product.variant)
        expected_packaging = canonical.packaging | set(normalize_text(product.packaging).split())
        if title.variants and title.variants != expected_variants:
            conflicts.append("Explicit listing variants differ from the canonical identity.")
        elif expected_variants and not title.variants:
            doubts.append("The listing title does not establish the stored variant.")
        if title.packaging and expected_packaging and title.packaging != expected_packaging:
            conflicts.append("Explicit listing packaging differs from the canonical identity.")
        elif title.packaging != expected_packaging:
            doubts.append("Packaging is explicit on only one side of this match.")
        if key is None or title.quantity is None or not inferred.brand or not title.name:
            doubts.append("A complete brand, size and name identity cannot be verified on both sides.")
        score = match_score(canonical, title)
        if tuple(sorted(canonical.name.split())) != tuple(sorted(title.name.split())):
            doubts.append("Normalized product names differ; a fuzzy match is not proof of equivalence.")
        if conflicts:
            add("listing_conflict", "error", " ".join(conflicts), [product], [listing],
                stored_contents=f"{product.pack_count} x {product.quantity} {product.unit}",
                parsed_contents=f"{title.pack_count} x {title.quantity} {title.unit}")
        elif doubts:
            add("listing_uncertain", "warning", " ".join(doubts), [product], [listing], name_similarity=f"{score:.1f}")

    pair_total = sum(len(group) * (len(group) - 1) // 2 for group in buckets.values())
    pairs_checked = 0
    for group in buckets.values():
        for left, right in combinations(group, 2):
            if pairs_checked >= PAIR_LIMIT:
                break
            pairs_checked += 1
            if keys[left.pk] == keys[right.pk] or (left.gtin and right.gtin and left.gtin != right.gtin):
                continue
            score = match_score(identities[left.pk], identities[right.pk])
            if 80 <= score < 100:
                add("similar_products", "warning", "Hard pack/brand/variant/packaging guards agree, but product names differ. Inspect sources before considering a duplicate; similarity is not confidence.",
                    [left, right], name_similarity=f"{score:.1f}")
        if pairs_checked >= PAIR_LIMIT:
            break
    findings.sort(key=lambda row: (0 if row["severity"] == "error" else 1, row["code"],
                                  [p["id"] for p in row["products"]], [o["id"] for o in row["listings"]]))
    selected = [row for row in findings if (severity == "all" or row["severity"] == severity) and (check == "all" or row["code"] == check)]
    limits = {"products": product_count > PRODUCT_LIMIT, "listings": listing_count > LISTING_LIMIT,
              "pairs": pair_total > PAIR_LIMIT, "findings": len(selected) > FINDING_LIMIT}
    return {"version": 1, "source": source, "as_of": timezone.localtime(now or timezone.now(), ZoneInfo("Asia/Karachi")).isoformat(),
            "filters": {"severity": severity, "check": check},
            "counts": {"products_total": product_count, "products_scanned": len(products),
                       "listings_total": listing_count, "listings_scanned": len(listings),
                       "pairs_possible": pair_total, "pairs_checked": pairs_checked,
                       "findings_evaluated": len(findings), "findings_selected": len(selected),
                       "findings_returned": min(len(selected), FINDING_LIMIT)},
            "by_severity": dict(Counter(row["severity"] for row in findings)),
            "by_check": dict(sorted(Counter(row["code"] for row in findings).items())),
            "limits": limits, "complete": not any(limits.values()),
            "bounds": {"products": PRODUCT_LIMIT, "listings": LISTING_LIMIT, "pairs": PAIR_LIMIT,
                       "findings": FINDING_LIMIT, "references_per_finding": REFERENCE_LIMIT},
            "findings": selected[:FINDING_LIMIT]}
