from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, ProductVariantViewSet, TaxViewSet, PlanViewSet
router = DefaultRouter()
router.register("products", ProductViewSet)
router.register("variants", ProductVariantViewSet)
router.register("taxes", TaxViewSet)
router.register("plans", PlanViewSet)
urlpatterns = router.urls
