from datetime import date
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from common.permissions import IsStaffOrAdmin
from .services import dashboard_summary

class DashboardSummaryAPIView(APIView):
    permission_classes = [IsStaffOrAdmin]
    def get(self, request):
        start_value = request.query_params.get("start_date")
        end_value = request.query_params.get("end_date")
        try:
            start_date = date.fromisoformat(start_value) if start_value else None
            end_date = date.fromisoformat(end_value) if end_value else None
        except ValueError:
            raise ValidationError({"date": "Use ISO dates in YYYY-MM-DD format."})
        if start_date and end_date and start_date > end_date:
            raise ValidationError({"date": "start_date cannot be later than end_date."})
        data = dashboard_summary(start_date=start_date, end_date=end_date)
        data.pop("recent_invoices", None)
        # DRF's JSON encoder serializes Decimal values safely as strings.
        return Response(data)
