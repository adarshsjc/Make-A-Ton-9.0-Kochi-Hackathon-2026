from datetime import date
from django.test import SimpleTestCase
from .services import advance_billing_date
from catalog.models import Plan

class BillingDateTests(SimpleTestCase):
    def test_month_end_clamps_to_last_day(self):
        self.assertEqual(advance_billing_date(date(2026, 1, 31), Plan.BillingInterval.MONTHLY), date(2026, 2, 28))
    def test_leap_day_yearly_clamps(self):
        self.assertEqual(advance_billing_date(date(2024, 2, 29), Plan.BillingInterval.YEARLY), date(2025, 2, 28))
