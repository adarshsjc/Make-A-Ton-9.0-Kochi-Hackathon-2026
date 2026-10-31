from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, CustomerProfile

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "phone", "is_active", "date_joined"]
        read_only_fields = ["id", "role", "is_active", "date_joined"]

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
            email=str(self.initial_data.get("email", "")),
            full_name=str(self.initial_data.get("full_name", "")),
        )
        validate_password(value, user=candidate)
        return value

    def create(self, validated_data):
        profile_data = {
            "company_name": validated_data.pop("company_name", ""),
            "billing_address": validated_data.pop("billing_address", ""),
        }
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, role=User.Role.CUSTOMER, **validated_data)
        CustomerProfile.objects.create(user=user, **profile_data)
        return user

class StaffCreateSerializer(RegisterSerializer):
    """Only IsAdminRole views may use this serializer; role is forced server-side."""
    def create(self, validated_data):
        validated_data.pop("company_name", None)
        validated_data.pop("billing_address", None)
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, role=User.Role.STAFF, **validated_data)


class CustomerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    class Meta:
        model = CustomerProfile
        fields = ["id", "user", "email", "full_name", "phone", "company_name", "billing_address", "tax_identifier", "created_at"]
        read_only_fields = fields
