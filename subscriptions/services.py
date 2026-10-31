from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from catalog.models import Plan, Product, ProductVariant, Tax
from common.numbering import make_number
from .models import Quotation, QuotationLine, Subscription, SubscriptionLine

def advance_billing_date(start: date, interval: str, count: int = 1) -> date:
    """Advance by a calendar interval (not 30/365 fixed days), multiplied by count."""
    count = max(1, count)
    curr = start
    for _ in range(count):
        if interval == Plan.BillingInterval.DAILY:
            curr = curr + timedelta(days=1)
        elif interval == Plan.BillingInterval.WEEKLY:
            curr = curr + timedelta(days=7)
        elif interval == Plan.BillingInterval.MONTHLY:
            month_index = curr.month
            year = curr.year + (month_index // 12)
            month = (month_index % 12) + 1
            curr = date(year, month, min(curr.day, monthrange(year, month)[1]))
        elif interval == Plan.BillingInterval.YEARLY:
            year = curr.year + 1
            curr = date(year, curr.month, min(curr.day, monthrange(year, curr.month)[1]))
        else:
            raise ValidationError("Unsupported billing interval.")
    return curr

@transaction.atomic
def create_quotation_from_template(*, template, customer, created_by, notes="", start_date=None):
    if not template.is_active:
        raise ValidationError("This quotation template is inactive.")
    today = timezone.localdate()
    start_date = start_date or today
    quotation = Quotation.objects.create(
        customer=customer,
        plan=template.plan,
        template=template,
        created_by=created_by,
        start_date=start_date,
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
            tax_rate_snapshot=line.tax.rate if line.tax else Decimal("0.00"),
        )
    return quotation

@transaction.atomic
def create_custom_quotation(*, customer, plan, lines_data, created_by, valid_days=15, start_date=None, notes=""):
    today = timezone.localdate()
    start_date = start_date or today
    if not plan.is_active:
        raise ValidationError("The selected plan is inactive.")
    if start_date < plan.available_from or (plan.available_until and start_date > plan.available_until):
        raise ValidationError("The selected plan is not available on the specified start date.")
    if not lines_data:
        raise ValidationError("At least one product line is required.")
    total_qty = sum(int(item.get("quantity", 1)) for item in lines_data)
    if total_qty < plan.minimum_quantity:
        raise ValidationError(f"This plan requires a minimum total quantity of {plan.minimum_quantity}.")

    quotation = Quotation.objects.create(
        customer=customer,
        plan=plan,
        created_by=created_by,
        start_date=start_date,
        valid_until=today + timedelta(days=valid_days),
        notes=notes,
        status=Quotation.Status.DRAFT,
    )
    for item in lines_data:
        product = item["product"]
        variant = item.get("variant")
        tax = item.get("tax")
        quantity = int(item.get("quantity", 1))
        if quantity <= 0:
            raise ValidationError("Line quantity must be greater than zero.")
        if not product.is_active:
            raise ValidationError(f"Product '{product.name}' is inactive.")
        if variant:
            if variant.product_id != product.id:
                raise ValidationError(f"Variant does not belong to product '{product.name}'.")
            if not variant.is_active:
                raise ValidationError(f"Variant is inactive.")
            price_adj = variant.price_adjustment
            var_desc = f"{variant.attribute_name}: {variant.value}"
        else:
            price_adj = Decimal("0.00")
            var_desc = ""
        unit_price = product.sale_price + price_adj
        tax_rate = tax.rate if (tax and tax.is_active) else Decimal("0.00")
        QuotationLine.objects.create(
            quotation=quotation,
            product=product,
            variant=variant,
            product_name=product.name,
            variant_description=var_desc,
            quantity=quantity,
            unit_price=unit_price,
            tax=tax if (tax and tax.is_active) else None,
            tax_rate_snapshot=tax_rate,
        )
    return quotation

@transaction.atomic
def convert_quotation_to_subscription(quotation_id, *, created_by, start_date=None, payment_terms_days=15):
    quotation = Quotation.objects.select_for_update(of=("self",)).select_related("customer").get(pk=quotation_id)
    if hasattr(quotation, "subscription"):
        return quotation.subscription
    if quotation.status not in {Quotation.Status.DRAFT, Quotation.Status.SENT}:
        raise ValidationError("Only draft or sent quotations can be converted.")
    today = timezone.localdate()
    if quotation.valid_until < today:
        quotation.status = Quotation.Status.EXPIRED
        quotation.save(update_fields=["status"])
        return None
    plan = quotation.plan or (quotation.template.plan if quotation.template else None)
    if not plan:
        raise ValidationError("Quotation has no associated plan.")
    start_date = start_date or quotation.start_date or today
    if start_date < plan.available_from or (plan.available_until and start_date > plan.available_until):
        raise ValidationError("The selected plan is not available on the subscription start date.")
    subscription = Subscription.objects.create(
        customer=quotation.customer,
        plan=plan,
        plan_price_snapshot=plan.price,
        quotation=quotation,
        created_by=created_by,
        start_date=start_date,
        payment_terms_days=payment_terms_days,
        status=Subscription.Status.QUOTATION,
    )
    for line in quotation.lines.select_related("product", "variant", "tax"):
        desc = line.product_name
        if line.variant_description:
            desc = f"{desc} ({line.variant_description})"
        SubscriptionLine.objects.create(
            subscription=subscription,
            product=line.product,
            variant=line.variant,
            product_name=line.product_name,
            variant_description=line.variant_description,
            description_snapshot=desc,
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
        "close": {
            Subscription.Status.ACTIVE: Subscription.Status.CLOSED,
            Subscription.Status.PAUSED: Subscription.Status.CLOSED,
            Subscription.Status.CONFIRMED: Subscription.Status.CLOSED,
            Subscription.Status.DRAFT: Subscription.Status.CLOSED,
        },
    }
    if action == "renew":
        if not plan.allow_renew:
            raise ValidationError("This plan does not allow renewal.")
        if subscription.status not in {Subscription.Status.ACTIVE, Subscription.Status.CLOSED}:
            raise ValidationError("Only active or closed subscriptions can be renewed.")
        base = subscription.expiry_date if subscription.expiry_date and subscription.expiry_date >= today else today
        subscription.expiry_date = advance_billing_date(base, plan.billing_interval, count=plan.interval_count)
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
            subscription.next_billing_date = today
        elif not subscription.next_billing_date:
            subscription.next_billing_date = subscription.start_date
        update_fields.extend(["activated_at", "next_billing_date"])
    if transition == Subscription.Status.CLOSED:
        subscription.closed_at = timezone.now()
        update_fields.append("closed_at")
    subscription.save(update_fields=update_fields)
    return subscription
