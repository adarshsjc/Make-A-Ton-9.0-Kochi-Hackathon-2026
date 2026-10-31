from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet, ModelViewSet
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from common.permissions import IsStaffOrAdmin, IsAdminRole
from accounts.models import User
from .models import Invoice, DiscountRule
from .serializers import InvoiceSerializer, PaymentSerializer, DiscountRuleSerializer
from .services import run_billing, confirm_invoice, cancel_invoice, record_payment

class RunBillingAPIView(APIView):
    permission_classes = [IsStaffOrAdmin]
    def post(self, request):
        result = run_billing()
        return Response(result)

class InvoiceViewSet(ReadOnlyModelViewSet):
    queryset = Invoice.objects.select_related("customer", "subscription").prefetch_related("lines", "payments")
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
        return Invoice.objects.filter(customer=self.request.user).select_related("customer", "subscription").prefetch_related("lines", "payments")
