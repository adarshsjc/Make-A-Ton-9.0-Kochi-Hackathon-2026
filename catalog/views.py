from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
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
    search_fields = ["name", "notes", "description"]
    ordering_fields = ["name", "sale_price", "created_at"]

    @action(detail=True, methods=["get", "post"])
    def variants(self, request, pk=None):
        product = self.get_object()
        if request.method == "GET":
            variants = product.variants.all()
            serializer = ProductVariantSerializer(variants, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            data = request.data.copy()
            data["product"] = product.id
            serializer = ProductVariantSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

class ProductVariantViewSet(AdminManagedViewSet):
    queryset = ProductVariant.objects.select_related("product").all()
    serializer_class = ProductVariantSerializer
    filterset_fields = ["product", "is_active"]
    search_fields = ["value", "attribute_name", "name", "sku", "product__name"]

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
