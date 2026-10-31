"""
Dashboard tests for Member C — Finance Dashboard.
Tests the existing DashboardHomeView, DashboardSummaryAPIView,
and the new FinanceDashboardView.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from billing.models import Invoice
from billing.services import (
    confirm_invoice,
    generate_invoice_for_subscription,
    record_payment,
    run_billing,
)
from catalog.models import Plan, Product, ProductVariant, Tax
from subscriptions.models import Subscription, SubscriptionLine
from django.utils import timezone

User = get_user_model()


def _make_admin(email="dash_admin@test.local"):
    return User.objects.create_user(
        email=email, password="AdminPass!9",
        full_name="Admin", role="ADMIN", is_staff=True, is_superuser=True,
    )


def _make_staff(email="dash_staff@test.local"):
    return User.objects.create_user(
        email=email, password="StaffPass!9",
        full_name="Staff", role="STAFF",
    )


def _make_customer(email="dash_cust@test.local"):
    return User.objects.create_user(
        email=email, password="CustPass!99",
        full_name="Customer", role="CUSTOMER",
    )


def _make_plan(name="Dash Plan", price="1000.00"):
    return Plan.objects.create(
        name=name, price=Decimal(price), billing_interval="MONTHLY",
        available_from=date.today(), allow_pause=True, allow_renew=True, allow_early_close=True,
    )


def _make_sub(customer, plan, admin, start=None):
    today = start or date.today()
    return Subscription.objects.create(
        customer=customer, plan=plan, created_by=admin,
        start_date=today, payment_terms_days=15,
        status=Subscription.Status.ACTIVE, activated_at=timezone.now(),
    )


class DashboardHomeViewTests(TestCase):
    """Tests for the existing DashboardHomeView."""

    def test_redirect_unauthenticated(self):
        c = Client()
        resp = c.get(reverse("dashboard-home"))
        self.assertRedirects(resp, "/accounts/login/?next=/")

    def test_staff_sees_metrics(self):
        admin = _make_admin()
        c = Client()
        c.force_login(admin)
        resp = c.get(reverse("dashboard-home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Subscription overview")

    def test_customer_sees_portal(self):
        customer = _make_customer()
        c = Client()
        c.force_login(customer)
        resp = c.get(reverse("dashboard-home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Welcome")

    def test_customer_sees_own_invoices(self):
        admin = _make_admin(email="admin_dh@test.local")
        customer = _make_customer(email="cust_dh@test.local")
        plan = _make_plan("DashHomePlan")
        sub = _make_sub(customer, plan, admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        c = Client()
        c.force_login(customer)
        resp = c.get(reverse("dashboard-home"))
        self.assertContains(resp, invoice.number)

    def test_customer_does_not_see_other_invoices(self):
        admin = _make_admin(email="admin_dh2@test.local")
        customer1 = _make_customer(email="c1@test.local")
        customer2 = _make_customer(email="c2@test.local")
        plan = _make_plan("DashHomePlan2")
        sub1 = _make_sub(customer1, plan, admin)
        sub2 = _make_sub(customer2, _make_plan("Plan2b"), admin)
        invoice1, _ = generate_invoice_for_subscription(sub1.id)
        invoice2, _ = generate_invoice_for_subscription(sub2.id)
        c = Client()
        c.force_login(customer2)
        resp = c.get(reverse("dashboard-home"))
        self.assertNotContains(resp, invoice1.number)
        self.assertContains(resp, invoice2.number)


class DashboardSummaryAPITests(TestCase):
    """Tests for DashboardSummaryAPIView."""

    def setUp(self):
        self.admin = _make_admin()
        self.staff = _make_staff()
        self.customer = _make_customer()

    def test_returns_200_for_staff(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/api/v1/dashboard/summary/")
        self.assertEqual(resp.status_code, 200)

    def test_returns_403_for_customer(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get("/api/v1/dashboard/summary/")
        self.assertEqual(resp.status_code, 403)

    def test_returns_401_unauthenticated(self):
        c = Client()
        resp = c.get("/api/v1/dashboard/summary/")
        self.assertEqual(resp.status_code, 403)  # DRF returns 403 not 401 for session auth

    def test_revenue_collected_reflects_payments(self):
        plan = _make_plan("API Sum Plan")
        sub = _make_sub(self.customer, plan, self.admin)
        invoice, _ = generate_invoice_for_subscription(sub.id)
        confirm_invoice(invoice.id)
        invoice.refresh_from_db()
        record_payment(
            invoice_id=invoice.id, method="CASH", amount=invoice.total,
            payment_date=date.today(), note="", reference="", recorded_by=self.admin,
        )
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/api/v1/dashboard/summary/")
        data = resp.json()
        self.assertGreater(Decimal(str(data["revenue_collected"])), Decimal("0"))

    def test_date_filter_params(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/api/v1/dashboard/summary/", {"start_date": "2020-01-01", "end_date": "2020-12-31"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(Decimal(str(data["revenue_collected"])), Decimal("0.00"))

    def test_invalid_date_returns_400(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get("/api/v1/dashboard/summary/", {"start_date": "not-a-date"})
        self.assertEqual(resp.status_code, 400)


class FinanceDashboardHTMLTests(TestCase):
    """Tests for the new HTML Finance Dashboard."""

    def setUp(self):
        self.admin = _make_admin(email="fadmin@test.local")
        self.staff = _make_staff(email="fstaff@test.local")
        self.customer = _make_customer(email="fcust@test.local")
        self.plan = _make_plan("Finance Plan")
        self.sub = _make_sub(self.customer, self.plan, self.admin)

    def test_finance_dashboard_shows_metrics(self):
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Revenue collected")
        self.assertContains(resp, "Outstanding")
        self.assertContains(resp, "Overdue")

    def test_finance_dashboard_lists_invoices(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"))
        self.assertContains(resp, invoice.number)

    def test_finance_dashboard_status_filter(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"), {"status": "CONFIRMED"})
        self.assertContains(resp, invoice.number)

    def test_finance_dashboard_excludes_cancelled(self):
        """The finance dashboard excludes CANCELLED invoices from aggregates."""
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        from billing.services import cancel_invoice
        cancel_invoice(invoice.id)
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"))
        self.assertNotContains(resp, invoice.number)

    def test_finance_dashboard_overdue_filter(self):
        invoice, _ = generate_invoice_for_subscription(self.sub.id)
        confirm_invoice(invoice.id)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2020, 1, 1))
        c = Client()
        c.force_login(self.staff)
        resp = c.get(reverse("finance-dashboard"), {"overdue": "1"})
        self.assertContains(resp, invoice.number)

    def test_finance_dashboard_customer_forbidden(self):
        c = Client()
        c.force_login(self.customer)
        resp = c.get(reverse("finance-dashboard"))
        self.assertEqual(resp.status_code, 403)
