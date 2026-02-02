import unittest

from server.miscite.routes import billing


class TestBillingFormatting(unittest.TestCase):
    def test_parse_amount_to_cents_valid(self):
        cents, error = billing._parse_amount_to_cents("12.34")
        self.assertEqual(cents, 1234)
        self.assertIsNone(error)

    def test_parse_amount_to_cents_rounding(self):
        cents, error = billing._parse_amount_to_cents("1.005")
        self.assertEqual(cents, 101)
        self.assertIsNone(error)

    def test_parse_amount_to_cents_invalid(self):
        cents, error = billing._parse_amount_to_cents("")
        self.assertIsNone(cents)
        self.assertEqual(error, "Enter a top-up amount.")

        cents, error = billing._parse_amount_to_cents("abc")
        self.assertIsNone(cents)
        self.assertEqual(error, "Enter a valid amount.")

        cents, error = billing._parse_amount_to_cents("-1")
        self.assertIsNone(cents)
        self.assertEqual(error, "Amount must be greater than zero.")

    def test_format_currency(self):
        self.assertEqual(billing._format_currency(1234), "$12.34")
        self.assertEqual(billing._format_currency(-11), "-$0.11")

    def test_format_amount(self):
        self.assertEqual(billing._format_amount(500), "+$5.00")
        self.assertEqual(billing._format_amount(-500), "-$5.00")


if __name__ == "__main__":
    unittest.main()
