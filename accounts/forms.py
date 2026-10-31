"""Forms for account administration, customer registration and profile editing."""

from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import CustomerProfile, User
from .services import create_customer_account


class BrightloopUserCreationForm(forms.ModelForm):
    """Django Admin add-user form; passwords are hashed before persistence."""

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("email", "full_name", "role")

    def clean_email(self):
        return self.cleaned_data["email"].strip().casefold()

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if not password1 or not password2:
            return password2
        if password1 != password2:
            raise ValidationError("The two password fields did not match.")
        candidate = User(
            email=self.cleaned_data.get("email", ""),
            full_name=self.cleaned_data.get("full_name", ""),
        )
        validate_password(password2, user=candidate)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class BrightloopUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = "__all__"


class CustomerRegistrationForm(forms.Form):
    """Public signup form. It intentionally has no role or permission fields."""

    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(max_length=30, required=False, label="Phone number")
    company_name = forms.CharField(max_length=180, required=False, label="Company name")
    billing_address = forms.CharField(
        required=False,
        label="Billing address",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    password = forms.CharField(
        min_length=9,
        strip=False,
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        candidate = User(
            email=self.data.get("email", "").strip().casefold(),
            full_name=self.data.get("full_name", "").strip(),
        )
        validate_password(password, user=candidate)
        return password

    def save(self):
        if not self.is_valid():
            raise ValueError("CustomerRegistrationForm.save() requires a valid form.")
        data = self.cleaned_data
        return create_customer_account(
            email=data["email"],
            password=data["password"],
            full_name=data["full_name"],
            phone=data.get("phone", ""),
            company_name=data.get("company_name", ""),
            billing_address=data.get("billing_address", ""),
        )


class AccountDetailsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "phone")
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = ("company_name", "billing_address", "tax_identifier")
        widgets = {
            "company_name": forms.TextInput(attrs={"autocomplete": "organization"}),
            "billing_address": forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"}),
            "tax_identifier": forms.TextInput(attrs={"autocomplete": "off"}),
        }
