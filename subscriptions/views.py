from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from accounts.models import User
from catalog.models import Plan, Product, ProductVariant, Tax
from common.permissions import IsStaffOrAdmin, IsAdminRole
from .models import QuotationTemplate, Quotation, Subscription
from .serializers import QuotationTemplateSerializer, QuotationSerializer, SubscriptionSerializer
from .services import (
    create_quotation_from_template,
    create_custom_quotation,
    convert_quotation_to_subscription,
    transition_subscription,
)

class QuotationTemplateViewSet(ModelViewSet):
    queryset = QuotationTemplate.objects.prefetch_related("lines").select_related("plan")
    serializer_class = QuotationTemplateSerializer
    permission_classes = [IsAdminRole]

class QuotationViewSet(ModelViewSet):
    queryset = Quotation.objects.select_related("customer", "template", "plan", "created_by").prefetch_related("lines")
    serializer_class = QuotationSerializer
    permission_classes = [IsStaffOrAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if getattr(self, "action", None) in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsStaffOrAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == User.Role.CUSTOMER:
            return qs.filter(customer=self.request.user)
        return qs

    def create(self, request, *args, **kwargs):
        template_id = request.data.get("template")
        customer_id = request.data.get("customer")
        plan_id = request.data.get("plan")
        lines_data = request.data.get("lines")
        notes = request.data.get("notes", "")
        start_date = request.data.get("start_date")

        try:
            customer = User.objects.get(pk=customer_id, role=User.Role.CUSTOMER, is_active=True)
            if template_id:
                template = QuotationTemplate.objects.get(pk=template_id, is_active=True)
                quotation = create_quotation_from_template(
                    template=template,
                    customer=customer,
                    created_by=request.user,
                    notes=notes,
                    start_date=start_date,
                )
            elif plan_id and lines_data:
                plan = Plan.objects.get(pk=plan_id, is_active=True)
                prepared_lines = []
                for item in lines_data:
                    prod = Product.objects.get(pk=item.get("product"))
                    var = ProductVariant.objects.get(pk=item.get("variant")) if item.get("variant") else None
                    tx = Tax.objects.get(pk=item.get("tax")) if item.get("tax") else None
                    prepared_lines.append({
                        "product": prod,
                        "variant": var,
                        "tax": tx,
                        "quantity": int(item.get("quantity", 1)),
                    })
                quotation = create_custom_quotation(
                    customer=customer,
                    plan=plan,
                    lines_data=prepared_lines,
                    created_by=request.user,
                    valid_days=int(request.data.get("validity_days", 15)),
                    start_date=start_date,
                    notes=notes,
                )
            else:
                raise ValidationError("Specify either an active template or an active plan with product lines.")
        except (QuotationTemplate.DoesNotExist, User.DoesNotExist, Plan.DoesNotExist, Product.DoesNotExist, ProductVariant.DoesNotExist, Tax.DoesNotExist) as exc:
            raise ValidationError(str(exc))
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages if hasattr(exc, "messages") else str(exc))

        return Response(self.get_serializer(quotation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        quotation = self.get_object()
        try:
            payment_terms_days = int(request.data.get("payment_terms_days", 15))
            if payment_terms_days < 0 or payment_terms_days > 365:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError({"payment_terms_days": "Enter a whole number from 0 to 365."})

        try:
            subscription = convert_quotation_to_subscription(
                pk,
                created_by=request.user,
                start_date=request.data.get("start_date"),
                payment_terms_days=payment_terms_days,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages if hasattr(exc, "messages") else str(exc))

        if subscription is None:
            raise ValidationError("This quotation has expired.")
        return Response(
            {"subscription_id": subscription.id, "subscription_number": subscription.number, "status": subscription.status},
            status=status.HTTP_201_CREATED,
        )

class SubscriptionViewSet(ModelViewSet):
    queryset = Subscription.objects.select_related("customer", "plan", "created_by").prefetch_related("lines")
    serializer_class = SubscriptionSerializer
    permission_classes = [IsStaffOrAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    filterset_fields = ["status", "plan", "customer"]
    search_fields = ["number", "customer__email", "customer__full_name", "plan__name"]
    ordering_fields = ["created_at", "start_date", "next_billing_date"]

    def get_permissions(self):
        if getattr(self, "action", None) in {"list", "retrieve", "transition"}:
            return [IsAuthenticated()]
        return [IsStaffOrAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == User.Role.CUSTOMER:
            return qs.filter(customer=self.request.user)
        return qs

    def perform_update(self, serializer):
        if serializer.instance.status not in {Subscription.Status.DRAFT, Subscription.Status.QUOTATION}:
            raise ValidationError("Only draft/quotation subscriptions may be edited.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        subscription_obj = self.get_object()
        action_name = request.data.get("action")
        if request.user.role == User.Role.CUSTOMER and action_name not in {"pause", "resume", "close", "renew"}:
            raise ValidationError("Customers may only pause, resume, close or renew their own subscriptions.")
        try:
            subscription = transition_subscription(subscription_obj.pk, action_name)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages if hasattr(exc, "messages") else str(exc))
        return Response(self.get_serializer(subscription).data)

class MySubscriptionsAPIView(ListAPIView):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(customer=self.request.user).select_related("customer", "plan").prefetch_related("lines")
