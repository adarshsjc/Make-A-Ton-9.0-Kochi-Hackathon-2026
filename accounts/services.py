"""Transactional account creation helpers used by both HTML and API flows."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import CustomerProfile, User


DUPLICATE_EMAIL_MESSAGE = "An account with this email already exists."


def _normalise_email(email: str) -> str:
    if not isinstance(email, str) or not email.strip():
        raise ValidationError({"email": "An email address is required."})
    return User.objects.normalize_email(email.strip()).casefold()


def _validate_account_details(email: str, password: str, full_name: str) -> tuple[str, str]:
    normalized_email = _normalise_email(email)
    normalized_name = full_name.strip() if isinstance(full_name, str) else ""
    if not normalized_name:
        raise ValidationError({"full_name": "A full name is required."})
    candidate = User(email=normalized_email, full_name=normalized_name)
    validate_password(password, user=candidate)
    return normalized_email, normalized_name

def create_customer_account(
    *,
    email: str,
    password: str,
    full_name: str,
    phone: str = "",
    company_name: str = "",
    billing_address: str = "",
) -> User:
    """Create a CUSTOMER user and its profile as one database operation.

    The role is deliberately not an argument. Public registration must never
    allow the caller to choose ADMIN or STAFF.
    """
    normalized_email, normalized_name = _validate_account_details(email, password, full_name)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=normalized_email,
                password=password,
                full_name=normalized_name,
                phone=phone.strip(),
                role=User.Role.CUSTOMER,
                is_staff=False,
                is_superuser=False,
            )
            CustomerProfile.objects.create(
                user=user,
                company_name=company_name.strip(),
                billing_address=billing_address.strip(),
            )
            return user
    except IntegrityError as exc:
        # The form/serializer checks for duplicates first, but the database
        # unique constraint is the final authority during concurrent signup.
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise ValidationError({"email": DUPLICATE_EMAIL_MESSAGE}) from exc
        raise


def create_staff_account(
    *, email: str, password: str, full_name: str, phone: str = ""
) -> User:
    """Create a STAFF account. Call only from an admin-authorised endpoint."""
    normalized_email, normalized_name = _validate_account_details(email, password, full_name)
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=normalized_email,
                password=password,
                full_name=normalized_name,
                phone=phone.strip(),
                role=User.Role.STAFF,
                is_staff=False,
                is_superuser=False,
            )
    except IntegrityError as exc:
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise ValidationError({"email": DUPLICATE_EMAIL_MESSAGE}) from exc
        raise
