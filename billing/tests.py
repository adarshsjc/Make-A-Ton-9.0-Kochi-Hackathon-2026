from decimal import Decimal
from django.test import SimpleTestCase
from .services import money

class MoneyTests(SimpleTestCase):
    def test_money_rounding(self):
        self.assertEqual(money(Decimal("1.005")), Decimal("1.01"))
