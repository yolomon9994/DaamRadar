import re
from decimal import Decimal

from rest_framework import serializers
from catalog.models import Category, PriceHistory, Product, Retailer, RetailerListing
from catalog.services.observations import context_known


class BasketQuerySerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=["demo", "live"], default="demo")
    budget = serializers.RegexField(r"\A(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?\Z", required=False, default=None, trim_whitespace=False)
    items = serializers.ListField(child=serializers.CharField(trim_whitespace=False), max_length=50, default=list)
    unresolved = serializers.ListField(child=serializers.RegexField(r"\A[-a-zA-Z0-9_]{1,280}\Z"), max_length=50, default=list)

    def validate(self, data):
        if not set(data["unresolved"]).issubset({slug for slug, _ in data["items"]}):
            raise serializers.ValidationError("Unresolved items must belong to this list.")
        return data

    def validate_budget(self, value):
        return Decimal(value) if value is not None else None

    def validate_items(self, values):
        result, seen = [], set()
        for value in values:
            if not re.fullmatch(r"[-a-zA-Z0-9_]{1,280}:[1-9][0-9]?", value):
                raise serializers.ValidationError("Use product-slug:quantity, with a quantity from 1 to 99.")
            slug, quantity = value.rsplit(":", 1)
            if slug in seen:
                raise serializers.ValidationError("Each product can appear only once.")
            seen.add(slug)
            result.append((slug, int(quantity)))
        return result


class WatchlistQuerySerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=["demo", "live"], default="demo")
    items = serializers.ListField(child=serializers.CharField(trim_whitespace=False), max_length=50, default=list)

    def validate_items(self, values):
        result, seen = [], set()
        for value in values:
            if not re.fullmatch(r"[-a-zA-Z0-9_]{1,280}:(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?", value):
                raise serializers.ValidationError("Use product-slug:target-price, in PKR with at most two decimal places.")
            slug, target = value.rsplit(":", 1)
            if slug in seen or Decimal(target) < Decimal("0.01"):
                raise serializers.ValidationError("Use each product once and a target from 0.01 to 9999999999.99.")
            seen.add(slug)
            result.append((slug, Decimal(target)))
        return result


class StrictDocumentSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": [
                "Unexpected fields in this list file. Use a DaamRadar list export without prices."]})
        return super().to_internal_value(data)


class StrictIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class TransferProductSerializer(StrictDocumentSerializer):
    name = serializers.CharField(max_length=255, trim_whitespace=False)
    brand = serializers.CharField(max_length=100, allow_blank=True, trim_whitespace=False)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"), allow_null=True)
    unit = serializers.ChoiceField(choices=["", "ml", "g", "pc"])
    pack_count = StrictIntegerField(min_value=1, max_value=32767)
    variant = serializers.CharField(max_length=120, allow_blank=True, trim_whitespace=False)
    packaging = serializers.CharField(max_length=40, allow_blank=True, trim_whitespace=False)
    gtin = serializers.CharField(max_length=14, allow_blank=True, trim_whitespace=False)
    size = serializers.CharField(max_length=80, required=False)  # Display hint only; recomputed, never trusted.

    def validate(self, data):
        if (data["quantity"] is None) != (data["unit"] == ""):
            raise serializers.ValidationError("Quantity and its normalized unit must both be known, or both unspecified.")
        return data


class TransferItemSerializer(StrictDocumentSerializer):
    slug = serializers.RegexField(r"\A[-a-zA-Z0-9_]{1,280}\Z")
    quantity = StrictIntegerField(min_value=1, max_value=99)
    product = TransferProductSerializer(allow_null=True)


class ListTransferSerializer(StrictDocumentSerializer):
    format = serializers.ChoiceField(choices=["daamradar-shopping-list"])
    version = StrictIntegerField(min_value=1, max_value=1)
    source = serializers.ChoiceField(choices=["demo", "live"])
    exported_at = serializers.DateTimeField()
    items = TransferItemSerializer(many=True, allow_empty=False, max_length=50)

    def validate_items(self, items):
        if len({item["slug"] for item in items}) != len(items):
            raise serializers.ValidationError("Duplicate product references are not allowed in a list file.")
        return items


class RetailerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Retailer
        fields = ["id", "name", "slug", "website", "status", "collection_enabled", "access_notes"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon"]


class ListingSerializer(serializers.ModelSerializer):
    check_time_is_future = serializers.BooleanField(read_only=True, default=False)
    matches_offer_filters = serializers.BooleanField(read_only=True, allow_null=True, default=None)
    retailer = serializers.CharField(source="retailer.name")
    is_stale = serializers.BooleanField(read_only=True)
    is_best = serializers.BooleanField(read_only=True, default=False)
    area_is_verified = serializers.BooleanField(read_only=True)
    standard_unit_price = serializers.JSONField(read_only=True, default=None)
    price_change = serializers.JSONField(read_only=True, default=None)

    class Meta:
        model = RetailerListing
        fields = ["id", "retailer", "original_title", "url", "current_price", "standard_unit_price", "price_change", "currency", "availability", "last_checked", "delivery_area", "delivery_area_key", "area_evidence_url", "area_verified_at", "area_is_verified", "is_demo", "is_stale", "is_best", "matches_offer_filters", "check_time_is_future"]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", default=None)
    size = serializers.CharField(source="size_label")
    best_price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, read_only=True)
    standard_unit_price = serializers.JSONField(read_only=True, default=None)
    has_mixed_areas = serializers.BooleanField(read_only=True)
    has_comparison = serializers.BooleanField(read_only=True)
    has_unverified_areas = serializers.BooleanField(read_only=True)
    comparison_area = serializers.CharField(read_only=True)
    listings = ListingSerializer(source="offers", many=True, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "slug", "canonical_name", "brand", "category", "quantity", "unit", "pack_count", "size", "image", "is_demo", "best_price", "standard_unit_price", "has_mixed_areas", "has_unverified_areas", "has_comparison", "comparison_area", "listings"]


class HistorySerializer(serializers.ModelSerializer):
    is_demo = serializers.SerializerMethodField()
    context_status = serializers.SerializerMethodField()

    def get_is_demo(self, obj):
        return obj.context["is_demo"] if context_known(obj.context) else None

    def get_context_status(self, obj):
        return "captured" if context_known(obj.context) else "unknown"

    class Meta:
        model = PriceHistory
        fields = ["price", "checked_at", "is_demo", "context_status", "context"]
