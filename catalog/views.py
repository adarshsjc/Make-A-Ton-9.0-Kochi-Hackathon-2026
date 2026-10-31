from rest_framework.viewsets import ModelViewSet
from common.permissions import ReadOnlyOrAdmin
from .models import Product, ProductVariant, Tax, Plan
from .serializers import ProductSerializer, ProductVariantSerializer, TaxSerializer, PlanSerializer

class AdminManagedViewSet(ModelViewSet):
    permission_classes = [ReadOnlyOrAdmin]

class ProductViewSet(AdminManagedViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ["product_type", "is_active"]
    search_fields = ["name", "notes"]
    ordering_fields = ["name", "sale_price", "created_at"]

class ProductVariantViewSet(AdminManagedViewSet):
    queryset = ProductVariant.objects.select_related("product").all()
    serializer_class = ProductVariantSerializer
    filterset_fields = ["product", "is_active"]
    search_fields = ["value", "attribute_name", "product__name"]

class TaxViewSet(AdminManagedViewSet):
    queryset = Tax.objects.all()
    serializer_class = TaxSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name"]

class PlanViewSet(AdminManagedViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    filterset_fields = ["billing_interval", "is_active"]
    search_fields = ["name", "description"]
