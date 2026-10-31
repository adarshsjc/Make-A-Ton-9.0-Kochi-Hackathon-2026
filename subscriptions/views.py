from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import ListAPIView
from common.permissions import IsStaffOrAdmin, IsAdminRole
from accounts.models import User
from .models import QuotationTemplate, Quotation, Subscription
from .serializers import QuotationTemplateSerializer, QuotationSerializer, SubscriptionSerializer
from .services import create_quotation_from_template, convert_quotation_to_subscription, transition_subscription

class QuotationTemplateViewSet(ModelViewSet):
    queryset = QuotationTemplate.objects.prefetch_related("lines").select_related("plan")
    serializer_class = QuotationTemplateSerializer
    permission_classes = [IsAdminRole]

class QuotationViewSet(ModelViewSet):
    queryset = Quotation.objects.select_related("customer", "template", "created_by").prefetch_related("lines")
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
        try:
            from accounts.models import User
            template = QuotationTemplate.objects.get(pk=template_id, is_active=True)
            customer = User.objects.get(pk=customer_id, role=User.Role.CUSTOMER, is_active=True)
            quotation = create_quotation_from_template(template=template, customer=customer, created_by=request.user, notes=request.data.get("notes", ""))
        except (QuotationTemplate.DoesNotExist, User.DoesNotExist):
            raise ValidationError("A valid active template and customer are required.")
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(quotation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        quotation = self.get_object()  # Apply queryset scoping and return a 404 for missing IDs.
        try:
            payment_terms_days = int(request.data.get("payment_terms_days", 15))
            if payment_terms_days < 0 or payment_terms_days > 365:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError({"payment_terms_days": "Enter a whole number from 0 to 365."})
        try:
            subscription = convert_quotation_to_subscription(
                pk, created_by=request.user,
                payment_terms_days=payment_terms_days,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        if subscription is None:
            raise ValidationError("This quotation has expired.")
        return Response({"subscription_id": subscription.id, "subscription_number": subscription.number, "status": subscription.status}, status=status.HTTP_201_CREATED)

class SubscriptionViewSet(ModelViewSet):
    queryset = Subscription.objects.select_related("customer", "plan", "created_by").prefetch_related("lines")
    serializer_class = SubscriptionSerializer
    permission_classes = [IsStaffOrAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    filterset_fields = ["status", "plan", "customer"]
    search_fields = ["number", "customer__email", "customer__full_name", "plan__name"]
    ordering_fields = ["created_at", "start_date", "next_billing_date"]

    def get_permissions(self):
        # Customers may read and manage their own subscription lifecycle; all other
        # mutations (create/edit) remain internal-only.
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
        subscription_obj = self.get_object()  # Customers are scoped to their own records here.
        action_name = request.data.get("action")
        if request.user.role == User.Role.CUSTOMER and action_name not in {"pause", "resume", "close", "renew"}:
            raise ValidationError("Customers may only pause, resume, close or renew their own subscriptions.")
        try:
            subscription = transition_subscription(subscription_obj.pk, action_name)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(self.get_serializer(subscription).data)


class MySubscriptionsAPIView(ListAPIView):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(customer=self.request.user).select_related("customer", "plan").prefetch_related("lines")
