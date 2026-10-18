from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination

from catalog.models import Category, Retailer, RetailerListing
from catalog.services.catalog import decorate, get_product_queryset, search_catalog
from .serializers import CategorySerializer, HistorySerializer, ProductSerializer, RetailerSerializer


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
