from rest_framework.routers import DefaultRouter
from .views import QuotationTemplateViewSet, QuotationViewSet, SubscriptionViewSet, MySubscriptionsAPIView
from django.urls import path
router = DefaultRouter()
router.register("quotation-templates", QuotationTemplateViewSet)
router.register("quotations", QuotationViewSet)
router.register("subscriptions", SubscriptionViewSet)
urlpatterns = [path("me/subscriptions/", MySubscriptionsAPIView.as_view(), name="api-my-subscriptions")] + router.urls
