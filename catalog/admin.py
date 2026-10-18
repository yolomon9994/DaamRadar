from django.contrib import admin
from .models import Category, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["canonical_name", "brand", "category", "is_demo"]
    list_filter = ["is_demo", "category"]
    search_fields = ["canonical_name", "brand", "gtin"]

@admin.register(RetailerListing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ["original_title", "retailer", "current_price", "availability", "last_checked", "is_demo"]
    list_filter = ["retailer", "is_demo", "availability"]
    search_fields = ["original_title"]
    list_select_related = ["retailer"]

admin.site.register([Retailer, Category, PriceHistory, ScrapeRun])
admin.site.site_header = "DaamRadar administration"
