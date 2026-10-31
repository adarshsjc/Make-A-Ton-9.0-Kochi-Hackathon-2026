from django.contrib import admin
from .models import Product, ProductVariant, Tax, Plan

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "sale_price", "cost_price", "is_active")
    list_filter = ("product_type", "is_active")
    search_fields = ("name",)
    inlines = [ProductVariantInline]

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "billing_interval", "is_active")
    list_filter = ("billing_interval", "is_active", "auto_close", "allow_pause")
    search_fields = ("name",)

admin.site.register(Tax)
admin.site.register(ProductVariant)
