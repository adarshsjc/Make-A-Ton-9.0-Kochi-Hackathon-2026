from django.urls import path
from .views import RegisterAPIView, LoginAPIView, LogoutAPIView, MeAPIView, StaffCreateAPIView, CustomerProfileViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("customers", CustomerProfileViewSet)

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="api-register"),
    path("auth/login/", LoginAPIView.as_view(), name="api-login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api-logout"),
    path("auth/me/", MeAPIView.as_view(), name="api-me"),
    path("staff/", StaffCreateAPIView.as_view(), name="api-staff-create"),
] + router.urls
