from django.contrib import admin
from .models import QuotationTemplate, QuotationTemplateLine, Quotation, QuotationLine, Subscription, SubscriptionLine

class TemplateLineInline(admin.TabularInline):
    model = QuotationTemplateLine
    extra = 0
class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 0
    readonly_fields = ("product_name", "variant_description", "tax_rate_snapshot")
class SubscriptionLineInline(admin.TabularInline):
    model = SubscriptionLine
    extra = 0
    readonly_fields = ("product_name", "variant_description", "tax_rate_snapshot")

@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "validity_days", "is_active")
    inlines = [TemplateLineInline]

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "valid_until", "status")
    list_filter = ("status",)
    search_fields = ("number", "customer__email")
    inlines = [QuotationLineInline]

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "plan", "status", "next_billing_date")
    list_filter = ("status", "plan__billing_interval")
    search_fields = ("number", "customer__email")
    inlines = [SubscriptionLineInline]
