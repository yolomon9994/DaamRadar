from django.urls import path
from .views import CategoryList, ListingHistory, ProductDetail, ProductList, RetailerList

urlpatterns = [path("products/", ProductList.as_view(), name="api-products"),
               path("products/<slug:slug>/", ProductDetail.as_view(), name="api-product"),
               path("retailers/", RetailerList.as_view()), path("categories/", CategoryList.as_view()),
               path("listings/<int:pk>/history/", ListingHistory.as_view(), name="api-history")]
