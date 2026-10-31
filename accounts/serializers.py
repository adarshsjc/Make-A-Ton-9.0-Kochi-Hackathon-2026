"""Serializers for account registration, staff creation and self-service profile."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import CustomerProfile, User
from .services import create_customer_account, create_staff_account


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "phone", "is_active", "date_joined"]
        read_only_fields = ["id", "email", "role", "is_active", "date_joined"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    billing_address = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().casefold()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        candidate = User(
            email=str(self.initial_data.get("email", "")).strip().casefold(),
            full_name=str(self.initial_data.get("full_name", "")),
        )
        try:
            validate_password(value, user=candidate)
        except DjangoValidationError as exc:
            # Django's password validators raise DjangoValidationError, while
            # DRF expects its own ValidationError for a clean HTTP 400 response.
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def create(self, validated_data):
        try:
            return create_customer_account(**validated_data)
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc


class StaffCreateSerializer(RegisterSerializer):
    """Only IsAdminRole views may use this serializer; role is forced server-side."""

    def create(self, validated_data):
        validated_data.pop("company_name", None)
        validated_data.pop("billing_address", None)
        try:
            return create_staff_account(**validated_data)
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc


class CustomerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id", "user", "email", "full_name", "phone", "company_name",
            "billing_address", "tax_identifier", "created_at",
        ]
        read_only_fields = fields


class MyProfileSerializer(serializers.Serializer):
    """Self-service profile serializer; identity and role are never writable."""

    full_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=180, required=False, allow_blank=True)
    billing_address = serializers.CharField(required=False, allow_blank=True)
    tax_identifier = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate(self, attrs):
        customer_fields = {"company_name", "billing_address", "tax_identifier"}
        if self.instance.role != User.Role.CUSTOMER and customer_fields.intersection(attrs):
            raise serializers.ValidationError(
                "Company and billing profile fields are available only to customer accounts."
            )
        return attrs

    def update(self, instance, validated_data):
        user_fields = {"full_name", "phone"}
        profile_fields = {"company_name", "billing_address", "tax_identifier"}
        with transaction.atomic():
            user_updates = user_fields.intersection(validated_data)
            for field in user_updates:
                setattr(instance, field, validated_data[field])
            if user_updates:
                instance.save(update_fields=sorted(user_updates))

            profile_updates = profile_fields.intersection(validated_data)
            if profile_updates:
                profile, created = CustomerProfile.objects.get_or_create(user=instance)
                for field in profile_updates:
                    setattr(profile, field, validated_data[field])
                # get_or_create has already persisted a new profile row.
                if created:
                    profile.save()
                else:
                    profile.save(update_fields=sorted(profile_updates))
        return instance

    def to_representation(self, instance):
        result = UserSerializer(instance, context=self.context).data
        profile = CustomerProfile.objects.filter(user=instance).first()
        result["customer_profile"] = (
            CustomerProfileSerializer(profile, context=self.context).data if profile else None
        )
        return result
