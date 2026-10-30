from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone
from rapidfuzz.fuzz import WRatio

from catalog.matching.normalization import identify, normalize_text
from catalog.models import Product, RetailerListing
from catalog.search_filters import filters_active, offer_filters
from catalog.services.unit_pricing import standard_unit_price
from catalog.services.snapshots import snapshot_metadata

SORTS = {"relevance": "Recommended", "price_asc": "Lowest price", "price_desc": "Highest price"}


def select_source(params):
    if params.get("source") in {"demo", "live"}:
        return params["source"]
    return "live" if RetailerListing.objects.filter(is_demo=False, product__is_demo=False).exists() else "demo"


def decorate(product, *, now=None):
    product.offers = list(product.listings.all())
    # A shared label or retailer-wide delivery claim does not verify a price's area.
    as_of = now if now is not None else timezone.now()
    product.snapshot = snapshot_metadata((o.last_checked for o in product.offers), now=as_of)
    cutoff = as_of - timedelta(hours=settings.PRICE_STALE_HOURS)
    eligible = [o for o in product.offers if o.is_demo == product.is_demo
                and o.availability == "in_stock" and cutoff <= o.last_checked <= as_of]
    verified = {o.id: o.area_is_verified for o in product.offers}
    areas = {o.delivery_area_key if verified[o.id] else o.delivery_area for o in eligible}
    product.has_mixed_areas = len(areas) > 1
    product.has_unverified_areas = not product.is_demo and any(not verified[o.id] for o in product.offers)
    if product.is_demo:
        area_known = len(areas) == 1 and all(area and "unverified" not in area.lower() for area in areas)
    else:
        area_known = len(areas) == 1 and all(verified[o.id] for o in eligible)
    product.has_comparison = len({o.retailer_id for o in eligible}) > 1 and area_known
    product.comparison_area = eligible[0].delivery_area if product.has_comparison and not product.is_demo else ""
    product.best_price = min((o.current_price for o in eligible), default=None)
    product.standard_unit_price = standard_unit_price(product, product.best_price)
    product.best_ids = {o.id for o in eligible if o.current_price == product.best_price} if product.has_comparison else set()
    product.offer_count = len(product.offers)
    product.savings = (max(o.current_price for o in eligible) - product.best_price) if product.has_comparison else Decimal("0")
    product.sort_price = product.best_price
    for offer in product.offers:
        offer.is_best = offer.id in product.best_ids
        offer.check_time_is_future = offer.last_checked > as_of
        offer.standard_unit_price = standard_unit_price(product, offer.current_price)
    return product


def search_catalog(params, *, filters=None, now=None, decorate_results=True):
    filters = offer_filters(params) if filters is None else filters
    as_of = now if now is not None else timezone.now()
    cutoff = as_of - timedelta(hours=settings.PRICE_STALE_HOURS)
    query = params.get("q", "").strip()[:150]
    source = select_source(params)
    offers = RetailerListing.objects.filter(is_demo=source == "demo").select_related("retailer").order_by("current_price", "retailer__name")
    if params.get("retailer"):
        offers = offers.filter(retailer__slug=params["retailer"])
    matching_offers = offers
    if filters["fresh"]:
        matching_offers = matching_offers.filter(last_checked__gte=cutoff, last_checked__lte=as_of)
    if filters["in_stock"]:
        matching_offers = matching_offers.filter(availability="in_stock")
    if filters["min_price"] is not None:
        matching_offers = matching_offers.filter(current_price__gte=filters["min_price"])
    if filters["max_price"] is not None:
        matching_offers = matching_offers.filter(current_price__lte=filters["max_price"])
    products = Product.objects.filter(is_demo=source == "demo", listings__in=matching_offers).distinct().select_related("category")
    if params.get("category"):
        products = products.filter(category__slug=params["category"])
    if params.get("brand"):
        products = products.filter(brand__iexact=params["brand"])
    if query:
        # Bound fuzzy work with a database candidate stage; never make network calls here.
        words = [w for w in normalize_text(query).split() if len(w) > 2][:8]
        candidate_query = Q()
        for word in words:
            candidate_query |= Q(canonical_name__icontains=word[:3]) | Q(brand__icontains=word[:3])
        if words:
            candidates = products.filter(candidate_query)
            if not candidates.exists():
                candidates = products  # Bounded spelling fallback for a small local catalog.
        else:
            candidates = products
        products = candidates
    if decorate_results:
        products = products.prefetch_related(Prefetch("listings", queryset=offers))
    found = []
    normalized_query = normalize_text(query)
    query_identity = identify(query)
    for product in products.order_by("canonical_name")[:1000]:
        title = normalize_text(f"{product.canonical_name} {product.brand}")
        score = WRatio(normalized_query, title) if query else 100
        if query and normalized_query not in title and score < 68:
            continue
        if query_identity.brand and query_identity.brand != identify(product.canonical_name, product.brand).brand:
            continue
        if query_identity.quantity is not None and (query_identity.quantity != product.quantity or query_identity.unit != product.unit or query_identity.pack_count != product.pack_count):
            continue
        if query_identity.variants and not query_identity.variants.issubset(identify(product.canonical_name).variants):
            continue
        if query_identity.packaging and query_identity.packaging != identify(product.canonical_name).packaging:
            continue
        if decorate_results:
            product = decorate(product, now=as_of)
            product.has_offer_filters = filters_active(filters)
            for offer in product.offers:
                offer.matches_offer_filters = (all((
                    not filters["fresh"] or cutoff <= offer.last_checked <= as_of,
                    not filters["in_stock"] or offer.availability == "in_stock",
                    filters["min_price"] is None or offer.current_price >= filters["min_price"],
                    filters["max_price"] is None or offer.current_price <= filters["max_price"],
                )) if product.has_offer_filters else None)
        product.relevance = score
        found.append(product)
    sort = params.get("sort", "relevance")
    if decorate_results and sort in {"price_asc", "price_desc"}:
        found.sort(key=lambda p: (p.sort_price is None, (p.sort_price or Decimal(0)) * (-1 if sort == "price_desc" else 1), p.canonical_name))
    else:
        found.sort(key=lambda p: (-p.relevance, p.canonical_name))
    return found


def search_suggestions(params):
    filters = offer_filters(params)
    if len(params.get("q", "").strip()) < 2:
        return []
    # Same bounded matching, identity/size guards and offer filters as full search.
    return search_catalog({**{key: value for key, value in params.items()}, "sort": "relevance"}, filters=filters, decorate_results=False)[:6]


def get_product_queryset():
    return Product.objects.select_related("category").prefetch_related(
        Prefetch("listings", queryset=RetailerListing.objects.select_related("retailer")))
