from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    MyProfileAPIView,
    RegisterAPIView,
    StaffCreateAPIView,
    CustomerProfileViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerProfileViewSet)

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="api-register"),
    path("auth/login/", LoginAPIView.as_view(), name="api-login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api-logout"),
    path("auth/me/", MeAPIView.as_view(), name="api-me"),
    path("auth/profile/", MyProfileAPIView.as_view(), name="api-my-profile"),
    path("staff/", StaffCreateAPIView.as_view(), name="api-staff-create"),
] + router.urls
