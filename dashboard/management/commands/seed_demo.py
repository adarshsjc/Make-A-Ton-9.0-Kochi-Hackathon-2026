import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import User, CustomerProfile
from catalog.models import Product, ProductVariant, Tax, Plan
from subscriptions.models import QuotationTemplate, QuotationTemplateLine, Subscription, SubscriptionLine

class Command(BaseCommand):
    help = "Create local demo users and sample catalog/subscription records. Development only."

    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "BrightloopDemo!2026")
        admin, created = User.objects.get_or_create(email="admin@brightloop.local", defaults={"full_name": "Brightloop Admin", "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True})
        if created: admin.set_password(password); admin.save()
        staff, created = User.objects.get_or_create(email="staff@brightloop.local", defaults={"full_name": "Brightloop Staff", "role": User.Role.STAFF})
        if created: staff.set_password(password); staff.save()
        customer, created = User.objects.get_or_create(email="customer@brightloop.local", defaults={"full_name": "Demo Customer", "role": User.Role.CUSTOMER})
        if created: customer.set_password(password); customer.save()
        CustomerProfile.objects.get_or_create(user=customer, defaults={"company_name": "Demo Retail Pvt Ltd", "billing_address": "Kochi, Kerala, India"})

        tax, _ = Tax.objects.get_or_create(name="GST Demo 18%", defaults={"rate": "18.00"})
        product, _ = Product.objects.get_or_create(name="CRM Brand Add-on", defaults={"product_type": Product.ProductType.ADD_ON, "sale_price": "1000.00", "cost_price": "250.00", "notes": "Demo brand add-on"})
        variant, _ = ProductVariant.objects.get_or_create(product=product, attribute_name="Brand", value="Odoo", defaults={"price_adjustment": "560.00"})
        plan, _ = Plan.objects.get_or_create(name="Monthly Starter", defaults={"price": "1000.00", "billing_interval": Plan.BillingInterval.MONTHLY, "minimum_quantity": 1, "available_from": timezone.localdate(), "allow_pause": True, "allow_renew": True, "allow_early_close": True, "tax": tax})
        template, _ = QuotationTemplate.objects.get_or_create(name="Starter CRM Quote", defaults={"plan": plan, "validity_days": 15})
        QuotationTemplateLine.objects.get_or_create(template=template, product=product, variant=variant, defaults={"quantity": 1, "unit_price": "1560.00", "tax": tax})

        if not Subscription.objects.filter(customer=customer, plan=plan).exists():
            subscription = Subscription.objects.create(customer=customer, plan=plan, created_by=admin, start_date=timezone.localdate(), expiry_date=timezone.localdate() + timedelta(days=365), payment_terms_days=15, status=Subscription.Status.ACTIVE)
            SubscriptionLine.objects.create(subscription=subscription, product=product, variant=variant, product_name=product.name, variant_description="Brand: Odoo", quantity=1, unit_price="1560.00", tax=tax, tax_rate_snapshot=tax.rate)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("Demo accounts: admin@brightloop.local, staff@brightloop.local, customer@brightloop.local")
        self.stdout.write("Password: value of DEMO_PASSWORD in .env (development only)")
