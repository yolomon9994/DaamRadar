from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from catalog.models import Category, Retailer, RetailerListing
from catalog.services.catalog import decorate, get_product_queryset, search_catalog
from .serializers import CategorySerializer, HistorySerializer, ProductSerializer, RetailerSerializer
from .serializers import BasketQuerySerializer
from catalog.services.basket import estimate_basket


@method_decorator(never_cache, name="dispatch")
class BasketEstimate(APIView):
    def get(self, request):
        query = BasketQuerySerializer(data={"source": request.query_params.get("source", "demo"),
                                           "items": request.query_params.getlist("item")})
        query.is_valid(raise_exception=True)
        return Response(estimate_basket(query.validated_data["items"], query.validated_data["source"]))


class CatalogPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 48


class ProductList(ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        return search_catalog(self.request.query_params)


class ProductDetail(RetrieveAPIView):
    serializer_class = ProductSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return get_product_queryset()

    def get_object(self):
        return decorate(super().get_object())


class RetailerList(ListAPIView):
    queryset = Retailer.objects.all()
    serializer_class = RetailerSerializer


class CategoryList(ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ListingHistory(ListAPIView):
    serializer_class = HistorySerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        listing = get_object_or_404(RetailerListing, pk=self.kwargs["pk"])
        return listing.history.select_related("listing").all()
