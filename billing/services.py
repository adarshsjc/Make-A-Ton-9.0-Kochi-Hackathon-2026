from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from catalog.models import Plan
from subscriptions.models import Subscription
from subscriptions.services import advance_billing_date
from .models import DiscountRule, DiscountRedemption, Invoice, InvoiceLine, Payment

CENT = Decimal("0.01")
def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)

def _eligible_discount(subscription, charge_lines, subtotal, today):
    """Choose one best valid rule; this starter intentionally does not stack discounts."""
    candidates = DiscountRule.objects.select_for_update().filter(is_active=True, valid_from__lte=today).filter(
        models_q_valid_until(today)
    ).prefetch_related("products")
    best = None
    for rule in candidates:
        if rule.max_uses is not None and rule.times_used >= rule.max_uses:
            continue
        if rule.scope == DiscountRule.Scope.SELECTED_PRODUCTS:
            product_ids = {product.id for product in rule.products.all()}
            eligible_lines = [line for line in charge_lines if line["product_id"] in product_ids]
            if not eligible_lines:
                continue
        else:
            eligible_lines = charge_lines
        eligible_subtotal = sum((line["gross"] for line in eligible_lines), Decimal("0.00"))
        eligible_qty = sum(line["quantity"] for line in eligible_lines)
        if eligible_subtotal < rule.minimum_purchase or eligible_qty < rule.minimum_quantity:
            continue
        if rule.discount_type == DiscountRule.DiscountType.PERCENTAGE:
            discount = money(eligible_subtotal * rule.value / Decimal("100"))
        else:
            discount = min(money(rule.value), eligible_subtotal)
        if discount > 0 and (best is None or discount > best[0]):
            best = (discount, rule, eligible_lines, eligible_subtotal)
    return best

def models_q_valid_until(today):
    from django.db.models import Q
    return Q(valid_until__isnull=True) | Q(valid_until__gte=today)

@transaction.atomic
def generate_invoice_for_subscription(subscription_id, *, billing_date=None):
    today = billing_date or timezone.localdate()
    subscription = Subscription.objects.select_for_update().select_related("plan", "customer").get(pk=subscription_id)
    if subscription.status != Subscription.Status.ACTIVE:
        raise ValidationError("Only active subscriptions can be billed.")
    period_start = subscription.next_billing_date or subscription.start_date
    if period_start > today:
        raise ValidationError("This subscription is not due yet.")
    existing = Invoice.objects.filter(subscription=subscription, period_start=period_start).first()
    if existing:
        # Repair an out-of-sync next_billing_date without creating a duplicate invoice.
        subscription.next_billing_date = advance_billing_date(period_start, subscription.plan.billing_interval)
        subscription.save(update_fields=["next_billing_date", "updated_at"])
        return existing, False
    if subscription.expiry_date and period_start > subscription.expiry_date:
        if subscription.plan.auto_close:
            subscription.status = Subscription.Status.CLOSED
            subscription.closed_at = timezone.now()
            subscription.save(update_fields=["status", "closed_at", "updated_at"])
            return None, False
        raise ValidationError("Subscription has expired and is not eligible for billing.")

    product_lines = list(subscription.lines.select_related("product", "tax", "variant").all())
    # A Plan is the recurring base fee; SubscriptionLine records are additional
    # billable product/add-on lines. This makes both Plan.price and product variants
    # affect the invoice, while keeping the quoted line prices as historical snapshots.
    charge_lines = [{
        "source_id": "plan",
        "product": None,
        "product_id": None,
        "product_name": subscription.plan.name,
        "variant_description": "Recurring plan fee",
        "quantity": 1,
        "unit_price": subscription.plan.price,
        "tax_rate": subscription.plan.tax.rate if subscription.plan.tax_id else Decimal("0.00"),
    }]
    for line in product_lines:
        charge_lines.append({
            "source_id": line.pk,
            "product": line.product,
            "product_id": line.product_id,
            "product_name": line.product_name,
            "variant_description": line.variant_description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "tax_rate": Decimal(line.tax_rate_snapshot or 0),
        })
    for charge in charge_lines:
        charge["gross"] = money(charge["unit_price"] * charge["quantity"])

    period_next = advance_billing_date(period_start, subscription.plan.billing_interval)
    period_end = period_next - timedelta(days=1)
    invoice = Invoice.objects.create(
        subscription=subscription,
        customer=subscription.customer,
        period_start=period_start,
        period_end=period_end,
        issue_date=today,
        due_date=today + timedelta(days=subscription.payment_terms_days),
    )
    subtotal = sum((charge["gross"] for charge in charge_lines), Decimal("0.00"))
    discount_choice = _eligible_discount(subscription, charge_lines, subtotal, today)
    discount_total = discount_choice[0] if discount_choice else Decimal("0.00")
    rule = discount_choice[1] if discount_choice else None
    eligible_ids = {charge["source_id"] for charge in discount_choice[2]} if discount_choice else set()
    eligible_subtotal = discount_choice[3] if discount_choice else Decimal("0.00")

    tax_total = Decimal("0.00")
    line_total_sum = Decimal("0.00")
    allocated = Decimal("0.00")
    eligible_line_rows = [charge for charge in charge_lines if charge["source_id"] in eligible_ids]
    for charge in charge_lines:
        gross = charge["gross"]
        line_discount = Decimal("0.00")
        if charge["source_id"] in eligible_ids and discount_total:
            if charge is eligible_line_rows[-1]:
                line_discount = max(money(discount_total - allocated), Decimal("0.00"))
            elif eligible_subtotal:
                line_discount = money(discount_total * gross / eligible_subtotal)
                allocated += line_discount
        net = max(gross - line_discount, Decimal("0.00"))
        tax_rate = charge["tax_rate"]
        tax_amount = money(net * tax_rate / Decimal("100"))
        line_total = net + tax_amount
        InvoiceLine.objects.create(
            invoice=invoice,
            product=charge["product"],
            product_name=charge["product_name"],
            variant_description=charge["variant_description"],
            quantity=charge["quantity"],
            unit_price=charge["unit_price"],
            tax_rate=tax_rate,
            discount_amount=line_discount,
            line_subtotal=net,
            tax_amount=tax_amount,
            line_total=line_total,
        )
        tax_total += tax_amount
        line_total_sum += line_total
    invoice.subtotal = subtotal
    invoice.discount_amount = discount_total
    invoice.tax_amount = tax_total
    invoice.total = money(line_total_sum)
    invoice.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total"])
    if rule:
        DiscountRedemption.objects.create(discount_rule=rule, invoice=invoice, discount_amount=discount_total)
        from django.db.models import F
        DiscountRule.objects.filter(pk=rule.pk).update(times_used=F("times_used") + 1)
    subscription.next_billing_date = period_next
    subscription.save(update_fields=["next_billing_date", "updated_at"])
    return invoice, True

def _get_finance_summary_filtered(
    *,
    start_date=None,
    end_date=None,
    status_filter=None,
    overdue_only=False,
    search=None,
):
    """Return filtered finance summary data for the HTML finance dashboard."""
    from django.db.models import ExpressionWrapper, F, Sum, Value, DecimalField
    from django.db.models.functions import Coalesce
    from accounts.models import User
    from subscriptions.models import Subscription
    from django.db.models import Q

    ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
    today = timezone.localdate()

    invoices = Invoice.objects.select_related("customer", "subscription").prefetch_related(
        "payments"
    ).exclude(status=Invoice.Status.CANCELLED)

    if start_date:
        invoices = invoices.filter(issue_date__gte=start_date)
    if end_date:
        invoices = invoices.filter(issue_date__lte=end_date)
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    if search:
        invoices = invoices.filter(
            Q(number__icontains=search)
            | Q(customer__email__icontains=search)
            | Q(customer__full_name__icontains=search)
            | Q(subscription__number__icontains=search)
        )
    if overdue_only:
        invoices = invoices.filter(status=Invoice.Status.CONFIRMED, due_date__lt=today)

    payments_qs = Payment.objects.all()
    if start_date:
        payments_qs = payments_qs.filter(payment_date__gte=start_date)
    if end_date:
        payments_qs = payments_qs.filter(payment_date__lte=end_date)

    collected = payments_qs.aggregate(total=Coalesce(Sum("amount"), ZERO))["total"]

    confirmed_qs = invoices.filter(
        status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PAID]
    ).annotate(
        paid=Coalesce(Sum("payments__amount"), ZERO)
    ).annotate(
        balance=ExpressionWrapper(
            F("total") - F("paid"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )
    outstanding = confirmed_qs.filter(balance__gt=0).aggregate(
        total=Coalesce(Sum("balance"), ZERO)
    )["total"]
    overdue_amount = confirmed_qs.filter(due_date__lt=today, balance__gt=0).aggregate(
        total=Coalesce(Sum("balance"), ZERO)
    )["total"]

    paginator_qs = invoices.order_by("-issue_date", "-id")

    return {
        "active_subscriptions": Subscription.objects.filter(
            status=Subscription.Status.ACTIVE
        ).count(),
        "total_customers": User.objects.filter(
            role=User.Role.CUSTOMER, is_active=True
        ).count(),
        "revenue_collected": collected,
        "outstanding_amount": outstanding,
        "overdue_amount": overdue_amount,
        "overdue_invoice_count": confirmed_qs.filter(due_date__lt=today, balance__gt=0).count(),
        "invoice_queryset": paginator_qs,
    }


def run_billing(*, billing_date=None):
    today = billing_date or timezone.localdate()
    due_ids = list(Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        next_billing_date__lte=today,
    ).order_by("next_billing_date").values_list("id", flat=True))
    result = {"processed": 0, "invoices_created": 0, "already_billed": 0, "skipped_expired": 0, "failed": []}
    for subscription_id in due_ids:
        result["processed"] += 1
        try:
            invoice, created = generate_invoice_for_subscription(subscription_id, billing_date=today)
            if invoice is None:
                result["skipped_expired"] += 1
            elif created:
                result["invoices_created"] += 1
            else:
                result["already_billed"] += 1
        except ValidationError as exc:
            # Another billing worker may have completed this subscription after due_ids was read.
            if "not due yet" in str(exc).lower():
                result["already_billed"] += 1
            else:
                result["failed"].append({"subscription_id": subscription_id, "reason": str(exc)})
        except IntegrityError as exc:
            result["failed"].append({"subscription_id": subscription_id, "reason": str(exc)})
    result["failed_count"] = len(result["failed"])
    return result

@transaction.atomic
def confirm_invoice(invoice_id):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Only draft invoices can be confirmed.")
    invoice.status = Invoice.Status.CONFIRMED
    invoice.save(update_fields=["status"])
    return invoice

@transaction.atomic
def cancel_invoice(invoice_id):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.status not in {Invoice.Status.DRAFT, Invoice.Status.CONFIRMED}:
        raise ValidationError("Only draft or confirmed invoices can be cancelled.")
    if invoice.payments.exists():
        raise ValidationError("An invoice with recorded payments cannot be cancelled.")
    # A cancelled invoice releases any discount-use slot it consumed at generation time.
    for redemption in invoice.discount_redemptions.select_related("discount_rule").select_for_update():
        rule = DiscountRule.objects.select_for_update().get(pk=redemption.discount_rule_id)
        if rule.times_used > 0:
            rule.times_used -= 1
            rule.save(update_fields=["times_used"])
        redemption.delete()
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status"])
    return invoice

@transaction.atomic
def record_payment(*, invoice_id, method, amount, payment_date, note, reference, recorded_by):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.status != Invoice.Status.CONFIRMED:
        raise ValidationError("Payments can only be recorded against confirmed invoices.")
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    balance = money(invoice.total - paid)
    if amount > balance:
        raise ValidationError(f"Payment exceeds the outstanding balance of {balance}.")
    payment = Payment.objects.create(
        invoice=invoice, method=method, amount=amount, payment_date=payment_date,
        note=note, reference=reference, recorded_by=recorded_by,
    )
    if amount == balance:
        invoice.status = Invoice.Status.PAID
        invoice.save(update_fields=["status"])
    return payment
