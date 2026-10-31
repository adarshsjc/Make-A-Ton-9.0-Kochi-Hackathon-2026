from django.urls import path
from .api_views import DashboardSummaryAPIView
urlpatterns = [path("dashboard/summary/", DashboardSummaryAPIView.as_view(), name="api-dashboard-summary")]
