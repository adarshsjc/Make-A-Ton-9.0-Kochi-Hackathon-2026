from decimal import Decimal
from rest_framework import serializers
from .models import Invoice, InvoiceLine, Payment, DiscountRule

class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ["id", "product_name", "variant_description", "quantity", "unit_price", "tax_rate", "discount_amount", "line_subtotal", "tax_amount", "line_total"]

class InvoiceSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    subscription_number = serializers.CharField(source="subscription.number", read_only=True)
    amount_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    payment_state = serializers.CharField(read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)
    class Meta:
        model = Invoice
        fields = ["id", "number", "subscription", "subscription_number", "customer", "customer_email", "period_start", "period_end", "issue_date", "due_date", "subtotal", "discount_amount", "tax_amount", "total", "amount_paid", "balance_due", "payment_state", "status", "sent_at", "created_at", "lines"]

class PaymentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = Payment
        fields = ["id", "invoice", "method", "amount", "payment_date", "note", "reference", "recorded_by", "created_at"]
        read_only_fields = ["id", "invoice", "recorded_by", "created_at"]

class DiscountRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountRule
        fields = "__all__"
        read_only_fields = ["id", "times_used", "created_at"]
    def validate(self, attrs):
        kind = attrs.get("discount_type", getattr(self.instance, "discount_type", None))
        value = attrs.get("value", getattr(self.instance, "value", None))
        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        scope = attrs.get("scope", getattr(self.instance, "scope", None))
        if kind == DiscountRule.DiscountType.PERCENTAGE and value is not None and value > 100:
            raise serializers.ValidationError({"value": "Percentage discounts cannot exceed 100."})
        if start and end and end < start:
            raise serializers.ValidationError({"valid_until": "Must be on or after valid_from."})
        if scope == DiscountRule.Scope.SELECTED_PRODUCTS and not attrs.get("products", getattr(self.instance, "products", []).all() if self.instance else []):
            raise serializers.ValidationError({"products": "Select at least one product."})
        return attrs
