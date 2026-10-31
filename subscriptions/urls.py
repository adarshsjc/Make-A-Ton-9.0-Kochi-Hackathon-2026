from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    QuotationTemplateViewSet,
    QuotationViewSet,
    SubscriptionViewSet,
    MySubscriptionsAPIView,
)
from .web_views import (
    SubscriptionListView,
    SubscriptionDetailView,
    QuotationCreateView,
)

router = DefaultRouter()
router.register("quotation-templates", QuotationTemplateViewSet)
router.register("quotations", QuotationViewSet)
router.register("subscriptions", SubscriptionViewSet)

urlpatterns = [
    path("me/subscriptions/", MySubscriptionsAPIView.as_view(), name="api-my-subscriptions"),
    path("subscriptions/page/", SubscriptionListView.as_view(), name="subscription-list-page"),
    path("subscriptions/<int:pk>/page/", SubscriptionDetailView.as_view(), name="subscription-detail-page"),
    path("quotations/new/", QuotationCreateView.as_view(), name="quotation-create-page"),
] + router.urls
