"""Django forms for billing HTML views."""
from decimal import Decimal
from django import forms
from django.utils import timezone

from .models import DiscountRule, Payment
from catalog.models import Product


class PaymentForm(forms.Form):
    method = forms.ChoiceField(choices=Payment.Method.choices)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payment_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    reference = forms.CharField(max_length=100, required=False)
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class DiscountRuleForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Required when scope is 'Selected products'.",
    )

    class Meta:
        model = DiscountRule
        fields = [
            "name",
            "discount_type",
            "value",
            "scope",
            "products",
            "minimum_purchase",
            "minimum_quantity",
            "valid_from",
            "valid_until",
            "max_uses",
            "is_active",
        ]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("discount_type")
        value = cleaned.get("value")
        start = cleaned.get("valid_from")
        end = cleaned.get("valid_until")
        scope = cleaned.get("scope")
        products = cleaned.get("products")

        if kind == DiscountRule.DiscountType.PERCENTAGE and value is not None and value > 100:
            self.add_error("value", "Percentage discount cannot exceed 100.")
        if start and end and end < start:
            self.add_error("valid_until", "End date must be on or after start date.")
        if scope == DiscountRule.Scope.SELECTED_PRODUCTS and not products:
            self.add_error("products", "Select at least one product for this discount scope.")
        return cleaned
