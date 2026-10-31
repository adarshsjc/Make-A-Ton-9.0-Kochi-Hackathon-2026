from decimal import Decimal
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.utils import timezone
from accounts.models import User
from subscriptions.models import Subscription
from billing.models import Invoice, Payment

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
def dashboard_summary(*, start_date=None, end_date=None):
    today = timezone.localdate()
    subscriptions = Subscription.objects.all()
    invoices = Invoice.objects.exclude(status=Invoice.Status.CANCELLED)
    payments = Payment.objects.all()
    if start_date:
        invoices = invoices.filter(issue_date__gte=start_date)
        payments = payments.filter(payment_date__gte=start_date)
    if end_date:
        invoices = invoices.filter(issue_date__lte=end_date)
        payments = payments.filter(payment_date__lte=end_date)
    collected = payments.aggregate(total=Coalesce(Sum("amount"), ZERO))["total"]
    confirmed = invoices.filter(status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PAID]).annotate(
        paid=Coalesce(Sum("payments__amount"), ZERO)
    ).annotate(balance=ExpressionWrapper(F("total") - F("paid"), output_field=DecimalField(max_digits=14, decimal_places=2)))
    outstanding = confirmed.filter(balance__gt=0).aggregate(total=Coalesce(Sum("balance"), ZERO))["total"]
    overdue = confirmed.filter(due_date__lt=today, balance__gt=0).aggregate(total=Coalesce(Sum("balance"), ZERO))["total"]
    return {
        "active_subscriptions": subscriptions.filter(status=Subscription.Status.ACTIVE).count(),
        "total_customers": User.objects.filter(role=User.Role.CUSTOMER, is_active=True).count(),
        "revenue_collected": collected,
        "outstanding_amount": outstanding,
        "overdue_amount": overdue,
        "overdue_invoice_count": confirmed.filter(due_date__lt=today, balance__gt=0).count(),
        "recent_invoices": Invoice.objects.select_related("customer").exclude(status=Invoice.Status.CANCELLED).order_by("-issue_date")[:8],
    }
