from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from accounts.views import RegisterPageView
from .api_views import APIIndexView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/register/", RegisterPageView.as_view(), name="register"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password-reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.html",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url="/accounts/password-reset/done/",
    ), name="password_reset"),
    path("accounts/password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"), name="password_reset_confirm"),
    path("accounts/reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
    path("api/v1/", APIIndexView.as_view(), name="api-root"),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("subscriptions.urls")),
    path("api/v1/", include("billing.urls")),
    path("api/v1/", include("dashboard.api_urls")),
]
