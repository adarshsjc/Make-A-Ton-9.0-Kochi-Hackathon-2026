from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from .models import Product, ProductVariant, Tax, Plan

class ProductTests(TestCase):
    def test_product_creation_and_positive_price(self):
        prod = Product.objects.create(
            name="Cloud Storage 100GB",
            product_type=Product.ProductType.SERVICE,
            sale_price=Decimal("499.00"),
            cost_price=Decimal("150.00"),
            description="High-speed secure cloud storage"
        )
        self.assertEqual(prod.name, "Cloud Storage 100GB")
        self.assertEqual(prod.description, "High-speed secure cloud storage")
        self.assertTrue(prod.is_active)

    def test_product_variant_and_price_adjustment(self):
        prod = Product.objects.create(
            name="Business Email",
            product_type=Product.ProductType.SERVICE,
            sale_price=Decimal("200.00"),
            cost_price=Decimal("50.00"),
        )
        variant = ProductVariant.objects.create(
            product=prod,
            attribute_name="Seats",
            value="10 Users",
            sku="EMAIL-10U",
            price_adjustment=Decimal("350.00"),
        )
        self.assertEqual(variant.product, prod)
        self.assertEqual(variant.sku, "EMAIL-10U")
        total_unit_price = prod.sale_price + variant.price_adjustment
        self.assertEqual(total_unit_price, Decimal("550.00"))

    def test_tax_rate_positive(self):
        tax = Tax.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.assertEqual(tax.rate, Decimal("18.00"))
        self.assertTrue(tax.is_active)

    def test_plan_creation_and_interval(self):
        plan = Plan.objects.create(
            name="Pro Annual",
            price=Decimal("9999.00"),
            billing_interval=Plan.BillingInterval.YEARLY,
            interval_count=1,
            minimum_quantity=1,
            available_from=timezone.localdate(),
            allow_pause=True,
            allow_renew=True,
        )
        self.assertEqual(plan.billing_interval, Plan.BillingInterval.YEARLY)
        self.assertEqual(plan.min_quantity, 1)

    def test_plan_invalid_availability_dates(self):
        today = timezone.localdate()
        plan = Plan(
            name="Invalid Dates Plan",
            price=Decimal("100.00"),
            available_from=today,
            available_until=today - timedelta(days=5),
        )
        with self.assertRaises(ValidationError):
            plan.clean()

    def test_product_variants_api_endpoint(self):
        from accounts.models import User
        admin = User.objects.create_superuser(
            email="catalog_admin@brightloop.local",
            password="AdminPassword123!",
            full_name="Catalog Admin"
        )
        self.client.force_login(admin)
        prod = Product.objects.create(
            name="API Test Product",
            sale_price=Decimal("100.00"),
            cost_price=Decimal("20.00"),
        )
        resp = self.client.post(f"/api/v1/products/{prod.id}/variants/", {
            "attribute_name": "Color",
            "value": "Red",
            "price_adjustment": "25.00"
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(prod.variants.count(), 1)

        get_resp = self.client.get(f"/api/v1/products/{prod.id}/variants/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(len(get_resp.data), 1)

