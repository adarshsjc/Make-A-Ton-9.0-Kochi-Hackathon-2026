from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from .services import dashboard_summary

class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if getattr(user, "role", None) == "CUSTOMER":
            from subscriptions.models import Subscription
            from billing.models import Invoice
            context["customer_subscriptions"] = Subscription.objects.filter(customer=user).select_related("plan").order_by("-created_at")[:8]
            context["customer_invoices"] = Invoice.objects.filter(customer=user).order_by("-issue_date")[:8]
            context["is_customer"] = True
        else:
            context.update(dashboard_summary())
            context["is_customer"] = False
        return context
