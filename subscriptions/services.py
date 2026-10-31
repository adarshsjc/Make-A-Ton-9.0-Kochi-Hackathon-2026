from calendar import monthrange
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from catalog.models import Plan
from common.numbering import make_number
from .models import Quotation, QuotationLine, Subscription, SubscriptionLine


def advance_billing_date(start: date, interval: str) -> date:
    """Advance by a calendar interval (not 30/365 fixed days)."""
    if interval == Plan.BillingInterval.DAILY:
        return start + timedelta(days=1)
    if interval == Plan.BillingInterval.WEEKLY:
        return start + timedelta(days=7)
    if interval == Plan.BillingInterval.MONTHLY:
        month_index = start.month  # one-based
        year = start.year + (month_index // 12)
        month = (month_index % 12) + 1
        return date(year, month, min(start.day, monthrange(year, month)[1]))
    if interval == Plan.BillingInterval.YEARLY:
        year = start.year + 1
        return date(year, start.month, min(start.day, monthrange(year, start.month)[1]))
    raise ValidationError("Unsupported billing interval.")

@transaction.atomic
def create_quotation_from_template(*, template, customer, created_by, notes=""):
    if not template.is_active:
        raise ValidationError("This quotation template is inactive.")
    today = timezone.localdate()
    quotation = Quotation.objects.create(
        customer=customer,
        template=template,
        created_by=created_by,
        valid_until=today + timedelta(days=template.validity_days),
        notes=notes,
    )
    template_lines = template.lines.select_related("product", "variant", "tax").all()
    if not template_lines.exists():
        raise ValidationError("The quotation template has no product lines.")
    for line in template_lines:
        QuotationLine.objects.create(
            quotation=quotation,
            product=line.product,
            variant=line.variant,
            product_name=line.product.name,
            variant_description=f"{line.variant.attribute_name}: {line.variant.value}" if line.variant else "",
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax=line.tax,
            tax_rate_snapshot=line.tax.rate if line.tax else 0,
        )
    return quotation

@transaction.atomic
def convert_quotation_to_subscription(quotation_id, *, created_by, start_date=None, payment_terms_days=15):
    quotation = Quotation.objects.select_for_update().select_related("template", "customer").get(pk=quotation_id)
    if hasattr(quotation, "subscription"):
        return quotation.subscription
    if quotation.status not in {Quotation.Status.DRAFT, Quotation.Status.SENT}:
        raise ValidationError("Only draft or sent quotations can be converted.")
    today = timezone.localdate()
    if quotation.valid_until < today:
        quotation.status = Quotation.Status.EXPIRED
        quotation.save(update_fields=["status"])
        return None
    plan = quotation.template.plan
    start_date = start_date or today
    if start_date < plan.available_from or (plan.available_until and start_date > plan.available_until):
        raise ValidationError("The selected plan is not available on the subscription start date.")
    subscription = Subscription.objects.create(
        customer=quotation.customer,
        plan=plan,
        quotation=quotation,
        created_by=created_by,
        start_date=start_date,
        payment_terms_days=payment_terms_days,
        status=Subscription.Status.QUOTATION,
    )
    for line in quotation.lines.select_related("product", "variant", "tax"):
        SubscriptionLine.objects.create(
            subscription=subscription,
            product=line.product,
            variant=line.variant,
            product_name=line.product_name,
            variant_description=line.variant_description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax=line.tax,
            tax_rate_snapshot=line.tax_rate_snapshot,
        )
    quotation.status = Quotation.Status.ACCEPTED
    quotation.save(update_fields=["status"])
    return subscription

@transaction.atomic
def transition_subscription(subscription_id, action):
    subscription = Subscription.objects.select_for_update().select_related("plan").get(pk=subscription_id)
    plan = subscription.plan
    today = timezone.localdate()
    if not isinstance(action, str):
        raise ValidationError("Action must be a string.")
    allowed = {
        "send_quotation": {Subscription.Status.DRAFT: Subscription.Status.QUOTATION},
        "confirm": {Subscription.Status.QUOTATION: Subscription.Status.CONFIRMED, Subscription.Status.DRAFT: Subscription.Status.CONFIRMED},
        "activate": {Subscription.Status.CONFIRMED: Subscription.Status.ACTIVE},
        "pause": {Subscription.Status.ACTIVE: Subscription.Status.PAUSED},
        "resume": {Subscription.Status.PAUSED: Subscription.Status.ACTIVE},
        "close": {Subscription.Status.ACTIVE: Subscription.Status.CLOSED, Subscription.Status.PAUSED: Subscription.Status.CLOSED, Subscription.Status.CONFIRMED: Subscription.Status.CLOSED},
    }
    if action == "renew":
        if not plan.allow_renew:
            raise ValidationError("This plan does not allow renewal.")
        if subscription.status not in {Subscription.Status.ACTIVE, Subscription.Status.CLOSED}:
            raise ValidationError("Only active or closed subscriptions can be renewed.")
        base = subscription.expiry_date if subscription.expiry_date and subscription.expiry_date >= today else today
        subscription.expiry_date = advance_billing_date(base, plan.billing_interval)
        update_fields = ["expiry_date", "updated_at"]
        if subscription.status == Subscription.Status.CLOSED:
            subscription.status = Subscription.Status.ACTIVE
            subscription.start_date = today
            subscription.next_billing_date = today
            subscription.activated_at = timezone.now()
            subscription.closed_at = None
            update_fields.extend(["status", "start_date", "next_billing_date", "activated_at", "closed_at"])
        subscription.save(update_fields=update_fields)
        return subscription
    transition = allowed.get(action, {}).get(subscription.status)
    if not transition:
        raise ValidationError(f"Action '{action}' is not valid from status '{subscription.status}'.")
    if action == "pause" and not plan.allow_pause:
        raise ValidationError("This plan does not allow pausing.")
    if action == "close" and not plan.allow_early_close:
        if not subscription.expiry_date or subscription.expiry_date > today:
            raise ValidationError("This plan does not allow early closure.")
    subscription.status = transition
    update_fields = ["status", "updated_at"]
    if transition == Subscription.Status.ACTIVE:
        subscription.activated_at = timezone.now()
        if action == "resume":
            # Resume starts billing from today; the paused period is not back-billed.
            subscription.next_billing_date = today
        elif not subscription.next_billing_date:
            subscription.next_billing_date = subscription.start_date
        update_fields.extend(["activated_at", "next_billing_date"])
    if transition == Subscription.Status.CLOSED:
        subscription.closed_at = timezone.now()
        update_fields.append("closed_at")
    subscription.save(update_fields=update_fields)
    return subscription
