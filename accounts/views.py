from django.contrib.auth import authenticate, login, logout
from django.views.generic import FormView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from .serializers import RegisterSerializer, UserSerializer, StaffCreateSerializer, CustomerProfileSerializer
from .models import CustomerProfile
from common.permissions import IsStaffOrAdmin
from common.permissions import IsAdminRole

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = str(request.data.get("email", "")).strip().casefold()
        password = request.data.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is None:
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active:
            return Response({"detail": "This account is inactive."}, status=status.HTTP_403_FORBIDDEN)
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

class StaffCreateAPIView(APIView):
    permission_classes = [IsAdminRole]
    def post(self, request):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

class RegisterPageView(FormView):
    template_name = "accounts/register.html"
    from django import forms
    form_class = type("RegisterPageForm", (forms.Form,), {
        "full_name": forms.CharField(max_length=150),
        "email": forms.EmailField(),
        "password": forms.CharField(widget=forms.PasswordInput, min_length=9),
        "company_name": forms.CharField(max_length=180, required=False),
    })
    def form_valid(self, form):
        from django.contrib import messages
        from django.shortcuts import redirect
        from .models import User, CustomerProfile
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        email = form.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            form.add_error("email", "An account with this email already exists.")
            return self.form_invalid(form)
        try:
            candidate = User(email=email, full_name=form.cleaned_data["full_name"])
            validate_password(form.cleaned_data["password"], user=candidate)
        except ValidationError as exc:
            form.add_error("password", exc)
            return self.form_invalid(form)
        user = User.objects.create_user(
            email=email,
            password=form.cleaned_data["password"],
            full_name=form.cleaned_data["full_name"],
            role=User.Role.CUSTOMER,
        )
        CustomerProfile.objects.create(user=user, company_name=form.cleaned_data.get("company_name", ""))
        messages.success(self.request, "Account created. You can now sign in.")
        return redirect("login")


class CustomerProfileViewSet(ReadOnlyModelViewSet):
    queryset = CustomerProfile.objects.select_related("user").all()
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsStaffOrAdmin]
    search_fields = ["user__email", "user__full_name", "company_name", "tax_identifier"]
    ordering_fields = ["created_at", "company_name"]
