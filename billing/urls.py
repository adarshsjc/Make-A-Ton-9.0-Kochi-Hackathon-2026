"""Billing app URL configuration: API routes and HTML screens."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    # API views
    DiscountRuleViewSet,
    InvoiceViewSet,
    MyInvoicesAPIView,
    RunBillingAPIView,
    # HTML views – invoices
    DiscountRuleCreateView,
    DiscountRuleDeleteView,
    DiscountRuleEditView,
    DiscountRuleListView,
    FinanceDashboardView,
    InvoiceCancelView,
    InvoiceConfirmView,
    InvoiceDetailView,
    InvoiceListView,
    InvoicePaymentView,
    InvoicePrintView,
    InvoiceSendView,
)

# DRF router for API viewsets
router = DefaultRouter()
router.register("invoices", InvoiceViewSet)
router.register("discount-rules", DiscountRuleViewSet)

urlpatterns = [
    # ---------- API ----------
    path("billing/run/", RunBillingAPIView.as_view(), name="api-run-billing"),
    path("me/invoices/", MyInvoicesAPIView.as_view(), name="api-my-invoices"),
    *router.urls,
]
