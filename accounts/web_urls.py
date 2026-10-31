"""HTML account routes mounted under /accounts/ in config/urls.py."""

from django.urls import path

from .views import ProfileView

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="accounts-profile"),
]
