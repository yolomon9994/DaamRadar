from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.utils import timezone

from .models import Category, Product, Retailer, RetailerListing
from .services.catalog import SORTS, decorate, get_product_queryset, search_catalog, select_source
from .services.history import price_history_chart
from .services.price_changes import attach_price_changes
from .services.collection_health import can_view_collection_health
from .services.source_health import source_health
from .search_filters import OfferFilterForm, filters_active
from .services.pack_comparison import SORTS as PACK_SORTS, pack_comparison
from .services.snapshots import snapshot_metadata


@never_cache
@require_safe
def home(request):
    as_of = timezone.now()
    source = select_source(request.GET)
    params = {**request.GET.dict(), "source": source}
    form = OfferFilterForm(params)
    valid = form.is_valid()
    active = valid and filters_active(form.cleaned_data)
    results = search_catalog(params, filters=form.cleaned_data, now=as_of) if valid else []
    empty_offer_filters = False
    if valid and active and not results:
        relaxed = {key: value for key, value in params.items() if key not in form.fields}
        empty_offer_filters = bool(search_catalog(relaxed, now=as_of))
    page = Paginator(results, 12).get_page(request.GET.get("page"))
    attach_price_changes(page.object_list)
    snapshot = snapshot_metadata((o.last_checked for product in page.object_list for o in product.offers), now=as_of)
    return render(request, "catalog/home.html", {
        "page_obj": page, "categories": Category.objects.all(), "retailers": Retailer.objects.all(),
        "snapshot": snapshot,
        "brands": Product.objects.filter(is_demo=source == "demo").exclude(brand="").values_list("brand", flat=True).distinct().order_by("brand"),
        "sorts": SORTS, "source": source, "query": request.GET.get("q", "").strip()[:150],
        "offer_filter_form": form, "offer_filters_active": active, "filter_error": not valid,
        "empty_offer_filters": empty_offer_filters,
        "preserved_filters": [(key, params[key]) for key in ("category", "retailer", "brand", "sort", "fresh", "in_stock", "min_price", "max_price") if params.get(key)],
        "collected_count": RetailerListing.objects.filter(is_demo=False, product__is_demo=False).count(),
        "is_filtered": any(request.GET.get(k) for k in ["q", "category", "brand", "retailer", "fresh", "in_stock", "min_price", "max_price"]),
    }, status=200 if valid else 400)


@never_cache
@require_safe
def product_detail(request, slug):
    product = decorate(get_object_or_404(get_product_queryset(), slug=slug), now=timezone.now())
    attach_price_changes([product])
    return render(request, "catalog/detail.html", {"product": product, "source": "demo" if product.is_demo else "live",
                                                  "snapshot": product.snapshot,
                                                  "history_chart": price_history_chart(product)})


@never_cache
@require_safe
def compare_packs(request, slug):
    product = get_object_or_404(Product, slug=slug)
    sort = request.GET.get("sort", "size")
    error = "Choose a supported pack comparison sort." if sort not in PACK_SORTS else ""
    data = pack_comparison(product, sort=sort) if not error else {"source": "demo" if product.is_demo else "live"}
    return render(request, "catalog/pack_comparison.html", {**data, "product": product, "sorts": PACK_SORTS,
                                                          "sort_error": error}, status=400 if error else 200)


@never_cache
@require_safe
def sources(request):
    health = source_health()
    operator = request.user.is_active and request.user.is_staff and can_view_collection_health(request.user)
    return render(request, "catalog/sources.html", {
        **health, "collected_count": health["totals"]["live"],
        "show_collection_controls": operator,
        "can_refresh_prices": operator and request.user.has_perm("catalog.run_price_refresh"),
        "can_import_catalog": operator and request.user.has_perm("catalog.import_reviewed_catalog"),
    })


def shopping_list(request):
    return render(request, "catalog/shopping_list.html", {"source": select_source(request.GET)})


def watchlist(request):
    return render(request, "catalog/watchlist.html", {"source": select_source(request.GET)})
