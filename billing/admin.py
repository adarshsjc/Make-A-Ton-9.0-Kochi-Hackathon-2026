from django.contrib import admin
from .models import DiscountRule, DiscountRedemption, Invoice, InvoiceLine, Payment

class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    can_delete = False
    readonly_fields = ("product_name", "variant_description", "quantity", "unit_price", "tax_rate", "discount_amount", "line_subtotal", "tax_amount", "line_total")

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "issue_date", "due_date", "total", "status")
    list_filter = ("status", "issue_date", "due_date")
    search_fields = ("number", "customer__email", "subscription__number")
    readonly_fields = ("number", "subtotal", "discount_amount", "tax_amount", "total")
    inlines = [InvoiceLineInline]

@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_type", "value", "scope", "times_used", "max_uses", "is_active")
    list_filter = ("discount_type", "scope", "is_active")
    filter_horizontal = ("products",)

admin.site.register(Payment)
admin.site.register(DiscountRedemption)
