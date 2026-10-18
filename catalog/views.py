from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Category, Product, Retailer
from .services.catalog import SORTS, decorate, get_product_queryset, search_catalog


def home(request):
    source = request.GET.get("source", "demo")
    source = source if source in {"demo", "live"} else "demo"
    results = search_catalog(request.GET)
    page = Paginator(results, 12).get_page(request.GET.get("page"))
    return render(request, "catalog/home.html", {
        "page_obj": page, "categories": Category.objects.all(), "retailers": Retailer.objects.all(),
        "brands": Product.objects.filter(is_demo=source == "demo").exclude(brand="").values_list("brand", flat=True).distinct().order_by("brand"),
        "sorts": SORTS, "source": source, "query": request.GET.get("q", ""),
        "is_filtered": any(request.GET.get(k) for k in ["q", "category", "brand", "retailer"]),
    })


def product_detail(request, slug):
    product = decorate(get_object_or_404(get_product_queryset(), slug=slug))
    return render(request, "catalog/detail.html", {"product": product, "source": "demo" if product.is_demo else "live"})


def sources(request):
    return render(request, "catalog/sources.html", {"retailers": Retailer.objects.all()})
