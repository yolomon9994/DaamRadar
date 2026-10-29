from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import Category, Product, Retailer, RetailerListing
from .services.catalog import SORTS, decorate, get_product_queryset, search_catalog, select_source
from .services.history import price_history_chart
from .services.price_changes import attach_price_changes
from .services.collection_health import can_view_collection_health
from .services.source_health import source_health


def home(request):
    source = select_source(request.GET)
    results = search_catalog({**request.GET.dict(), "source": source})
    page = Paginator(results, 12).get_page(request.GET.get("page"))
    attach_price_changes(page.object_list)
    return render(request, "catalog/home.html", {
        "page_obj": page, "categories": Category.objects.all(), "retailers": Retailer.objects.all(),
        "brands": Product.objects.filter(is_demo=source == "demo").exclude(brand="").values_list("brand", flat=True).distinct().order_by("brand"),
        "sorts": SORTS, "source": source, "query": request.GET.get("q", ""),
        "collected_count": RetailerListing.objects.filter(is_demo=False, product__is_demo=False).count(),
        "is_filtered": any(request.GET.get(k) for k in ["q", "category", "brand", "retailer"]),
    })


def product_detail(request, slug):
    product = decorate(get_object_or_404(get_product_queryset(), slug=slug))
    attach_price_changes([product])
    return render(request, "catalog/detail.html", {"product": product, "source": "demo" if product.is_demo else "live",
                                                  "history_chart": price_history_chart(product)})


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
