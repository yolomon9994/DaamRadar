from rest_framework import serializers
from catalog.models import Category, PriceHistory, Product, Retailer, RetailerListing


class RetailerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Retailer
        fields = ["id", "name", "slug", "website", "status", "collection_enabled", "access_notes"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon"]


class ListingSerializer(serializers.ModelSerializer):
    retailer = serializers.CharField(source="retailer.name")
    is_stale = serializers.BooleanField(read_only=True)
    is_best = serializers.BooleanField(read_only=True, default=False)
    area_is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = RetailerListing
        fields = ["id", "retailer", "original_title", "url", "current_price", "currency", "availability", "last_checked", "delivery_area", "delivery_area_key", "area_evidence_url", "area_verified_at", "area_is_verified", "is_demo", "is_stale", "is_best"]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", default=None)
    size = serializers.CharField(source="size_label")
    best_price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, read_only=True)
    has_mixed_areas = serializers.BooleanField(read_only=True)
    has_comparison = serializers.BooleanField(read_only=True)
    has_unverified_areas = serializers.BooleanField(read_only=True)
    comparison_area = serializers.CharField(read_only=True)
    listings = ListingSerializer(source="offers", many=True, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "slug", "canonical_name", "brand", "category", "quantity", "unit", "pack_count", "size", "image", "is_demo", "best_price", "has_mixed_areas", "has_unverified_areas", "has_comparison", "comparison_area", "listings"]


class HistorySerializer(serializers.ModelSerializer):
    is_demo = serializers.BooleanField(source="listing.is_demo")

    class Meta:
        model = PriceHistory
        fields = ["price", "checked_at", "is_demo"]
