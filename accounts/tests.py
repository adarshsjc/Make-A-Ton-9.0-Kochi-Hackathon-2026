from django.test import TestCase
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User

class UserModelTests(TestCase):
    def test_email_is_case_normalized(self):
        user = User.objects.create_user(email="Example@Mail.com", password="StrongPass!9", full_name="Example")
        self.assertEqual(user.email, "example@mail.com")
    def test_customer_role_is_default(self):
        user = User.objects.create_user(email="a@example.com", password="StrongPass!9", full_name="A")
        self.assertEqual(user.role, User.Role.CUSTOMER)
    def test_password_requires_special_character(self):
        with self.assertRaises(ValidationError):
            validate_password("StrongPassword9")
