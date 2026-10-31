from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RunBillingAPIView, InvoiceViewSet, DiscountRuleViewSet, MyInvoicesAPIView
router = DefaultRouter()
router.register("invoices", InvoiceViewSet)
router.register("discount-rules", DiscountRuleViewSet)
urlpatterns = [path("billing/run/", RunBillingAPIView.as_view(), name="api-run-billing"), path("me/invoices/", MyInvoicesAPIView.as_view(), name="api-my-invoices")] + router.urls
