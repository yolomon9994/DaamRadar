from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from catalog.models import Category, Retailer, RetailerListing
from catalog.services.basket import estimate_basket
from catalog.services.catalog import decorate, get_product_queryset, search_catalog
from catalog.services.list_transfer import resolve_list
from catalog.services.watchlist import check_targets
from catalog.services.price_changes import attach_price_changes
from .serializers import (BasketQuerySerializer, CategorySerializer, HistorySerializer,
                          ListTransferSerializer, ProductSerializer, RetailerSerializer, WatchlistQuerySerializer)


@method_decorator(never_cache, name="dispatch")
class WatchlistCheck(APIView):
    def get(self, request):
        query = WatchlistQuerySerializer(data={"source": request.query_params.get("source", "demo"),
                                             "items": request.query_params.getlist("item")})
        query.is_valid(raise_exception=True)
        return Response(check_targets(query.validated_data["items"], query.validated_data["source"]))


@method_decorator(never_cache, name="dispatch")
class BasketEstimate(APIView):
    def get(self, request):
        query = BasketQuerySerializer(data={"source": request.query_params.get("source", "demo"),
                                           "items": request.query_params.getlist("item"),
                                           "unresolved": request.query_params.getlist("unresolved"),
                                           **({"budget": request.query_params["budget"]} if "budget" in request.query_params else {})})
        query.is_valid(raise_exception=True)
        return Response(estimate_basket(query.validated_data["items"], query.validated_data["source"],
                                        query.validated_data["unresolved"], query.validated_data["budget"]))


@method_decorator(never_cache, name="dispatch")
class ListImportPreview(APIView):
    # Anonymous read-only computation: ignore account/session cookies and persist nothing.
    authentication_classes = []
    parser_classes = [JSONParser]

    def post(self, request):
        maximum = 256 * 1024
        if int(request.META.get("CONTENT_LENGTH") or 0) > maximum or len(request.body) > maximum:
            return Response({"detail": "List files must be at most 256 KiB."}, status=413)
        document = ListTransferSerializer(data=request.data)
        document.is_valid(raise_exception=True)
        return Response(resolve_list(document.validated_data))


class CatalogPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 48


class ProductList(ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        return search_catalog(self.request.query_params)

    def get_serializer(self, *args, **kwargs):
        # Load history only for the serialized page, in one bounded query.
        if kwargs.get("many") and args:
            attach_price_changes(args[0])
        return super().get_serializer(*args, **kwargs)


class ProductDetail(RetrieveAPIView):
    serializer_class = ProductSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return get_product_queryset()

    def get_object(self):
        product = decorate(super().get_object())
        attach_price_changes([product])
        return product


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
