"""
Billing views: DRF API viewsets + Django HTML views for invoices, payments, and discount rules.
Member C owns this file.
"""
from datetime import date as date_type
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from accounts.models import User
from common.permissions import IsAdminRole, IsStaffOrAdmin

from .forms import DiscountRuleForm, PaymentForm
from .models import DiscountRule, DiscountRedemption, Invoice, Payment
from .serializers import DiscountRuleSerializer, InvoiceSerializer, PaymentSerializer
from .services import (
    cancel_invoice,
    confirm_invoice,
    record_payment,
    run_billing,
)

# ---------------------------------------------------------------------------
# DRF API views (existing contracts preserved)
# ---------------------------------------------------------------------------

class RunBillingAPIView(APIView):
    permission_classes = [IsStaffOrAdmin]

    def post(self, request):
        result = run_billing()
        return Response(result)


class InvoiceViewSet(ReadOnlyModelViewSet):
    queryset = Invoice.objects.select_related("customer", "subscription").prefetch_related(
        "lines", "payments"
    )
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "customer", "subscription"]
    search_fields = ["number", "customer__email", "customer__full_name", "subscription__number"]
    ordering_fields = ["issue_date", "due_date", "total", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == User.Role.CUSTOMER:
            return qs.filter(customer=self.request.user)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    def confirm(self, request, pk=None):
        try:
            invoice = confirm_invoice(pk)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    def cancel(self, request, pk=None):
        try:
            invoice = cancel_invoice(pk)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    def send(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status == Invoice.Status.CANCELLED:
            raise ValidationError("Cancelled invoices cannot be sent.")
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=["sent_at"])
        # Actual email/PDF delivery is a team extension; this records the send event.
        return Response({"detail": "Invoice marked as sent.", "sent_at": invoice.sent_at})

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    def payments(self, request, pk=None):
        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = record_payment(
                invoice_id=pk,
                method=serializer.validated_data["method"],
                amount=serializer.validated_data["amount"],
                payment_date=serializer.validated_data.get("payment_date", timezone.localdate()),
                note=serializer.validated_data.get("note", ""),
                reference=serializer.validated_data.get("reference", ""),
                recorded_by=request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class DiscountRuleViewSet(ModelViewSet):
    queryset = DiscountRule.objects.prefetch_related("products").all()
    serializer_class = DiscountRuleSerializer
    permission_classes = [IsAdminRole]
    filterset_fields = ["is_active", "discount_type", "scope"]
    search_fields = ["name"]


class MyInvoicesAPIView(ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(customer=self.request.user).select_related(
            "customer", "subscription"
        ).prefetch_related("lines", "payments")


# ---------------------------------------------------------------------------
# HTML helper mixin
# ---------------------------------------------------------------------------

class StaffOrAdminRequiredMixin(LoginRequiredMixin):
    """Redirect customers away from staff-only HTML views."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in {User.Role.STAFF, User.Role.ADMIN} and not request.user.is_superuser:
            return HttpResponseForbidden("Access restricted to staff and administrators.")
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# HTML: Invoice List
# ---------------------------------------------------------------------------

class InvoiceListView(StaffOrAdminRequiredMixin, TemplateView):
    template_name = "billing/invoice_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = Invoice.objects.select_related("customer", "subscription").prefetch_related("payments")

        # Filters from query string
        status_filter = self.request.GET.get("status", "")
        overdue_filter = self.request.GET.get("overdue", "")
        start_date_str = self.request.GET.get("start_date", "")
        end_date_str = self.request.GET.get("end_date", "")
        search = self.request.GET.get("q", "").strip()

        if status_filter:
            qs = qs.filter(status=status_filter)
        if start_date_str:
            try:
                qs = qs.filter(issue_date__gte=date_type.fromisoformat(start_date_str))
            except ValueError:
                pass
        if end_date_str:
            try:
                qs = qs.filter(issue_date__lte=date_type.fromisoformat(end_date_str))
            except ValueError:
                pass
        if search:
            qs = qs.filter(
                Q(number__icontains=search)
                | Q(customer__email__icontains=search)
                | Q(customer__full_name__icontains=search)
                | Q(subscription__number__icontains=search)
            )
        if overdue_filter == "1":
            today = timezone.localdate()
            qs = qs.filter(
                status=Invoice.Status.CONFIRMED,
                due_date__lt=today,
            )

        paginator = Paginator(qs.order_by("-issue_date", "-id"), 25)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        ctx.update(
            {
                "page_obj": page_obj,
                "status_choices": Invoice.Status.choices,
                "status_filter": status_filter,
                "overdue_filter": overdue_filter,
                "start_date_str": start_date_str,
                "end_date_str": end_date_str,
                "search": search,
            }
        )
        return ctx


# ---------------------------------------------------------------------------
# HTML: Invoice Detail
# ---------------------------------------------------------------------------

class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "billing/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        qs = Invoice.objects.select_related(
            "customer", "subscription", "subscription__plan"
        ).prefetch_related("lines", "payments__recorded_by", "discount_redemptions__discount_rule")
        user = self.request.user
        if user.role == User.Role.CUSTOMER and not user.is_superuser:
            return qs.filter(customer=user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        invoice = self.object
        is_staff_or_admin = (
            self.request.user.role in {User.Role.STAFF, User.Role.ADMIN}
            or self.request.user.is_superuser
        )
        ctx["is_staff_or_admin"] = is_staff_or_admin
        if is_staff_or_admin:
            ctx["payment_form"] = PaymentForm()
        return ctx


# ---------------------------------------------------------------------------
# HTML: Invoice Print view
# ---------------------------------------------------------------------------

class InvoicePrintView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "billing/invoice_print.html"
    context_object_name = "invoice"

    def get_queryset(self):
        qs = Invoice.objects.select_related(
            "customer", "subscription", "subscription__plan"
        ).prefetch_related(
            "lines",
            "payments",
            "discount_redemptions__discount_rule",
            "customer__customer_profile",
        )
        user = self.request.user
        if user.role == User.Role.CUSTOMER and not user.is_superuser:
            return qs.filter(customer=user)
        return qs


# ---------------------------------------------------------------------------
# HTML: Invoice action views (confirm, cancel, send) — POST only
# ---------------------------------------------------------------------------

class InvoiceConfirmView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            confirm_invoice(pk)
            messages.success(request, "Invoice confirmed successfully.")
        except DjangoValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("billing-invoice-detail", pk=pk)


class InvoiceCancelView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        try:
            cancel_invoice(pk)
            messages.success(request, "Invoice cancelled.")
        except DjangoValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("billing-invoice-detail", pk=pk)


class InvoiceSendView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if invoice.status == Invoice.Status.CANCELLED:
            messages.error(request, "Cancelled invoices cannot be sent.")
            return redirect("billing-invoice-detail", pk=pk)
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=["sent_at"])
        # Email delivery via configured backend (console/locmem in dev; SMTP in prod)
        _send_invoice_email(invoice, request)
        messages.success(request, "Invoice marked as sent.")
        return redirect("billing-invoice-detail", pk=pk)


def _send_invoice_email(invoice, request):
    """Send a simple invoice notification email using the configured backend."""
    try:
        from django.core.mail import send_mail
        from django.conf import settings

        customer_email = invoice.customer.email
        subject = f"Invoice {invoice.number} from Brightloop"
        body = (
            f"Dear {invoice.customer.full_name or customer_email},\n\n"
            f"Please find your invoice {invoice.number} for the period "
            f"{invoice.period_start} to {invoice.period_end}.\n\n"
            f"Total: ₹{invoice.total}\n"
            f"Due date: {invoice.due_date}\n\n"
            f"Please contact us if you have any questions.\n\n"
            f"— Brightloop Team"
        )
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [customer_email], fail_silently=True)
    except Exception:
        pass  # Email is best-effort; the send event is already recorded.


# ---------------------------------------------------------------------------
# HTML: Payment recording
# ---------------------------------------------------------------------------

class InvoicePaymentView(StaffOrAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        form = PaymentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid payment data. " + str(form.errors))
            return redirect("billing-invoice-detail", pk=pk)
        try:
            record_payment(
                invoice_id=pk,
                method=form.cleaned_data["method"],
                amount=form.cleaned_data["amount"],
                payment_date=form.cleaned_data.get("payment_date") or timezone.localdate(),
                note=form.cleaned_data.get("note", ""),
                reference=form.cleaned_data.get("reference", ""),
                recorded_by=request.user,
            )
            messages.success(request, "Payment recorded successfully.")
        except DjangoValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("billing-invoice-detail", pk=pk)


# ---------------------------------------------------------------------------
# HTML: Discount Rule CRUD
# ---------------------------------------------------------------------------

class DiscountRuleListView(StaffOrAdminRequiredMixin, TemplateView):
    template_name = "billing/discount_rule_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = DiscountRule.objects.prefetch_related("products").order_by("-created_at")

        active_filter = self.request.GET.get("is_active", "")
        type_filter = self.request.GET.get("discount_type", "")
        scope_filter = self.request.GET.get("scope", "")
        search = self.request.GET.get("q", "").strip()

        if active_filter == "1":
            qs = qs.filter(is_active=True)
        elif active_filter == "0":
            qs = qs.filter(is_active=False)
        if type_filter:
            qs = qs.filter(discount_type=type_filter)
        if scope_filter:
            qs = qs.filter(scope=scope_filter)
        if search:
            qs = qs.filter(name__icontains=search)

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        ctx.update(
            {
                "page_obj": page_obj,
                "discount_type_choices": DiscountRule.DiscountType.choices,
                "scope_choices": DiscountRule.Scope.choices,
                "active_filter": active_filter,
                "type_filter": type_filter,
                "scope_filter": scope_filter,
                "search": search,
            }
        )
        return ctx


class DiscountRuleCreateView(StaffOrAdminRequiredMixin, View):
    template_name = "billing/discount_rule_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": DiscountRuleForm(), "action": "Create"})

    def post(self, request):
        form = DiscountRuleForm(request.POST)
        if form.is_valid():
            rule = form.save()
            messages.success(request, f"Discount rule '{rule.name}' created.")
            return redirect("billing-discount-list")
        return render(request, self.template_name, {"form": form, "action": "Create"})


class DiscountRuleEditView(StaffOrAdminRequiredMixin, View):
    template_name = "billing/discount_rule_form.html"

    def get(self, request, pk):
        rule = get_object_or_404(DiscountRule, pk=pk)
        return render(request, self.template_name, {"form": DiscountRuleForm(instance=rule), "action": "Edit", "rule": rule})

    def post(self, request, pk):
        rule = get_object_or_404(DiscountRule, pk=pk)
        form = DiscountRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, f"Discount rule '{rule.name}' updated.")
            return redirect("billing-discount-list")
        return render(request, self.template_name, {"form": form, "action": "Edit", "rule": rule})


class DiscountRuleDeleteView(StaffOrAdminRequiredMixin, View):
    template_name = "billing/discount_rule_confirm_delete.html"

    def get(self, request, pk):
        rule = get_object_or_404(DiscountRule, pk=pk)
        return render(request, self.template_name, {"rule": rule})

    def post(self, request, pk):
        rule = get_object_or_404(DiscountRule, pk=pk)
        if DiscountRedemption.objects.filter(discount_rule=rule).exists():
            messages.error(
                request,
                "Cannot delete a discount rule that has been redeemed. Deactivate it instead.",
            )
            return redirect("billing-discount-list")
        name = rule.name
        rule.delete()
        messages.success(request, f"Discount rule '{name}' deleted.")
        return redirect("billing-discount-list")


# ---------------------------------------------------------------------------
# HTML: Finance dashboard (staff/admin filtered view)
# ---------------------------------------------------------------------------

class FinanceDashboardView(StaffOrAdminRequiredMixin, TemplateView):
    template_name = "billing/finance_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .services import _get_finance_summary_filtered

        start_date_str = self.request.GET.get("start_date", "")
        end_date_str = self.request.GET.get("end_date", "")
        status_filter = self.request.GET.get("status", "")
        overdue_filter = self.request.GET.get("overdue", "")
        search = self.request.GET.get("q", "").strip()

        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = date_type.fromisoformat(start_date_str)
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = date_type.fromisoformat(end_date_str)
            except ValueError:
                pass

        from django.core.paginator import Paginator

        summary = _get_finance_summary_filtered(
            start_date=start_date,
            end_date=end_date,
            status_filter=status_filter,
            overdue_only=(overdue_filter == "1"),
            search=search,
        )
        invoice_qs = summary.pop("invoice_queryset", Invoice.objects.none())
        paginator = Paginator(invoice_qs, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        ctx.update(summary)
        ctx["page_obj"] = page_obj
        ctx.update(
            {
                "status_choices": Invoice.Status.choices,
                "status_filter": status_filter,
                "overdue_filter": overdue_filter,
                "start_date_str": start_date_str,
                "end_date_str": end_date_str,
                "search": search,
            }
        )
        return ctx
