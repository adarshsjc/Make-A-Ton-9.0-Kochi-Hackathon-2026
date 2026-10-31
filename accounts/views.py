"""HTML and API views for user accounts and customer profiles."""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import FormView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.permissions import IsAdminRole, IsStaffOrAdmin

from .forms import AccountDetailsForm, CustomerProfileForm, CustomerRegistrationForm
from .models import CustomerProfile, User
from .serializers import (
    CustomerProfileSerializer,
    MyProfileSerializer,
    RegisterSerializer,
    StaffCreateSerializer,
    UserSerializer,
)


@method_decorator(csrf_protect, name="dispatch")
class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "")
        password = request.data.get("password", "")
        if not isinstance(email, str) or not isinstance(password, str):
            return Response(
                {"detail": "Enter a valid email address and password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(
            request,
            username=email.strip().casefold(),
            password=password,
        )
        # Keep the response generic; do not reveal whether an email exists or
        # whether an account is inactive.
        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response({"user": UserSerializer(user).data})


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class MyProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MyProfileSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = MyProfileSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StaffCreateAPIView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class RegisterPageView(FormView):
    template_name = "accounts/register.html"
    form_class = CustomerRegistrationForm

    def form_valid(self, form):
        try:
            form.save()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    target = field if field in form.fields else None
                    for error in errors:
                        form.add_error(target, error)
            else:
                form.add_error(None, exc.messages)
            return self.form_invalid(form)
        messages.success(self.request, "Account created. You can now sign in.")
        return redirect("login")


class ProfileView(LoginRequiredMixin, View):
    """Let the signed-in user edit only their own account/profile fields."""

    template_name = "accounts/profile.html"

    def _profile_instance(self, user):
        if user.role != User.Role.CUSTOMER:
            return None
        return CustomerProfile.objects.filter(user=user).first()

    def _render(self, request, account_form, profile_form=None, status_code=200):
        return render(
            request,
            self.template_name,
            {
                "account_form": account_form,
                "profile_form": profile_form,
                "is_customer": request.user.role == User.Role.CUSTOMER,
            },
            status=status_code,
        )

    def get(self, request):
        profile = self._profile_instance(request.user)
        account_form = AccountDetailsForm(instance=request.user)
        profile_form = CustomerProfileForm(instance=profile) if request.user.role == User.Role.CUSTOMER else None
        return self._render(request, account_form, profile_form)

    def post(self, request):
        profile = self._profile_instance(request.user)
        account_form = AccountDetailsForm(request.POST, instance=request.user)
        profile_form = (
            CustomerProfileForm(request.POST, instance=profile)
            if request.user.role == User.Role.CUSTOMER
            else None
        )
        account_valid = account_form.is_valid()
        profile_valid = profile_form.is_valid() if profile_form is not None else True
        if not (account_valid and profile_valid):
            return self._render(request, account_form, profile_form)

        with transaction.atomic():
            account_form.save()
            if profile_form is not None:
                customer_profile = profile_form.save(commit=False)
                customer_profile.user = request.user
                customer_profile.save()

        messages.success(request, "Your profile has been updated.")
        return redirect("accounts-profile")


class CustomerProfileViewSet(ReadOnlyModelViewSet):
    queryset = CustomerProfile.objects.select_related("user").all()
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsStaffOrAdmin]
    search_fields = ["user__email", "user__full_name", "company_name", "tax_identifier"]
    ordering_fields = ["created_at", "company_name"]
