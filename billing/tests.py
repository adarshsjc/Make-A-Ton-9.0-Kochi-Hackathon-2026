"""
Comprehensive test suite for Member C — Billing & Finance.

Covers the 12-step shared test path plus:
- Monthly/yearly calendar boundary dates
- Discount eligibility (ALL and SELECTED_PRODUCTS scope)
- Plan tax + line tax, Decimal rounding, snapshot stability
- Invoice confirm/cancel/send flow
- Partial/full/overpayment payment handling
- Cancelled-invoice guards
- Overdue calculations
- Dashboard filters and role permissions
- Idempotent billing (no duplicate invoices)
- Customer isolation
"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import (
    DiscountRedemption,
    DiscountRule,
    Invoice,
    InvoiceLine,
    Payment,
)
from billing.services import (
    _get_finance_summary_filtered,
    cancel_invoice,
    confirm_invoice,
    generate_invoice_for_subscription,
    money,
    record_payment,
    run_billing,
)
from catalog.models import Plan, Product, ProductVariant, Tax
from subscriptions.models import (
    Quotation,
    QuotationLine,
    QuotationTemplate,
    QuotationTemplateLine,
    Subscription,
    SubscriptionLine,
)
from subscriptions.services import (
    advance_billing_date,
    convert_quotation_to_subscription,
    create_quotation_from_template,
    transition_subscription,
)

User = get_user_model()

CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_staff(**kwargs):
    defaults = {"full_name": "Staff User", "role": "STAFF", "is_staff": False}
    defaults.update(kwargs)
    user = User.objects.create_user(email=defaults.pop("email", "staff@test.local"), password="StaffPass!9", **defaults)
    return user


def _make_admin(**kwargs):
    defaults = {"full_name": "Admin User", "role": "ADMIN", "is_staff": True, "is_superuser": True}
    defaults.update(kwargs)
    user = User.objects.create_user(email=defaults.pop("email", "admin@test.local"), password="AdminPass!9", **defaults)
    return user


def _make_customer(email="customer@test.local", **kwargs):
    defaults = {"full_name": "Test Customer", "role": "CUSTOMER"}
    defaults.update(kwargs)
    return User.objects.create_user(email=email, password="CustPass!99", **defaults)


def _make_tax(name="GST 18", rate="18.00"):
    return Tax.objects.create(name=name, rate=Decimal(rate))


def _make_product(name="Widget", sale_price="1000.00"):
    return Product.objects.create(name=name, sale_price=Decimal(sale_price), product_type="SOFTWARE")


def _make_variant(product, adj="0.00"):
    return ProductVariant.objects.create(
        product=product, attribute_name="Tier", value="Standard", price_adjustment=Decimal(adj)
    )


def _make_plan(name="Monthly Plan", price="500.00", interval="MONTHLY", tax=None):
    return Plan.objects.create(
        name=name,
        price=Decimal(price),
        billing_interval=interval,
        tax=tax,
        available_from=date.today(),
        allow_pause=True,
        allow_renew=True,
        allow_early_close=True,
    )


def _make_subscription(customer, plan, staff, start=None, lines=None):
    """Create an active subscription directly (bypassing quotation)."""
    today = start or date.today()
    sub = Subscription.objects.create(
        customer=customer,
        plan=plan,
        created_by=staff,
        start_date=today,
        payment_terms_days=15,
        status=Subscription.Status.ACTIVE,
        activated_at=timezone.now(),
    )
    for line_data in (lines or []):
        product = line_data["product"]
        variant = line_data.get("variant")
        tax = line_data.get("tax")
        qty = line_data.get("quantity", 1)
        price = line_data.get("unit_price", product.sale_price)
        SubscriptionLine.objects.create(
            subscription=sub,
            product=product,
            variant=variant,
            product_name=product.name,
            variant_description=f"Tier: Standard" if variant else "",
            quantity=qty,
            unit_price=price,
            tax=tax,
            tax_rate_snapshot=tax.rate if tax else Decimal("0"),
        )
    return sub


# ---------------------------------------------------------------------------
# 1. Money rounding utility
# ---------------------------------------------------------------------------

class MoneyRoundingTests(TestCase):
    def test_half_up_rounding(self):
        self.assertEqual(money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(money(Decimal("1.004")), Decimal("1.00"))
        self.assertEqual(money(Decimal("2.555")), Decimal("2.56"))

    def test_string_input(self):
        self.assertEqual(money("100"), Decimal("100.00"))

    def test_zero(self):
        self.assertEqual(money(0), Decimal("0.00"))


# ---------------------------------------------------------------------------
# 2. Calendar boundary dates
# ---------------------------------------------------------------------------

class AdvanceBillingDateTests(TestCase):
    def test_daily(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 31), "DAILY"), date(2026, 2, 1))

    def test_weekly(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 31), "WEEKLY"), date(2026, 2, 7))

    def test_monthly_normal(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 15), "MONTHLY"), date(2026, 2, 15))

    def test_monthly_jan31_to_feb(self):
        # Jan 31 → Feb 28 (2026 is not a leap year)
        self.assertEqual(advance_billing_date(date(2026, 1, 31), "MONTHLY"), date(2026, 2, 28))

    def test_monthly_jan31_leap(self):
        # Jan 31, 2024 → Feb 29 (2024 is a leap year)
        self.assertEqual(advance_billing_date(date(2024, 1, 31), "MONTHLY"), date(2024, 2, 29))

    def test_monthly_dec_to_jan(self):
        self.assertEqual(advance_billing_date(date(2026, 12, 15), "MONTHLY"), date(2027, 1, 15))

    def test_yearly_normal(self):
        self.assertEqual(advance_billing_date(date(2026, 3, 15), "YEARLY"), date(2027, 3, 15))

    def test_yearly_leap_to_nonleap(self):
        # Feb 29 of a leap year → Feb 28 of next (non-leap) year
        self.assertEqual(advance_billing_date(date(2024, 2, 29), "YEARLY"), date(2025, 2, 28))


# ---------------------------------------------------------------------------
# 3. Full 12-step shared test path
# ---------------------------------------------------------------------------

class SharedTestPath(TestCase):
    """
    Follows the 12-step shared test path defined in the team contract.
    """

    def setUp(self):
        self.admin = _make_admin()
        self.staff = _make_staff()
        self.customer = _make_customer()
        self.tax = _make_tax()
        self.product = _make_product()
        self.variant = _make_variant(self.product, adj="200.00")
        self.plan = _make_plan(tax=self.tax)

    # Step 1-5: Customer, Tax, Product, Variant, Plan, Template, Quotation, Convert
    def _full_setup_via_quotation(self):
        # Step 3: QuotationTemplate
        template = QuotationTemplate.objects.create(
            name="Test Template", plan=self.plan, validity_days=15
        )
        QuotationTemplateLine.objects.create(
            template=template,
            product=self.product,
            variant=self.variant,
            quantity=1,
            unit_price=Decimal("1200.00"),
            tax=self.tax,
        )
        # Step 4: Quotation
        quotation = create_quotation_from_template(
            template=template, customer=self.customer, created_by=self.staff
        )
        # Step 5: Convert to Subscription
        subscription = convert_quotation_to_subscription(
            quotation.id, created_by=self.staff
        )
        return subscription

    def test_step_6_confirm_activate(self):
        sub = self._full_setup_via_quotation()
        # Step 6: confirm → activate
        sub = transition_subscription(sub.id, "confirm")
        self.assertEqual(sub.status, Subscription.Status.CONFIRMED)
        sub = transition_subscription(sub.id, "activate")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_step_7_run_billing_creates_invoice(self):
        """Step 7: POST /api/v1/billing/run/ creates a draft invoice."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        result = run_billing()
        self.assertGreaterEqual(result["invoices_created"], 1)
        invoice = Invoice.objects.get(subscription=sub)
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_step_8_confirm_invoice(self):
        """Step 8: Confirm the draft invoice."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        run_billing()
        invoice = Invoice.objects.get(subscription=sub)
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_step_9_partial_then_final_payment(self):
        """Step 9: Partial payment → balance > 0, then final payment."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        run_billing()
        invoice = Invoice.objects.get(subscription=sub)
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        balance = invoice.total
        partial = money(balance / 2)
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=partial,
            payment_date=date.today(), note="", reference="", recorded_by=self.staff,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertGreater(invoice.balance_due, 0)
        # Final payment
        record_payment(
            invoice_id=invoice.id, method="UPI", amount=invoice.balance_due,
            payment_date=date.today(), note="", reference="", recorded_by=self.staff,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_step_10_dashboard_revenue_changes(self):
        """Step 10: After full payment, revenue_collected increases."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        run_billing()
        invoice = Invoice.objects.get(subscription=sub)
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        before = _get_finance_summary_filtered()["revenue_collected"]
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=invoice.total,
            payment_date=date.today(), note="", reference="", recorded_by=self.staff,
        )
        after = _get_finance_summary_filtered()["revenue_collected"]
        self.assertGreater(after, before)

    def test_step_11_no_duplicate_invoice(self):
        """Step 11: Repeat billing run does not create a duplicate invoice."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        run_billing()
        count_before = Invoice.objects.filter(subscription=sub).count()
        result = run_billing()
        count_after = Invoice.objects.filter(subscription=sub).count()
        self.assertEqual(count_before, count_after)
        self.assertEqual(result["invoices_created"], 0)

        # Even if next_billing_date was somehow reset to period_start,
        # repeat billing repairs it and does not create duplicate invoices.
        sub.refresh_from_db()
        sub.next_billing_date = sub.start_date
        sub.save(update_fields=["next_billing_date"])
        result2 = run_billing()
        self.assertEqual(Invoice.objects.filter(subscription=sub).count(), count_before)
        self.assertEqual(result2["already_billed"], 1)
        self.assertEqual(result2["invoices_created"], 0)

    def test_step_12_customer_isolation(self):
        """Step 12: Second customer cannot see first customer's invoices."""
        sub = self._full_setup_via_quotation()
        transition_subscription(sub.id, "confirm")
        transition_subscription(sub.id, "activate")
        run_billing()
        invoice = Invoice.objects.get(subscription=sub)
        # Second customer
        other = _make_customer("other@test.local")
        c = Client()
        c.force_login(other)
        resp = c.get(reverse("billing-invoice-detail", args=[invoice.pk]))
        # Should 404 (customer queryset excludes other customers' invoices)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 4. Discount eligibility tests
# ---------------------------------------------------------------------------

class DiscountEligibilityTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.staff = _make_staff()
        self.customer = _make_customer()
        self.tax = _make_tax()
        self.product = _make_product("CRM", "1000.00")
        self.plan = _make_plan("Monthly", "500.00", tax=None)

    def _make_sub_with_line(self, product=None):
        p = product or self.product
        sub = _make_subscription(self.customer, self.plan, self.admin, lines=[
            {"product": p, "quantity": 1, "unit_price": p.sale_price, "tax": None}
        ])
        return sub

    def test_all_scope_discount_applied(self):
        """A FIXED ALL-scope discount reduces the invoice total."""
        DiscountRule.objects.create(
            name="Flat 100",
            discount_type="FIXED",
            value=Decimal("100.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, created = generate_invoice_for_subscription(sub.id)
        self.assertTrue(created)
        self.assertEqual(invoice.discount_amount, Decimal("100.00"))
        self.assertLess(invoice.total, invoice.subtotal)

    def test_percentage_discount(self):
        DiscountRule.objects.create(
            name="10%",
            discount_type="PERCENTAGE",
            value=Decimal("10.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        expected_discount = money(invoice.subtotal * Decimal("10") / Decimal("100"))
        self.assertEqual(invoice.discount_amount, expected_discount)

    def test_selected_products_scope(self):
        """SELECTED_PRODUCTS discount only applied if matching product in lines."""
        other_product = _make_product("Other", "800.00")
        rule = DiscountRule.objects.create(
            name="Specific",
            discount_type="FIXED",
            value=Decimal("50.00"),
            scope="SELECTED_PRODUCTS",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        rule.products.add(other_product)
        # Subscription without other_product → no discount
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        self.assertEqual(invoice.discount_amount, Decimal("0.00"))

    def test_selected_products_scope_match(self):
        """SELECTED_PRODUCTS discount applied when product matches."""
        rule = DiscountRule.objects.create(
            name="Specific Match",
            discount_type="FIXED",
            value=Decimal("50.00"),
            scope="SELECTED_PRODUCTS",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        rule.products.add(self.product)
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        self.assertGreater(invoice.discount_amount, Decimal("0.00"))

    def test_max_uses_exhausted(self):
        """Discount is not applied after max_uses is reached."""
        rule = DiscountRule.objects.create(
            name="Max 1",
            discount_type="FIXED",
            value=Decimal("100.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            max_uses=1,
            times_used=1,  # Already exhausted
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        self.assertEqual(invoice.discount_amount, Decimal("0.00"))

    def test_minimum_purchase_not_met(self):
        """Discount not applied if subtotal < minimum_purchase."""
        DiscountRule.objects.create(
            name="High Min",
            discount_type="FIXED",
            value=Decimal("100.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("99999.00"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        self.assertEqual(invoice.discount_amount, Decimal("0.00"))

    def test_expired_discount_not_applied(self):
        """Discount with valid_until in the past is not applied."""
        DiscountRule.objects.create(
            name="Expired",
            discount_type="FIXED",
            value=Decimal("100.00"),
            scope="ALL",
            valid_from=date(2020, 1, 1),
            valid_until=date(2020, 12, 31),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        self.assertEqual(invoice.discount_amount, Decimal("0.00"))

    def test_single_discount_only(self):
        """Only the best discount is applied (no stacking)."""
        DiscountRule.objects.create(
            name="Small",
            discount_type="FIXED",
            value=Decimal("50.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        DiscountRule.objects.create(
            name="Large",
            discount_type="FIXED",
            value=Decimal("200.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        # Only one redemption record
        self.assertEqual(invoice.discount_redemptions.count(), 1)
        # The larger discount is chosen
        self.assertEqual(invoice.discount_amount, Decimal("200.00"))

    def test_cancel_invoice_releases_discount_use(self):
        """Cancelling an invoice decrements times_used on the discount rule."""
        rule = DiscountRule.objects.create(
            name="Releasable",
            discount_type="FIXED",
            value=Decimal("100.00"),
            scope="ALL",
            valid_from=date.today(),
            is_active=True,
            minimum_purchase=Decimal("0"),
            minimum_quantity=1,
        )
        sub = self._make_sub_with_line()
        invoice, _ = generate_invoice_for_subscription(sub.id)
        rule.refresh_from_db()
        uses_after_billing = rule.times_used
        cancel_invoice(invoice.id)
        rule.refresh_from_db()
        self.assertEqual(rule.times_used, uses_after_billing - 1)


# ---------------------------------------------------------------------------
# 5. Tax calculation and snapshot stability
# ---------------------------------------------------------------------------

class TaxAndSnapshotTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.customer = _make_customer()
        self.tax = _make_tax("GST 18", "18.00")
        self.product = _make_product("Service", "1000.00")
        self.plan = _make_plan("Plan", "500.00", tax=self.tax)

    def test_plan_tax_included_in_invoice(self):
        """Plan tax is included in the invoice total."""
        sub = _make_subscription(self.customer, self.plan, self.admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        expected_plan_tax = money(Decimal("500.00") * Decimal("18") / Decimal("100"))
        self.assertGreaterEqual(invoice.tax_amount, expected_plan_tax)

    def test_line_tax_computed_correctly(self):
        """Line-level tax is calculated on net (after discount)."""
        sub = _make_subscription(self.customer, self.plan, self.admin, lines=[
            {"product": self.product, "quantity": 2, "unit_price": Decimal("1000.00"), "tax": self.tax}
        ])
        invoice, _ = generate_invoice_for_subscription(sub.id)
        # All line taxes should be > 0 (product lines have tax)
        product_lines = invoice.lines.filter(product__isnull=False)
        for line in product_lines:
            self.assertGreater(line.tax_amount, Decimal("0"))
            expected = money(line.line_subtotal * Decimal("18") / Decimal("100"))
            self.assertEqual(line.tax_amount, expected)

    def test_snapshot_stability(self):
        """Editing catalogue price after billing doesn't change the invoice line."""
        sub = _make_subscription(self.customer, self.plan, self.admin, lines=[
            {"product": self.product, "quantity": 1, "unit_price": Decimal("1000.00"), "tax": self.tax}
        ])
        invoice, _ = generate_invoice_for_subscription(sub.id)
        original_unit = invoice.lines.filter(product=self.product).first().unit_price
        # Mutate catalogue price
        self.product.sale_price = Decimal("9999.00")
        self.product.save()
        # Reload invoice line — must not have changed
        invoice.refresh_from_db()
        line = invoice.lines.filter(product=self.product).first()
        self.assertEqual(line.unit_price, original_unit)


# ---------------------------------------------------------------------------
# 6. Invoice workflow: confirm, cancel, send
# ---------------------------------------------------------------------------

class InvoiceWorkflowTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.customer = _make_customer()
        self.plan = _make_plan()
        self.sub = _make_subscription(self.customer, self.plan, self.admin)

    def _make_invoice(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        return invoice

    def test_confirm_draft_invoice(self):
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_cannot_confirm_non_draft(self):
        from django.core.exceptions import ValidationError
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        with self.assertRaises(ValidationError):
            confirm_invoice(invoice.id)

    def test_cancel_draft_invoice(self):
        invoice = self._make_invoice()
        cancel_invoice(invoice.id)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    def test_cancel_confirmed_invoice(self):
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        cancel_invoice(invoice.id)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    def test_cannot_cancel_paid_invoice(self):
        from django.core.exceptions import ValidationError
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=invoice.total,
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        invoice.refresh_from_db()
        with self.assertRaises(ValidationError):
            cancel_invoice(invoice.id)

    def test_cannot_cancel_invoice_with_payments(self):
        from django.core.exceptions import ValidationError
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=money(invoice.total / 2),
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            cancel_invoice(invoice.id)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_invoice_html_view(self):
        """Invoice send view records sent_at and triggers email."""
        invoice = self._make_invoice()
        confirm_invoice(invoice.id)
        c = Client()
        c.force_login(self.admin)
        url = reverse("billing-invoice-send", args=[invoice.pk])
        resp = c.post(url)
        self.assertRedirects(resp, reverse("billing-invoice-detail", args=[invoice.pk]))
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.sent_at)
        # Email is sent via locmem backend
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invoice.number, mail.outbox[0].subject)

    def test_cannot_send_cancelled_invoice(self):
        invoice = self._make_invoice()
        cancel_invoice(invoice.id)
        c = Client()
        c.force_login(self.admin)
        c.post(reverse("billing-invoice-send", args=[invoice.pk]))
        invoice.refresh_from_db()
        self.assertIsNone(invoice.sent_at)


# ---------------------------------------------------------------------------
# 7. Payment recording
# ---------------------------------------------------------------------------

class PaymentTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.customer = _make_customer()
        self.plan = _make_plan(price="1000.00")
        self.sub = _make_subscription(self.customer, self.plan, self.admin)
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        self.invoice = Invoice.objects.get(pk=invoice.pk)

    def test_partial_payment_leaves_confirmed(self):
        balance = self.invoice.total
        partial = money(balance / 2)
        record_payment(
            invoice_id=self.invoice.id, method="CASH", amount=partial,
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)
        self.assertGreater(self.invoice.balance_due, 0)

    def test_full_payment_marks_paid(self):
        record_payment(
            invoice_id=self.invoice.id, method="UPI", amount=self.invoice.total,
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_overpayment_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            record_payment(
                invoice_id=self.invoice.id, method="CASH",
                amount=self.invoice.total + Decimal("1.00"),
                payment_date=date.today(), note="", reference="", recorded_by=self.admin,
            )

    def test_cannot_pay_draft_invoice(self):
        from django.core.exceptions import ValidationError
        # Create a fresh draft invoice on a new sub
        plan2 = _make_plan("Monthly2", price="500.00")
        sub2 = _make_subscription(self.customer, plan2, self.admin, start=date.today() + timedelta(days=1))
        sub2.next_billing_date = date.today() + timedelta(days=1)
        sub2.save(update_fields=["next_billing_date"])
        # Manually create a draft invoice
        invoice = Invoice.objects.create(
            subscription=sub2, customer=self.customer,
            period_start=date.today() + timedelta(days=1),
            period_end=date.today() + timedelta(days=31),
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=15),
            total=Decimal("500.00"),
            status=Invoice.Status.DRAFT,
        )
        with self.assertRaises(ValidationError):
            record_payment(
                invoice_id=invoice.id, method="CASH", amount=Decimal("100.00"),
                payment_date=date.today(), note="", reference="", recorded_by=self.admin,
            )

    def test_cannot_pay_cancelled_invoice(self):
        from django.core.exceptions import ValidationError
        cancel_invoice(self.invoice.id)
        with self.assertRaises(ValidationError):
            record_payment(
                invoice_id=self.invoice.id, method="CASH", amount=Decimal("100.00"),
                payment_date=date.today(), note="", reference="", recorded_by=self.admin,
            )

    def test_zero_amount_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            record_payment(
                invoice_id=self.invoice.id, method="CASH", amount=Decimal("0.00"),
                payment_date=date.today(), note="", reference="", recorded_by=self.admin,
            )


# ---------------------------------------------------------------------------
# 8. Overdue calculation
# ---------------------------------------------------------------------------

class OverdueTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.customer = _make_customer()
        self.plan = _make_plan(price="1000.00")
        self.sub = _make_subscription(self.customer, self.plan, self.admin)

    def test_overdue_confirmed_past_due_date(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        # Manually push due_date to the past
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_overdue)

    def test_not_overdue_if_paid(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        invoice.refresh_from_db()
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=invoice.total,
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        invoice.refresh_from_db()
        self.assertFalse(invoice.is_overdue)

    def test_not_overdue_if_draft(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        invoice.refresh_from_db()
        self.assertFalse(invoice.is_overdue)

    def test_dashboard_overdue_count(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        summary = _get_finance_summary_filtered()
        self.assertGreaterEqual(summary["overdue_invoice_count"], 1)
        self.assertGreater(summary["overdue_amount"], 0)


# ---------------------------------------------------------------------------
# 9. Idempotent billing
# ---------------------------------------------------------------------------

class IdempotentBillingTests(TestCase):
    def test_no_duplicate_on_repeated_run(self):
        admin = _make_admin()
        customer = _make_customer()
        plan = _make_plan()
        sub = _make_subscription(customer, plan, admin)
        run_billing()
        count_1 = Invoice.objects.filter(subscription=sub).count()
        result = run_billing()
        count_2 = Invoice.objects.filter(subscription=sub).count()
        self.assertEqual(count_1, count_2)
        self.assertEqual(result["invoices_created"], 0)

        # Out-of-sync retry
        sub.refresh_from_db()
        sub.next_billing_date = sub.start_date
        sub.save(update_fields=["next_billing_date"])
        result2 = run_billing()
        self.assertEqual(result2["already_billed"], 1)
        self.assertEqual(result2["invoices_created"], 0)
        self.assertEqual(Invoice.objects.filter(subscription=sub).count(), count_1)

    def test_generate_invoice_idempotent(self):
        """Direct call to generate_invoice_for_subscription is idempotent when next_billing_date matches period_start."""
        admin = _make_admin()
        customer = _make_customer()
        plan = _make_plan()
        sub = _make_subscription(customer, plan, admin)
        invoice1, created1 = generate_invoice_for_subscription(sub.id)
        self.assertTrue(created1)
        # Reset next_billing_date to period_start to test existing invoice detection & repair
        sub.refresh_from_db()
        sub.next_billing_date = invoice1.period_start
        sub.save(update_fields=["next_billing_date"])
        invoice2, created2 = generate_invoice_for_subscription(sub.id)
        self.assertFalse(created2)
        self.assertEqual(invoice1.id, invoice2.id)


# ---------------------------------------------------------------------------
# 10. HTML view permission tests
# ---------------------------------------------------------------------------

class HtmlViewPermissionTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.staff = _make_staff()
        self.customer = _make_customer()
        self.plan = _make_plan()
        self.sub = _make_subscription(self.customer, self.plan, self.admin)
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        self.invoice = invoice

    def test_invoice_list_requires_login(self):
        c = Client()
        resp = c.get(reverse("billing-invoice-list"))
        self.assertRedirects(resp, "/accounts/login/?next=" + reverse("billing-invoice-list"))

    def test_invoice_list_forbidden_for_customer(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get(reverse("billing-invoice-list"))
        self.assertEqual(resp.status_code, 403)

    def test_invoice_list_accessible_to_staff(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("billing-invoice-list"))
        self.assertEqual(resp.status_code, 200)

    def test_invoice_detail_accessible_to_owner_customer(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get(reverse("billing-invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_invoice_detail_403_other_customer(self):
        c = Client()
        other = _make_customer("other2@test.local")
        c.force_login(other)
        resp = c.get(reverse("billing-invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_discount_list_requires_staff(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get(reverse("billing-discount-list"))
        self.assertEqual(resp.status_code, 403)

    def test_discount_list_accessible_to_admin(self):
        c = Client()
        c.force_login(self.admin)
        resp = c.get(reverse("billing-discount-list"))
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_requires_staff(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get(reverse("finance-dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_finance_dashboard_ok_for_staff(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_confirm_action_via_html(self):
        c = Client()
        c.force_login(self.staff)
        url = reverse("billing-invoice-confirm", args=[self.invoice.pk])
        resp = c.post(url)
        self.assertRedirects(resp, reverse("billing-invoice-detail", args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)

    def test_cancel_action_via_html(self):
        c = Client()
        c.force_login(self.staff)
        c.post(reverse("billing-invoice-cancel", args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.CANCELLED)

    def test_payment_via_html(self):
        c = Client()
        c.force_login(self.staff)
        confirm_invoice(self.invoice.id)
        self.invoice.refresh_from_db()
        url = reverse("billing-invoice-payment", args=[self.invoice.pk])
        resp = c.post(url, {
            "method": "CASH",
            "amount": str(self.invoice.total),
            "payment_date": str(date.today()),
            "reference": "",
            "note": "",
        })
        self.assertRedirects(resp, reverse("billing-invoice-detail", args=[self.invoice.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_run_billing_html_post_staff(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.post(reverse("billing-run"))
        self.assertRedirects(resp, reverse("billing-invoice-list"))

    def test_run_billing_html_post_with_next(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.post(reverse("billing-run"), {"next": reverse("finance-dashboard")})
        self.assertRedirects(resp, reverse("finance-dashboard"))

    def test_run_billing_html_post_admin(self):
        c = Client()
        c.force_login(self.admin)
        resp = c.post(reverse("billing-run"))
        self.assertRedirects(resp, reverse("billing-invoice-list"))

    def test_run_billing_html_post_customer_blocked(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.post(reverse("billing-run"))
        self.assertEqual(resp.status_code, 403)

    def test_run_billing_html_get_method_not_allowed(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("billing-run"))
        self.assertEqual(resp.status_code, 405)

    def test_billing_root_redirect(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/billing/")
        self.assertRedirects(resp, reverse("billing-invoice-list"))


# ---------------------------------------------------------------------------
# 11. Discount rule form / CRUD
# ---------------------------------------------------------------------------

class DiscountRuleCRUDTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.product = _make_product()

    def test_create_discount_rule_via_form(self):
        c = Client()
        c.force_login(self.admin)
        resp = c.post(reverse("billing-discount-create"), {
            "name": "Test Disc",
            "discount_type": "FIXED",
            "value": "100",
            "scope": "ALL",
            "minimum_purchase": "0",
            "minimum_quantity": "1",
            "valid_from": str(date.today()),
            "is_active": "on",
            "products": [],
        })
        self.assertRedirects(resp, reverse("billing-discount-list"))
        self.assertTrue(DiscountRule.objects.filter(name="Test Disc").exists())

    def test_create_selected_products_without_products_fails(self):
        c = Client()
        c.force_login(self.admin)
        resp = c.post(reverse("billing-discount-create"), {
            "name": "Bad Scope",
            "discount_type": "FIXED",
            "value": "50",
            "scope": "SELECTED_PRODUCTS",
            "minimum_purchase": "0",
            "minimum_quantity": "1",
            "valid_from": str(date.today()),
            "is_active": "on",
        })
        # Form should re-render with errors; not redirect
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DiscountRule.objects.filter(name="Bad Scope").exists())

    def test_delete_rule_with_redemption_blocked(self):
        c = Client()
        c.force_login(self.admin)
        rule = DiscountRule.objects.create(
            name="BlockedDel", discount_type="FIXED", value="10",
            scope="ALL", valid_from=date.today(), is_active=True,
            minimum_purchase="0", minimum_quantity=1,
        )
        # Create a customer + subscription + invoice so a redemption exists
        customer = _make_customer("del_cust@test.local")
        plan = _make_plan("DelPlan", price="200.00")
        sub = _make_subscription(customer, plan, self.admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        # Redemption was created by generate_invoice_for_subscription
        self.assertTrue(DiscountRedemption.objects.filter(discount_rule=rule).exists())
        # Try to delete
        resp = c.post(reverse("billing-discount-delete", args=[rule.pk]))
        self.assertRedirects(resp, reverse("billing-discount-list"))
        self.assertTrue(DiscountRule.objects.filter(pk=rule.pk).exists())


# ---------------------------------------------------------------------------
# 12. Finance dashboard filter tests
# ---------------------------------------------------------------------------

class FinanceDashboardFilterTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.staff = _make_staff()
        self.customer = _make_customer()
        self.plan = _make_plan(price="1000.00")
        self.sub = _make_subscription(self.customer, self.plan, self.admin)

    def test_filter_by_status_draft(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        summary = _get_finance_summary_filtered(status_filter="DRAFT")
        ids = list(summary["invoice_queryset"].values_list("id", flat=True))
        self.assertIn(invoice.id, ids)

    def test_filter_confirmed_excludes_draft(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        summary = _get_finance_summary_filtered(status_filter="CONFIRMED")
        ids = list(summary["invoice_queryset"].values_list("id", flat=True))
        self.assertNotIn(invoice.id, ids)

    def test_filter_overdue_only(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        summary = _get_finance_summary_filtered(overdue_only=True)
        ids = list(summary["invoice_queryset"].values_list("id", flat=True))
        self.assertIn(invoice.id, ids)

    def test_filter_by_date_range(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        # Filter with dates far in the future — should exclude today's invoice
        summary = _get_finance_summary_filtered(
            start_date=date(2099, 1, 1), end_date=date(2099, 12, 31)
        )
        ids = list(summary["invoice_queryset"].values_list("id", flat=True))
        self.assertNotIn(invoice.id, ids)

    def test_search_by_invoice_number(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        summary = _get_finance_summary_filtered(search=invoice.number)
        ids = list(summary["invoice_queryset"].values_list("id", flat=True))
        self.assertIn(invoice.id, ids)

    def test_search_no_match(self):
        generate_invoice_for_subscription(self.sub.id)
        summary = _get_finance_summary_filtered(search="XXXXNOTMATCH")
        self.assertEqual(summary["invoice_queryset"].count(), 0)

    def test_finance_dashboard_html_filter(self):
        """HTML finance dashboard respects query-string filters."""
        c = Client()
        c.force_login(self.staff)
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        resp = c.get(reverse("finance-dashboard"), {"status": "DRAFT"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, invoice.number)

    def test_api_summary_endpoint(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/api/v1/dashboard/summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("revenue_collected", data)
        self.assertIn("outstanding_amount", data)


# ---------------------------------------------------------------------------
# 13. Invoice print view
# ---------------------------------------------------------------------------

class InvoicePrintTests(TestCase):
    def test_print_view_staff(self):
        admin = _make_admin()
        customer = _make_customer()
        plan = _make_plan()
        sub = _make_subscription(customer, plan, admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        c = Client()
        c.force_login(admin)
        resp = c.get(reverse("billing-invoice-print", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, invoice.number)

    def test_print_view_own_invoice_customer(self):
        admin = _make_admin()
        customer = _make_customer()
        plan = _make_plan()
        sub = _make_subscription(customer, plan, admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        c = Client()
        c.force_login(customer)
        resp = c.get(reverse("billing-invoice-print", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_print_view_other_customer_404(self):
        admin = _make_admin()
        customer = _make_customer()
        other = _make_customer("other_print@test.local")
        plan = _make_plan()
        sub = _make_subscription(customer, plan, admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        c = Client()
        c.force_login(other)
        resp = c.get(reverse("billing-invoice-print", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 404)
