from django.urls import path
from . import views

urlpatterns = [path("", views.home, name="home"), path("products/<slug:slug>/", views.product_detail, name="product-detail"),
               path("products/<slug:slug>/pack-comparison/", views.compare_packs, name="pack-comparison"),
               path("shopping-list/", views.shopping_list, name="shopping-list"),
               path("watchlist/", views.watchlist, name="watchlist"),
               path("sources/", views.sources, name="sources")]
