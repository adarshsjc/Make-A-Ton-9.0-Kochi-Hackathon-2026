from datetime import date
from django.test import TestCase
from .models import Plan

class PlanTests(TestCase):
    def test_monthly_interval_choice_exists(self):
        self.assertIn(Plan.BillingInterval.MONTHLY, dict(Plan.BillingInterval.choices))
