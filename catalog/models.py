from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

class Product(models.Model):
    class ProductType(models.TextChoices):
        SOFTWARE = "SOFTWARE", "Software"
        SERVICE = "SERVICE", "Service"
        ADD_ON = "ADD_ON", "Add-on"
        PHYSICAL = "PHYSICAL", "Physical product"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=180, unique=True)
    product_type = models.CharField(max_length=12, choices=ProductType.choices, default=ProductType.SOFTWARE)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self):
        return self.name

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    attribute_name = models.CharField(max_length=80, default="Variant")
    value = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name", "attribute_name", "value"]
        constraints = [models.UniqueConstraint(fields=["product", "attribute_name", "value"], name="uniq_product_variant_attribute_value")]

    def __str__(self):
        return f"{self.product} — {self.attribute_name}: {self.value}"

class Tax(models.Model):
    name = models.CharField(max_length=100, unique=True)
    rate = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class Plan(models.Model):
    class BillingInterval(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT, null=True, blank=True, related_name="plans")
    billing_interval = models.CharField(max_length=10, choices=BillingInterval.choices, default=BillingInterval.MONTHLY)
    minimum_quantity = models.PositiveIntegerField(default=1)
    available_from = models.DateField(default=timezone.localdate)
    available_until = models.DateField(null=True, blank=True)
    auto_close = models.BooleanField(default=False)
    allow_early_close = models.BooleanField(default=True)
    allow_pause = models.BooleanField(default=True)
    allow_renew = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=models.Q(minimum_quantity__gte=1), name="plan_min_quantity_gte_1")]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.available_until and self.available_until < self.available_from:
            raise ValidationError({"available_until": "Availability end must be on or after its start date."})
