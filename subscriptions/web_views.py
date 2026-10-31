from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from accounts.models import User
from catalog.models import Plan, Product, ProductVariant, Tax
from .models import Quotation, QuotationLine, Subscription, SubscriptionLine
from .services import (
    create_custom_quotation,
    convert_quotation_to_subscription,
    transition_subscription,
)

class SubscriptionListView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        if getattr(user, "role", None) == User.Role.CUSTOMER:
            subscriptions = Subscription.objects.filter(customer=user).select_related("plan").order_by("-created_at")
            quotations = Quotation.objects.filter(customer=user).select_related("plan").order_by("-created_at")
        else:
            subscriptions = Subscription.objects.select_related("customer", "plan").order_by("-created_at")
            quotations = Quotation.objects.select_related("customer", "plan").order_by("-created_at")
        return render(request, "subscriptions/subscriptions_list.html", {
            "subscriptions": subscriptions,
            "quotations": quotations,
            "is_customer": getattr(user, "role", None) == User.Role.CUSTOMER,
        })


class SubscriptionDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        user = request.user
        if getattr(user, "role", None) == User.Role.CUSTOMER:
            subscription = get_object_or_404(Subscription.objects.select_related("plan", "customer").prefetch_related("lines"), pk=pk, customer=user)
        else:
            subscription = get_object_or_404(Subscription.objects.select_related("plan", "customer").prefetch_related("lines"), pk=pk)
        return render(request, "subscriptions/subscription_detail.html", {
            "subscription": subscription,
            "is_customer": getattr(user, "role", None) == User.Role.CUSTOMER,
        })

    def post(self, request, pk):
        user = request.user
        if getattr(user, "role", None) == User.Role.CUSTOMER:
            subscription = get_object_or_404(Subscription, pk=pk, customer=user)
        else:
            subscription = get_object_or_404(Subscription, pk=pk)

        action = request.POST.get("action")
        if getattr(user, "role", None) == User.Role.CUSTOMER and action not in {"pause", "resume", "close", "renew"}:
            messages.error(request, "Customers can only pause, resume, close, or renew subscriptions.")
            return redirect("subscription-detail", pk=pk)

        try:
            transition_subscription(subscription.id, action)
            messages.success(request, f"Subscription status updated via action '{action}'.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect("subscription-detail", pk=pk)


class QuotationCreateView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == User.Role.CUSTOMER:
            messages.error(request, "Only staff can generate new customer quotations.")
            return redirect("subscription-list")

        customers = User.objects.filter(role=User.Role.CUSTOMER, is_active=True)
        plans = Plan.objects.filter(is_active=True)
        products = Product.objects.filter(is_active=True).prefetch_related("variants")
        taxes = Tax.objects.filter(is_active=True)
        return render(request, "subscriptions/create_quote.html", {
            "customers": customers,
            "plans": plans,
            "products": products,
            "taxes": taxes,
        })

    def post(self, request):
        if request.user.role == User.Role.CUSTOMER:
            messages.error(request, "Permission denied.")
            return redirect("subscription-list")

        customer_id = request.POST.get("customer_id")
        plan_id = request.POST.get("plan_id")
        product_id = request.POST.get("product_id")
        variant_id = request.POST.get("variant_id")
        quantity = int(request.POST.get("quantity", 1))
        tax_id = request.POST.get("tax_id")
        notes = request.POST.get("notes", "")

        try:
            customer = User.objects.get(pk=customer_id, role=User.Role.CUSTOMER)
            plan = Plan.objects.get(pk=plan_id, is_active=True)
            product = Product.objects.get(pk=product_id, is_active=True)
            variant = ProductVariant.objects.filter(pk=variant_id).first() if variant_id else None
            tax = Tax.objects.filter(pk=tax_id).first() if tax_id else None

            lines_data = [{
                "product": product,
                "variant": variant,
                "tax": tax,
                "quantity": quantity,
            }]

            quote = create_custom_quotation(
                customer=customer,
                plan=plan,
                lines_data=lines_data,
                created_by=request.user,
                notes=notes,
            )
            messages.success(request, f"Quotation {quote.number} created successfully.")
            return redirect("subscription-list")
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect("quotation-create")
