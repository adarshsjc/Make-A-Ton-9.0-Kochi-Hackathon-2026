from django.utils import timezone
from rest_framework import serializers
from accounts.models import User
from catalog.models import Product, ProductVariant, Tax, Plan
from .models import QuotationTemplate, QuotationTemplateLine, Quotation, QuotationLine, Subscription, SubscriptionLine

class QuotationTemplateLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationTemplateLine
        fields = "__all__"

class QuotationTemplateSerializer(serializers.ModelSerializer):
    lines = QuotationTemplateLineSerializer(many=True, read_only=True)
    class Meta:
        model = QuotationTemplate
        fields = ["id", "name", "plan", "validity_days", "is_active", "created_at", "lines"]
        read_only_fields = ["id", "created_at"]

class QuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLine
        fields = ["id", "product", "variant", "product_name", "variant_description", "quantity", "unit_price", "tax", "tax_rate_snapshot"]
        read_only_fields = fields

class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True, read_only=True)
    class Meta:
        model = Quotation
        fields = ["id", "number", "customer", "template", "created_by", "created_at", "valid_until", "status", "notes", "lines"]
        read_only_fields = ["id", "number", "created_by", "created_at", "status", "lines"]

class SubscriptionLineSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

    class Meta:
        model = SubscriptionLine
        fields = ["id", "product", "variant", "product_name", "variant_description", "quantity", "unit_price", "tax", "tax_rate_snapshot"]
        read_only_fields = ["id", "product_name", "variant_description", "unit_price", "tax_rate_snapshot"]

    def validate(self, attrs):
        product = attrs.get("product")
        variant = attrs.get("variant")
        if product and not product.is_active:
            raise serializers.ValidationError({"product": "This product is inactive."})
        if variant and product and variant.product_id != product.id:
            raise serializers.ValidationError({"variant": "This variant does not belong to the selected product."})
        if variant and not variant.is_active:
            raise serializers.ValidationError({"variant": "This variant is inactive."})
        if attrs.get("tax") and not attrs["tax"].is_active:
            raise serializers.ValidationError({"tax": "This tax rule is inactive."})
        return attrs

class SubscriptionSerializer(serializers.ModelSerializer):
    lines = SubscriptionLineSerializer(many=True, required=False)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "number", "customer", "customer_email", "plan", "plan_name", "quotation", "created_by", "start_date", "expiry_date", "next_billing_date", "payment_terms_days", "status", "created_at", "updated_at", "notes", "lines"]
        read_only_fields = ["id", "number", "created_by", "status", "created_at", "updated_at", "next_billing_date"]

    def validate(self, attrs):
        plan = attrs.get("plan", getattr(self.instance, "plan", None))
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        expiry = attrs.get("expiry_date", getattr(self.instance, "expiry_date", None))
        if plan and not plan.is_active:
            raise serializers.ValidationError({"plan": "This plan is inactive."})
        if plan and start:
            if start < plan.available_from or (plan.available_until and start > plan.available_until):
                raise serializers.ValidationError({"start_date": "The plan is not available on this date."})
        if expiry and start and expiry < start:
            raise serializers.ValidationError({"expiry_date": "Expiry must be on or after start date."})
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if customer and customer.role != User.Role.CUSTOMER:
            raise serializers.ValidationError({"customer": "A subscription must belong to a customer account."})
        if customer and not customer.is_active:
            raise serializers.ValidationError({"customer": "The customer account is inactive."})
        lines = attrs.get("lines")
        if not self.instance and not lines:
            raise serializers.ValidationError({"lines": "At least one subscription line is required."})
        if lines and plan:
            quantity = sum(item.get("quantity", 1) for item in lines)
            if quantity < plan.minimum_quantity:
                raise serializers.ValidationError({"lines": f"This plan requires a minimum total quantity of {plan.minimum_quantity}."})
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        request = self.context.get("request")
        validated_data["created_by"] = request.user
        subscription = Subscription.objects.create(**validated_data)
        for item in lines_data:
            product = item["product"]
            variant = item.get("variant")
            tax = item.get("tax")
            item["product_name"] = product.name
            item["variant_description"] = f"{variant.attribute_name}: {variant.value}" if variant else ""
            item["unit_price"] = product.sale_price + (variant.price_adjustment if variant else 0)
            item["tax_rate_snapshot"] = tax.rate if tax else 0
            SubscriptionLine.objects.create(subscription=subscription, **item)
        return subscription

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        if lines_data is not None and instance.status not in {Subscription.Status.DRAFT, Subscription.Status.QUOTATION}:
            raise serializers.ValidationError("Subscription lines cannot be edited after confirmation.")
        old_start_date = instance.start_date
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if "start_date" in validated_data and instance.next_billing_date == old_start_date:
            instance.next_billing_date = instance.start_date
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for item in lines_data:
                product, variant, tax = item["product"], item.get("variant"), item.get("tax")
                item["product_name"] = product.name
                item["variant_description"] = f"{variant.attribute_name}: {variant.value}" if variant else ""
                item["unit_price"] = product.sale_price + (variant.price_adjustment if variant else 0)
                item["tax_rate_snapshot"] = tax.rate if tax else 0
                SubscriptionLine.objects.create(subscription=instance, **item)
        return instance
