from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from common.numbering import make_number
from catalog.models import Plan, Product, ProductVariant, Tax

class QuotationTemplate(models.Model):
    name = models.CharField(max_length=150, unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="quotation_templates")
    validity_days = models.PositiveIntegerField(default=15, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return f"{self.template}: {self.product} x {self.quantity}"

class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        ACCEPTED = "ACCEPTED", "Accepted"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, blank=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quotations")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="quotations", null=True, blank=True)
    template = models.ForeignKey(QuotationTemplate, on_delete=models.PROTECT, related_name="quotations", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_quotations")
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = make_number("QUO")
        if not self.plan and self.template:
            self.plan = self.template.plan
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        base = self.plan.price if self.plan else Decimal("0.00")
        line_total = sum((line.subtotal for line in self.lines.all()), Decimal("0.00"))
        return base + line_total

    @property
    def plan_name(self):
        if self.plan:
            return self.plan.name
        if self.template and self.template.plan:
            return self.template.plan.name
        return "—"

    def __str__(self):
        return self.number

class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)
    product_name = models.CharField(max_length=180)
    variant_description = models.CharField(max_length=180, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT, null=True, blank=True)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        if not self.product_name and self.product:
            self.product_name = self.product.name
        if not self.variant_description and self.variant:
            self.variant_description = f"{self.variant.attribute_name}: {self.variant.value}"
        if self.tax and not self.tax_rate_snapshot:
            self.tax_rate_snapshot = self.tax.rate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quotation.number}: {self.product_name} x {self.quantity}"

class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Quotation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        CLOSED = "CLOSED", "Closed"

    number = models.CharField(max_length=30, unique=True, blank=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    plan_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])
    quotation = models.OneToOneField(Quotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_subscriptions")
    start_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True, db_index=True)
    payment_terms_days = models.PositiveIntegerField(default=15)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "next_billing_date"]), models.Index(fields=["customer", "status"])]

    @property
    def payment_terms(self):
        return self.payment_terms_days

    @property
    def customer_profile(self):
        return getattr(self.customer, "customer_profile", None)

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = make_number("SUB")
        if self.next_billing_date is None and self.start_date:
            self.next_billing_date = self.start_date
        if (self.plan_price_snapshot == 0 or self.plan_price_snapshot is None) and self.plan_id:
            self.plan_price_snapshot = self.plan.price
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)
    product_name = models.CharField(max_length=180)
    variant_description = models.CharField(max_length=180, blank=True)
    description_snapshot = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT, null=True, blank=True)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        if not self.description_snapshot:
            desc = self.product_name or (self.product.name if self.product else "")
            if self.variant_description:
                desc = f"{desc} ({self.variant_description})"
            self.description_snapshot = desc
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subscription.number}: {self.product_name} x {self.quantity}"
