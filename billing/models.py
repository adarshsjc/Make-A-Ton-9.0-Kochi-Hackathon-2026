from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from common.numbering import make_number
from catalog.models import Product
from subscriptions.models import Subscription

class DiscountRule(models.Model):
    class DiscountType(models.TextChoices):
        FIXED = "FIXED", "Fixed amount"
        PERCENTAGE = "PERCENTAGE", "Percentage"
    class Scope(models.TextChoices):
        ALL = "ALL", "Whole subscription"
        SELECTED_PRODUCTS = "SELECTED_PRODUCTS", "Selected products"

    name = models.CharField(max_length=150, unique=True)
    discount_type = models.CharField(max_length=12, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    minimum_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    minimum_quantity = models.PositiveIntegerField(default=1)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.ALL)
    products = models.ManyToManyField(Product, blank=True, related_name="discount_rules")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        suffix = "%" if self.discount_type == self.DiscountType.PERCENTAGE else " INR"
        return f"{self.name} ({self.value}{suffix})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "End date must be on or after start date."})
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError({"value": "Percentage discount cannot exceed 100."})
        if self.scope == self.Scope.SELECTED_PRODUCTS and self.pk and not self.products.exists():
            raise ValidationError({"products": "Select at least one product for this discount scope."})

class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=30, unique=True, blank=True)
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices")
    period_start = models.DateField()
    period_end = models.DateField()
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["subscription", "period_start"], name="uniq_invoice_subscription_period_start")]
        indexes = [models.Index(fields=["status", "due_date"]), models.Index(fields=["customer", "issue_date"])]

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = make_number("INV", self.issue_date or timezone.localdate())
        super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        # The invoice API prefetches payments, avoiding one aggregate query per row.
        if "payments" in getattr(self, "_prefetched_objects_cache", {}):
            return sum((payment.amount for payment in self.payments.all()), 0)
        result = self.payments.aggregate(total=Sum("amount"))["total"]
        return result or 0

    @property
    def balance_due(self):
        return max(self.total - self.amount_paid, 0)

    @property
    def is_overdue(self):
        return self.status == self.Status.CONFIRMED and self.due_date < timezone.localdate() and self.balance_due > 0

    @property
    def payment_state(self):
        if self.status == self.Status.PAID:
            return "PAID"
        if self.status == self.Status.CONFIRMED and self.amount_paid > 0:
            return "PARTIALLY_PAID" if self.balance_due > 0 else "PAID"
        if self.is_overdue:
            return "OVERDUE"
        return self.status

    def __str__(self):
        return self.number

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    product_name = models.CharField(max_length=180)
    variant_description = models.CharField(max_length=180, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.invoice.number}: {self.product_name}"

class DiscountRedemption(models.Model):
    discount_rule = models.ForeignKey(DiscountRule, on_delete=models.PROTECT, related_name="redemptions")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="discount_redemptions")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["discount_rule", "invoice"], name="uniq_discount_redemption_invoice")]

class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        CARD = "CARD", "Card"
        CHEQUE = "CHEQUE", "Cheque"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0.01)])
    payment_date = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_payments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        indexes = [models.Index(fields=["payment_date"])]

    def __str__(self):
        return f"{self.invoice.number}: {self.amount}"
