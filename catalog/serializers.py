from rest_framework import serializers
from .models import Product, ProductVariant, Tax, Plan

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = "__all__"
        read_only_fields = ["id"]

class TaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = "__all__"
        read_only_fields = ["id", "created_at"]

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"available_until": "Must be on or after available_from."})
        return attrs
