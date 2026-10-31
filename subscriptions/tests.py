from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from accounts.models import User, CustomerProfile
from catalog.models import Plan, Product, ProductVariant, Tax
from .models import Quotation, QuotationLine, Subscription, SubscriptionLine
from .services import (
    advance_billing_date,
    create_custom_quotation,
    convert_quotation_to_subscription,
    transition_subscription,
)

class BillingDateTests(TestCase):
    def test_month_end_clamps_to_last_day(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 31), Plan.BillingInterval.MONTHLY), date(2026, 2, 28))

    def test_leap_day_yearly_clamps(self):
        self.assertEqual(advance_billing_date(date(2024, 2, 29), Plan.BillingInterval.YEARLY), date(2025, 2, 28))

    def test_interval_count(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 15), Plan.BillingInterval.MONTHLY, count=3), date(2026, 4, 15))


class SubscriptionWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin_test@brightloop.local",
            password="TestPassword123!",
            role=User.Role.ADMIN,
            is_staff=True,
            full_name="Admin Test"
        )
        self.customer = User.objects.create_user(
            email="client@company.com",
            password="TestPassword123!",
            role=User.Role.CUSTOMER,
            full_name="Jane Doe"
        )
        self.profile = CustomerProfile.objects.create(
            user=self.customer,
            company_name="Acme Corp",
            billing_address="123 Tech Park, Kochi",
            tax_identifier="GSTIN123456"
        )
        self.tax = Tax.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.plan = Plan.objects.create(
            name="SaaS Growth",
            price=Decimal("1500.00"),
            billing_interval=Plan.BillingInterval.MONTHLY,
            interval_count=1,
            minimum_quantity=1,
            available_from=timezone.localdate() - timedelta(days=10),
            allow_pause=True,
            allow_renew=True,
            allow_early_close=True,
            tax=self.tax,
        )
        self.product = Product.objects.create(
            name="User Seat License",
            product_type=Product.ProductType.SOFTWARE,
            sale_price=Decimal("250.00"),
            cost_price=Decimal("50.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            attribute_name="Tier",
            value="Enterprise",
            price_adjustment=Decimal("100.00"),
        )

    def test_create_custom_quotation_and_conversion(self):
        lines_data = [{
            "product": self.product,
            "variant": self.variant,
            "tax": self.tax,
            "quantity": 2,
        }]
        quote = create_custom_quotation(
            customer=self.customer,
            plan=self.plan,
            lines_data=lines_data,
            created_by=self.admin,
            valid_days=15,
        )
        self.assertEqual(quote.status, Quotation.Status.DRAFT)
        self.assertEqual(quote.lines.count(), 1)
        line = quote.lines.first()
        # Price should be product.sale_price + variant.price_adjustment = 250 + 100 = 350
        self.assertEqual(line.unit_price, Decimal("350.00"))
        self.assertEqual(line.subtotal, Decimal("700.00"))

        # Convert quotation to subscription
        sub = convert_quotation_to_subscription(quote.id, created_by=self.admin)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, Subscription.Status.QUOTATION)
        self.assertEqual(sub.plan_price_snapshot, Decimal("1500.00"))
        self.assertEqual(sub.lines.count(), 1)
        sub_line = sub.lines.first()
        self.assertEqual(sub_line.unit_price, Decimal("350.00"))
        self.assertEqual(sub_line.tax_rate_snapshot, Decimal("18.00"))
        self.assertIn("Enterprise", sub_line.description_snapshot)

        # Verify quote marked ACCEPTED
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quotation.Status.ACCEPTED)

    def test_subscription_lifecycle_transitions(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            created_by=self.admin,
            start_date=timezone.localdate(),
            status=Subscription.Status.QUOTATION,
        )
        # Quotation -> Confirmed
        transition_subscription(sub.id, "confirm")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CONFIRMED)

        # Confirmed -> Active
        transition_subscription(sub.id, "activate")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(sub.activated_at)

        # Active -> Paused
        transition_subscription(sub.id, "pause")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAUSED)

        # Paused -> Active (Resume)
        transition_subscription(sub.id, "resume")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.next_billing_date, timezone.localdate())

        # Active -> Renew
        transition_subscription(sub.id, "renew")
        sub.refresh_from_db()
        self.assertIsNotNone(sub.expiry_date)

        # Active -> Closed
        transition_subscription(sub.id, "close")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CLOSED)
        self.assertIsNotNone(sub.closed_at)

    def test_pause_rejected_if_plan_disallows(self):
        self.plan.allow_pause = False
        self.plan.save()
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            created_by=self.admin,
            start_date=timezone.localdate(),
            status=Subscription.Status.ACTIVE,
        )
        with self.assertRaises(ValidationError):
            transition_subscription(sub.id, "pause")

    def test_renew_rejected_if_plan_disallows(self):
        self.plan.allow_renew = False
        self.plan.save()
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            created_by=self.admin,
            start_date=timezone.localdate(),
            status=Subscription.Status.ACTIVE,
        )
        with self.assertRaises(ValidationError):
            transition_subscription(sub.id, "renew")

    def test_member_c_integration_readiness(self):
        """Verifies Member C billing engine can read subscription and line data."""
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            plan_price_snapshot=self.plan.price,
            created_by=self.admin,
            start_date=timezone.localdate(),
            status=Subscription.Status.ACTIVE,
        )
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            variant=self.variant,
            product_name=self.product.name,
            variant_description="Tier: Enterprise",
            description_snapshot="User Seat License (Tier: Enterprise)",
            quantity=3,
            unit_price=Decimal("350.00"),
            tax=self.tax,
            tax_rate_snapshot=self.tax.rate,
        )
        # Check Member C contracts
        self.assertEqual(sub.plan_price_snapshot, Decimal("1500.00"))
        self.assertEqual(sub.customer, self.customer)
        self.assertEqual(sub.customer_profile.company_name, "Acme Corp")
        lines = list(sub.lines.all())
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].description_snapshot, "User Seat License (Tier: Enterprise)")
        self.assertEqual(lines[0].tax_rate_snapshot, Decimal("18.00"))
        self.assertEqual(lines[0].unit_price, Decimal("350.00"))
        self.assertEqual(lines[0].quantity, 3)

    def test_pages_render(self):
        self.client.force_login(self.admin)
        # Create a quotation without a template to test rendering
        Quotation.objects.create(
            customer=self.customer,
            plan=self.plan,
            template=None,
            created_by=self.admin,
            valid_until=timezone.localdate() + timedelta(days=15),
        )
        r1 = self.client.get("/subscriptions/")
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.get("/subscriptions/quotations/new/")
        self.assertEqual(r2.status_code, 200)
        r3 = self.client.get("/catalog/products/")
        self.assertEqual(r3.status_code, 200)
        r4 = self.client.get("/catalog/plans/")
        self.assertEqual(r4.status_code, 200)
        r5 = self.client.get("/api/v1/subscriptions/page/")
        self.assertEqual(r5.status_code, 200)


