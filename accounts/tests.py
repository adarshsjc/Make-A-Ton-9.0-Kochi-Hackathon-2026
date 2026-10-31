from unittest.mock import patch

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import CustomerProfile, User
from .services import create_customer_account


VALID_PASSWORD = "V3ry$trong-Unique-91"


class UserModelTests(TestCase):
    def test_email_is_case_normalized(self):
        user = User.objects.create_user(
            email="Example@Mail.com", password=VALID_PASSWORD, full_name="Example"
        )
        self.assertEqual(user.email, "example@mail.com")

    def test_customer_role_is_default(self):
        user = User.objects.create_user(
            email="a@example.com", password=VALID_PASSWORD, full_name="A"
        )
        self.assertEqual(user.role, User.Role.CUSTOMER)

    def test_password_requires_special_character(self):
        with self.assertRaises(ValidationError):
            validate_password("StrongPassword9")


class CustomerAccountServiceTests(TestCase):
    def test_user_and_customer_profile_are_created_together(self):
        user = create_customer_account(
            email=" MATRIX@EXAMPLE.COM ",
            password=VALID_PASSWORD,
            full_name="Matrix User",
            company_name="Matrix",
            billing_address="Kochi, Kerala",
        )
        self.assertEqual(user.email, "matrix@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        profile = CustomerProfile.objects.get(user=user)
        self.assertEqual(profile.company_name, "Matrix")
        self.assertEqual(profile.billing_address, "Kochi, Kerala")

    def test_profile_failure_rolls_back_user_creation(self):
        with patch(
            "accounts.services.CustomerProfile.objects.create",
            side_effect=RuntimeError("simulated profile insert failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_customer_account(
                    email="atomic@example.com",
                    password=VALID_PASSWORD,
                    full_name="Atomic User",
                )
        self.assertFalse(User.objects.filter(email="atomic@example.com").exists())


class RegistrationPageTests(TestCase):
    def test_registration_creates_customer_and_profile(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Matrix User",
                "email": "MATRIX@example.com",
                "phone": "9876543210",
                "company_name": "Matrix",
                "billing_address": "Kochi, Kerala",
                "password": VALID_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(email="matrix@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.customer_profile.company_name, "Matrix")

    def test_duplicate_registration_is_rejected(self):
        User.objects.create_user(
            email="taken@example.com", password=VALID_PASSWORD, full_name="Existing"
        )
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Duplicate User",
                "email": "TAKEN@example.com",
                "password": VALID_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email="taken@example.com").count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Weak User",
                "email": "weak@example.com",
                "password": "weakpassword123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())


class RegistrationAPITests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_public_api_registration_always_creates_customer(self):
        response = self.api.post(
            reverse("api-register"),
            {
                "full_name": "API Customer",
                "email": "API@example.com",
                "password": VALID_PASSWORD,
                "company_name": "API Matrix",
                "role": "ADMIN",
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="api@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.customer_profile.company_name, "API Matrix")

    def test_duplicate_api_registration_is_rejected(self):
        User.objects.create_user(
            email="taken@example.com", password=VALID_PASSWORD, full_name="Existing"
        )
        response = self.api.post(
            reverse("api-register"),
            {
                "full_name": "Duplicate User",
                "email": "taken@example.com",
                "password": VALID_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_weak_password_api_registration_returns_validation_error(self):
        response = self.api.post(
            reverse("api-register"),
            {
                "full_name": "Weak API User",
                "email": "weak-api@example.com",
                "password": "weakpassword123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(User.objects.filter(email="weak-api@example.com").exists())


class ProfileAPITests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password=VALID_PASSWORD,
            full_name="Customer User",
            role=User.Role.CUSTOMER,
        )
        self.profile = CustomerProfile.objects.create(
            user=self.customer, company_name="Old Company"
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.customer)

    def test_customer_can_read_own_profile(self):
        response = self.api.get(reverse("api-my-profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "customer@example.com")
        self.assertEqual(response.data["customer_profile"]["company_name"], "Old Company")

    def test_customer_can_update_own_profile(self):
        response = self.api.patch(
            reverse("api-my-profile"),
            {"full_name": "Updated Name", "company_name": "Matrix"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.customer.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.customer.full_name, "Updated Name")
        self.assertEqual(self.profile.company_name, "Matrix")

    def test_profile_api_creates_a_missing_customer_profile(self):
        self.profile.delete()
        response = self.api.patch(
            reverse("api-my-profile"),
            {"company_name": "Created On First Edit"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            CustomerProfile.objects.get(user=self.customer).company_name,
            "Created On First Edit",
        )

    def test_profile_api_does_not_allow_role_or_email_changes(self):
        response = self.api.patch(
            reverse("api-my-profile"),
            {"role": "ADMIN", "email": "attacker@example.com", "is_staff": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.role, User.Role.CUSTOMER)
        self.assertEqual(self.customer.email, "customer@example.com")
        self.assertFalse(self.customer.is_staff)

    def test_profile_page_edits_only_signed_in_users_profile(self):
        response = self.client.get(reverse("accounts-profile"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("accounts-profile"),
            {
                "full_name": "Web Updated",
                "phone": "9999999999",
                "company_name": "Matrix Web",
                "billing_address": "Kochi",
                "tax_identifier": "GSTIN-EXAMPLE",
            },
        )
        self.assertRedirects(response, reverse("accounts-profile"))
        self.customer.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.customer.full_name, "Web Updated")
        self.assertEqual(self.profile.company_name, "Matrix Web")
        self.assertEqual(self.profile.tax_identifier, "GSTIN-EXAMPLE")


class StaffPermissionTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com", password=VALID_PASSWORD, full_name="Customer"
        )
        self.admin_role_user = User.objects.create_user(
            email="business-admin@example.com",
            password=VALID_PASSWORD,
            full_name="Business Admin",
            role=User.Role.ADMIN,
        )
        self.api = APIClient()

    def test_customer_cannot_create_staff(self):
        self.api.force_authenticate(user=self.customer)
        response = self.api.post(
            reverse("api-staff-create"),
            {
                "full_name": "New Staff",
                "email": "staff@example.com",
                "password": VALID_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="staff@example.com").exists())

    def test_business_admin_can_create_staff_without_admin_site_access(self):
        self.api.force_authenticate(user=self.admin_role_user)
        response = self.api.post(
            reverse("api-staff-create"),
            {
                "full_name": "New Staff",
                "email": "staff@example.com",
                "password": VALID_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        staff = User.objects.get(email="staff@example.com")
        self.assertEqual(staff.role, User.Role.STAFF)
        self.assertFalse(staff.is_staff)
