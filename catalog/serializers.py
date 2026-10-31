from decimal import Decimal
from rest_framework import serializers
from .models import Product, ProductVariant, Tax, Plan

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "notes", "product_type",
            "sale_price", "cost_price", "is_active", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sale_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Sale price cannot be negative.")
        return value

    def validate_cost_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Cost price cannot be negative.")
        return value

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id", "product", "name", "sku", "attribute_name", "value",
            "price_adjustment", "is_active", "created_at"
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        if product and not product.is_active:
            raise serializers.ValidationError({"product": "Cannot add or edit variants for an inactive product."})
        return attrs

class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ["id", "name", "rate", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_rate(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Tax rate cannot be negative.")
        return value

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id", "name", "description", "price", "tax", "billing_interval",
            "interval_count", "minimum_quantity", "available_from", "available_until",
            "auto_close", "allow_early_close", "allow_pause", "allow_renew",
            "is_active", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"available_until": "Available until must be on or after available from."})
        min_qty = attrs.get("minimum_quantity", getattr(self.instance, "minimum_quantity", 1))
        if min_qty < 1:
            raise serializers.ValidationError({"minimum_quantity": "Minimum quantity must be at least 1."})
        interval_count = attrs.get("interval_count", getattr(self.instance, "interval_count", 1))
        if interval_count < 1:
            raise serializers.ValidationError({"interval_count": "Interval count must be at least 1."})
        return attrs
