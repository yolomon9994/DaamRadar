from django.urls import path
from .views import BasketEstimate, CategoryList, ListImportPreview, ListingHistory, ProductDetail, ProductList, RetailerList

urlpatterns = [path("products/", ProductList.as_view(), name="api-products"),
               path("basket/", BasketEstimate.as_view(), name="api-basket"),
               path("shopping-list/preview/", ListImportPreview.as_view(), name="api-list-import-preview"),
               path("products/<slug:slug>/", ProductDetail.as_view(), name="api-product"),
               path("retailers/", RetailerList.as_view()), path("categories/", CategoryList.as_view()),
               path("listings/<int:pk>/history/", ListingHistory.as_view(), name="api-history")]
