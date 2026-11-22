import unittest

from flightback.extract import suggest

MSG = """Dear Passenger, we regret to inform you that your flight 6E 000 from Delhi to Jaipur,
scheduled to depart on 20 Nov 2026 17:00, has been cancelled due to adverse weather.
This message was sent on 20/11/2026 14:05. Basic fare Rs 3,200, fuel charge INR 450, total Rs 5,000."""


def by_field(res, field):
    return [c for c in res["candidates"] if c["suggested_field"] == field]


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.r = suggest(MSG)

    def test_scheduled_departure_found_with_its_quote(self):
        c = by_field(self.r, "scheduled_departure")[0]
        self.assertEqual(c["value"], "2026-11-20T17:00")
        self.assertIn("20 Nov 2026 17:00", c["snippet"])

    def test_day_first_numeric_date_is_read_as_india_format(self):
        vals = [c["value"] for c in self.r["candidates"] if c["type"] == "datetime"]
        self.assertIn("2026-11-20T14:05", vals)  # 20/11/2026, not month 20

    def test_amounts_are_labelled(self):
        self.assertEqual(by_field(self.r, "basic_fare")[0]["value"], 3200.0)
        self.assertEqual(by_field(self.r, "fuel_charge")[0]["value"], 450.0)
        self.assertEqual(by_field(self.r, "total_paid")[0]["value"], 5000.0)

    def test_named_extraordinary_cause_is_flagged_with_caution(self):
        c = by_field(self.r, "extraordinary_claimed")[0]
        self.assertTrue(c["value"])
        self.assertIn("refund", c["note"])

    def test_operational_cause_is_not_called_extraordinary(self):
        r = suggest("Your flight is cancelled due to operational reasons.")
        self.assertFalse(by_field(r, "extraordinary_claimed")[0]["value"])

    def test_cancellation_is_noted(self):
        self.assertTrue(any("cancelled by the airline" in n for n in self.r["notes"]))

    def test_invalid_dates_are_dropped_not_guessed(self):
        r = suggest("Departure 31 Foo 2026 10:00 and 45/13/2026 10:00")
        self.assertEqual([c for c in r["candidates"] if c["type"] == "datetime"], [])

    def test_empty_text_says_so(self):
        r = suggest("hello")
        self.assertEqual(r["candidates"], [])
        self.assertTrue(r["notes"])


if __name__ == "__main__":
    unittest.main()
