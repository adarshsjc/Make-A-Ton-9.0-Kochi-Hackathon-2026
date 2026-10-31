from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, ProductVariantViewSet, TaxViewSet, PlanViewSet
from .web_views import ProductListView, PlanListView

router = DefaultRouter()
router.register("products", ProductViewSet)
router.register("variants", ProductVariantViewSet)
router.register("taxes", TaxViewSet)
router.register("plans", PlanViewSet)

urlpatterns = [
    path("products/page/", ProductListView.as_view(), name="catalog-product-page"),
    path("plans/page/", PlanListView.as_view(), name="catalog-plan-page"),
] + router.urls
