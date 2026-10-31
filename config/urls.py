from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import RegisterPageView
from .api_views import APIIndexView

# Billing HTML views
from billing.views import (
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
    RunBillingHTMLView,
)

# Catalog & Subscriptions HTML views
from catalog.web_views import ProductListView, PlanListView
from subscriptions.web_views import (
    SubscriptionListView,
    SubscriptionDetailView,
    QuotationCreateView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/register/", RegisterPageView.as_view(), name="register"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password-reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.html",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url="/accounts/password-reset/done/",
    ), name="password_reset"),
    path("accounts/password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"), name="password_reset_confirm"),
    path("accounts/reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),

    # API
    path("api/v1/", APIIndexView.as_view(), name="api-root"),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("subscriptions.urls")),
    path("api/v1/", include("billing.urls")),
    path("api/v1/", include("dashboard.api_urls")),

    # HTML screens – Catalog
    path("catalog/", RedirectView.as_view(pattern_name="catalog-product-list", permanent=False)),
    path("catalog/products/", ProductListView.as_view(), name="catalog-product-list"),
    path("catalog/plans/", PlanListView.as_view(), name="catalog-plan-list"),

    # HTML screens – Subscriptions
    path("subscriptions/", SubscriptionListView.as_view(), name="subscription-list"),
    path("subscriptions/<int:pk>/", SubscriptionDetailView.as_view(), name="subscription-detail"),
    path("subscriptions/quotations/new/", QuotationCreateView.as_view(), name="quotation-create"),

    # HTML screens – Billing / Finance
    path("billing/", RedirectView.as_view(pattern_name="billing-invoice-list", permanent=False)),
    path("billing/run/", RunBillingHTMLView.as_view(), name="billing-run"),
    path("billing/invoices/", InvoiceListView.as_view(), name="billing-invoice-list"),
    path("billing/invoices/<int:pk>/", InvoiceDetailView.as_view(), name="billing-invoice-detail"),
    path("billing/invoices/<int:pk>/confirm/", InvoiceConfirmView.as_view(), name="billing-invoice-confirm"),
    path("billing/invoices/<int:pk>/cancel/", InvoiceCancelView.as_view(), name="billing-invoice-cancel"),
    path("billing/invoices/<int:pk>/send/", InvoiceSendView.as_view(), name="billing-invoice-send"),
    path("billing/invoices/<int:pk>/payment/", InvoicePaymentView.as_view(), name="billing-invoice-payment"),
    path("billing/invoices/<int:pk>/print/", InvoicePrintView.as_view(), name="billing-invoice-print"),

    # HTML screens – Discount Rules
    path("billing/discounts/", DiscountRuleListView.as_view(), name="billing-discount-list"),
    path("billing/discounts/create/", DiscountRuleCreateView.as_view(), name="billing-discount-create"),
    path("billing/discounts/<int:pk>/edit/", DiscountRuleEditView.as_view(), name="billing-discount-edit"),
    path("billing/discounts/<int:pk>/delete/", DiscountRuleDeleteView.as_view(), name="billing-discount-delete"),

    # HTML screens – Finance dashboard
    path("finance/", FinanceDashboardView.as_view(), name="finance-dashboard"),
]
