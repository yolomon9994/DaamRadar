from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Product, Retailer, RetailerListing
from .services.catalog import SORTS, decorate, get_product_queryset, search_catalog, select_source
from .services.history import price_history_chart
from .services.delivery_review import DELIVERY_REVIEWS


def home(request):
    source = select_source(request.GET)
    results = search_catalog({**request.GET.dict(), "source": source})
    page = Paginator(results, 12).get_page(request.GET.get("page"))
    return render(request, "catalog/home.html", {
        "page_obj": page, "categories": Category.objects.all(), "retailers": Retailer.objects.all(),
        "brands": Product.objects.filter(is_demo=source == "demo").exclude(brand="").values_list("brand", flat=True).distinct().order_by("brand"),
        "sorts": SORTS, "source": source, "query": request.GET.get("q", ""),
        "collected_count": RetailerListing.objects.filter(is_demo=False, product__is_demo=False).count(),
        "is_filtered": any(request.GET.get(k) for k in ["q", "category", "brand", "retailer"]),
    })


def product_detail(request, slug):
    product = decorate(get_object_or_404(get_product_queryset(), slug=slug))
    return render(request, "catalog/detail.html", {"product": product, "source": "demo" if product.is_demo else "live",
                                                  "history_chart": price_history_chart(product)})


def sources(request):
    retailers = list(Retailer.objects.annotate(collected_count=Count("listings", filter=Q(listings__is_demo=False, listings__product__is_demo=False))))
    for retailer in retailers:
        retailer.delivery_review = DELIVERY_REVIEWS.get(retailer.slug)
    return render(request, "catalog/sources.html", {
        "retailers": retailers,
        "collected_count": RetailerListing.objects.filter(is_demo=False, product__is_demo=False).count(),
    })
