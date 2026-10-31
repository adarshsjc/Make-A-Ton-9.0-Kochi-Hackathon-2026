from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class APIIndexView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        routes = {
            "current_user": "auth/me/",
            "customers": "customers/",
            "products": "products/",
            "variants": "variants/",
            "taxes": "taxes/",
            "plans": "plans/",
            "quotation_templates": "quotation-templates/",
            "quotations": "quotations/",
            "subscriptions": "subscriptions/",
            "my_subscriptions": "me/subscriptions/",
            "invoices": "invoices/",
            "my_invoices": "me/invoices/",
            "discount_rules": "discount-rules/",
            "run_billing": "billing/run/",
            "dashboard_summary": "dashboard/summary/",
        }
        return Response({name: request.build_absolute_uri(path) for name, path in routes.items()})
