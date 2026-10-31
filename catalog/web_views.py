from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from .models import Product, ProductVariant, Tax, Plan

class ProductListView(LoginRequiredMixin, View):
    def get(self, request):
        products = Product.objects.prefetch_related("variants").all()
        return render(request, "catalog/products.html", {"products": products})

    def post(self, request):
        if not (request.user.is_staff or request.user.role in {"ADMIN", "STAFF"}):
            messages.error(request, "Permission denied.")
            return redirect("catalog-product-list")

        action = request.POST.get("action")
        if action == "create_product":
            name = request.POST.get("name", "").strip()
            product_type = request.POST.get("product_type", Product.ProductType.SOFTWARE)
            sale_price = request.POST.get("sale_price", "0.00")
            cost_price = request.POST.get("cost_price", "0.00")
            description = request.POST.get("description", "").strip()
            if not name:
                messages.error(request, "Product name is required.")
            else:
                try:
                    Product.objects.create(
                        name=name,
                        product_type=product_type,
                        sale_price=Decimal(sale_price),
                        cost_price=Decimal(cost_price),
                        description=description,
                    )
                    messages.success(request, f"Product '{name}' created successfully.")
                except Exception as e:
                    messages.error(request, f"Error: {e}")
        elif action == "create_variant":
            product_id = request.POST.get("product_id")
            product = get_object_or_404(Product, pk=product_id)
            attr_name = request.POST.get("attribute_name", "Variant").strip()
            val = request.POST.get("value", "").strip()
            sku = request.POST.get("sku", "").strip() or None
            price_adj = request.POST.get("price_adjustment", "0.00")
            if not val:
                messages.error(request, "Variant value is required.")
            else:
                try:
                    ProductVariant.objects.create(
                        product=product,
                        attribute_name=attr_name,
                        value=val,
                        sku=sku,
                        price_adjustment=Decimal(price_adj),
                    )
                    messages.success(request, f"Variant '{val}' added to {product.name}.")
                except Exception as e:
                    messages.error(request, f"Error: {e}")

        return redirect("catalog-product-list")


class PlanListView(LoginRequiredMixin, View):
    def get(self, request):
        plans = Plan.objects.select_related("tax").all()
        taxes = Tax.objects.filter(is_active=True)
        return render(request, "catalog/plans.html", {"plans": plans, "taxes": taxes})

    def post(self, request):
        if not (request.user.is_staff or request.user.role in {"ADMIN", "STAFF"}):
            messages.error(request, "Permission denied.")
            return redirect("catalog-plan-list")

        name = request.POST.get("name", "").strip()
        price = request.POST.get("price", "0.00")
        billing_interval = request.POST.get("billing_interval", Plan.BillingInterval.MONTHLY)
        min_qty = int(request.POST.get("minimum_quantity", 1))
        tax_id = request.POST.get("tax_id")
        tax = Tax.objects.filter(pk=tax_id).first() if tax_id else None
        allow_pause = request.POST.get("allow_pause") == "on"
        allow_renew = request.POST.get("allow_renew") == "on"
        allow_early_close = request.POST.get("allow_early_close") == "on"

        if not name:
            messages.error(request, "Plan name is required.")
        else:
            try:
                Plan.objects.create(
                    name=name,
                    price=Decimal(price),
                    billing_interval=billing_interval,
                    minimum_quantity=min_qty,
                    tax=tax,
                    allow_pause=allow_pause,
                    allow_renew=allow_renew,
                    allow_early_close=allow_early_close,
                )
                messages.success(request, f"Plan '{name}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error: {e}")

        return redirect("catalog-plan-list")
