from django.urls import path
from .views import BasketEstimate, CategoryList, ListImportPreview, ListingHistory, PackComparison, ProductDetail, ProductList, RetailerList, SearchSuggestions, WatchlistCheck

urlpatterns = [path("products/", ProductList.as_view(), name="api-products"),
               path("search-suggestions/", SearchSuggestions.as_view(), name="api-search-suggestions"),
               path("basket/", BasketEstimate.as_view(), name="api-basket"),
               path("watchlist/", WatchlistCheck.as_view(), name="api-watchlist"),
               path("shopping-list/preview/", ListImportPreview.as_view(), name="api-list-import-preview"),
               path("products/<slug:slug>/", ProductDetail.as_view(), name="api-product"),
               path("products/<slug:slug>/pack-comparison/", PackComparison.as_view(), name="api-pack-comparison"),
               path("retailers/", RetailerList.as_view()), path("categories/", CategoryList.as_view()),
               path("listings/<int:pk>/history/", ListingHistory.as_view(), name="api-history")]
