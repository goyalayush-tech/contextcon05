import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from flightback.rules import (PART_II, PART_IV, CancellationFacts, DelayFacts, RefundFacts, Status,
                              add_working_days, assess_cancellation, assess_delay, assess_refund,
                              compensation_cap, in_night_window, meal_threshold)

IST = timezone(timedelta(hours=5, minutes=30))
S = Status


def t(y=2026, mo=11, d=20, h=10, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=IST)


def canc(**kw):
    base = dict(scheduled_departure=t(h=17), informed_at=t(h=14), block_time_hours=1.5, basic_fare=3000,
                fuel_charge=500, contact_info_provided=True, extraordinary_claimed=False,
                same_ticket_connection_missed=False)
    base.update(kw)
    return assess_cancellation(CancellationFacts(**base))


class RulePackTests(unittest.TestCase):
    def test_verification_flags_are_honest(self):
        self.assertTrue(PART_IV.verified)
        self.assertFalse(PART_II.verified)
        self.assertEqual((PART_IV.revision, PART_IV.effective), ("Rev. 4", "2023-02-15"))


class CancellationTests(unittest.TestCase):
    def test_waiting_facilities_need_both_an_accepted_alternate_and_reporting_at_the_airport(self):
        st = lambda **kw: canc(**kw).get("waiting_facilities")
        self.assertEqual(st(alternate_accepted=True, reported_at_airport=True).status, Status.SUPPORTED)
        self.assertEqual(st(alternate_accepted=True, reported_at_airport=False).status, Status.NOT_APPLICABLE)
        self.assertEqual(st(alternate_accepted=False, reported_at_airport=True).status, Status.NOT_APPLICABLE)
        alone = st(alternate_accepted=True)  # accepting an alternate alone no longer implies an airport wait
        self.assertEqual(alone.status, Status.UNKNOWN)
        self.assertEqual(alone.missing, ["whether the passenger had already reported at the airport"])
        self.assertEqual(len(st().missing), 2)

    def test_caps_by_block_time_boundaries(self):
        self.assertEqual(compensation_cap(1), 5000)
        self.assertEqual(compensation_cap("1.01"), 7500)
        self.assertEqual(compensation_cap(2), 7500)
        self.assertEqual(compensation_cap("2.01"), 10000)

    def test_compensation_uses_basic_plus_fuel_not_total_ticket(self):
        a = canc(basic_fare=3000, fuel_charge=500, block_time_hours=1.5)  # cap 7500, base 3500
        self.assertEqual(a.get("compensation").status, S.SUPPORTED)
        self.assertEqual(a.amounts["payable_compensation"], Decimal(3500))
        self.assertIn("min(7500, 3000 + 500) = 3500", a.amounts["formula"])

    def test_cap_binds_when_fare_is_large(self):
        a = canc(basic_fare=9000, fuel_charge=2000, block_time_hours=0.8)
        self.assertEqual(a.amounts["payable_compensation"], Decimal(5000))

    def test_two_weeks_notice_means_no_compensation(self):
        a = canc(informed_at=t(h=17) - timedelta(days=14))  # exactly two weeks counts
        self.assertEqual(a.get("informed_per_331").status, S.SUPPORTED)
        self.assertEqual(a.get("compensation").status, S.NOT_SUPPORTED)

    def test_under_24_hours_notice_triggers_compensation(self):
        a = canc(informed_at=t(h=17) - timedelta(hours=23, minutes=59))
        self.assertEqual(a.get("informed_per_331").status, S.NOT_SUPPORTED)
        self.assertEqual(a.get("compensation").status, S.SUPPORTED)

    def test_exactly_24_hours_needs_the_offer_fact(self):
        unknown = canc(informed_at=t(h=17) - timedelta(hours=24), alt_or_refund_offered=None)
        self.assertEqual(unknown.get("informed_per_331").status, S.UNKNOWN)
        self.assertEqual(unknown.get("compensation").status, S.UNKNOWN)
        self.assertIn("whether the airline offered an alternate flight or refund", unknown.missing)
        no_offer = canc(informed_at=t(h=17) - timedelta(hours=24), alt_or_refund_offered=False)
        self.assertEqual(no_offer.get("compensation").status, S.SUPPORTED)
        offered = canc(informed_at=t(h=17) - timedelta(hours=24), alt_or_refund_offered=True)
        self.assertEqual(offered.get("compensation").status, S.NOT_SUPPORTED)

    def test_missed_same_ticket_connection_triggers_even_with_long_notice(self):
        a = canc(informed_at=t(h=17) - timedelta(days=20), same_ticket_connection_missed=True)
        self.assertEqual(a.get("compensation_trigger").status, S.SUPPORTED)
        self.assertEqual(a.get("compensation").status, S.SUPPORTED)

    def test_no_contact_info_blocks_compensation_but_not_refund(self):
        a = canc(informed_at=t(h=16), contact_info_provided=False)
        self.assertEqual(a.get("compensation").status, S.NOT_SUPPORTED)
        self.assertEqual(a.get("alt_or_refund_obligation").status, S.SUPPORTED)

    def test_extraordinary_circumstances_is_review_and_keeps_refund_duty(self):
        a = canc(informed_at=t(h=16), extraordinary_claimed=True)
        self.assertEqual(a.get("compensation").status, S.REVIEW_REQUIRED)
        self.assertEqual(a.get("alt_or_refund_obligation").status, S.SUPPORTED)

    def test_accepting_an_alternate_flight_removes_compensation(self):
        a = canc(informed_at=t(h=16), alternate_accepted=True)
        self.assertEqual(a.get("compensation").status, S.NOT_APPLICABLE)

    def test_missing_inputs_are_named_not_assumed(self):
        a = canc(informed_at=t(h=16), basic_fare=None, block_time_hours=None)
        self.assertEqual(a.get("compensation").status, S.UNKNOWN)
        self.assertIn("booked one-way basic fare", a.missing)
        self.assertIn("flight block time", a.missing)
        self.assertIsNone(a.amounts["payable_compensation"])

    def test_international_is_out_of_scope(self):
        a = canc(domestic=False)
        self.assertEqual(a.conditions[0].status, S.NOT_APPLICABLE)


def dly(**kw):
    base = dict(scheduled_departure=t(h=10), expected_departure=t(h=10) + timedelta(hours=3), block_time_hours=2,
                checked_in_on_time=True, extraordinary_claimed=False)
    base.update(kw)
    return assess_delay(DelayFacts(**base))


class DelayTests(unittest.TestCase):
    def test_meal_thresholds(self):
        self.assertEqual(meal_threshold("2.5"), timedelta(hours=2))
        self.assertEqual(meal_threshold("2.51"), timedelta(hours=3))
        self.assertEqual(meal_threshold(5), timedelta(hours=3))
        self.assertEqual(meal_threshold("5.01"), timedelta(hours=4))

    def test_meals_at_and_below_threshold(self):
        at = dly(block_time_hours=2, expected_departure=t(h=10) + timedelta(hours=2))
        self.assertEqual(at.get("meals_obligation").status, S.SUPPORTED)
        below = dly(block_time_hours=2, expected_departure=t(h=10) + timedelta(hours=1, minutes=59))
        self.assertEqual(below.get("meals_obligation").status, S.NOT_SUPPORTED)

    def test_meals_need_timely_check_in(self):
        self.assertEqual(dly(checked_in_on_time=False).get("meals_obligation").status, S.NOT_SUPPORTED)
        unk = dly(checked_in_on_time=None)
        self.assertEqual(unk.get("meals_obligation").status, S.UNKNOWN)
        self.assertIn("proof of timely check-in", unk.missing)

    def test_exactly_six_hours_is_not_more_than_six(self):
        six = dly(expected_departure=t(h=10) + timedelta(hours=6))
        self.assertEqual(six.get("alt_or_refund_obligation").status, S.NOT_SUPPORTED)
        over = dly(expected_departure=t(h=10) + timedelta(hours=6, minutes=1))
        self.assertEqual(over.get("alt_or_refund_obligation").status, S.SUPPORTED)

    def test_baseline_is_a_revision_only_if_told_more_than_24h_before(self):
        sched = t(h=10)
        early = dly(scheduled_departure=sched, previous_revised_departure=t(h=14),
                    previous_revision_informed_at=sched - timedelta(hours=30),
                    expected_departure=t(h=20, mi=30))
        c = early.get("alt_or_refund_obligation")
        self.assertEqual(c.status, S.SUPPORTED)  # 6.5h after the revised 14:00
        self.assertIn("previously revised", c.inputs["baseline"])
        late = dly(scheduled_departure=sched, previous_revised_departure=t(h=14),
                   previous_revision_informed_at=sched - timedelta(hours=10),
                   expected_departure=t(h=17))
        c2 = late.get("alt_or_refund_obligation")
        self.assertEqual(c2.inputs["baseline"], "published scheduled departure")
        self.assertEqual(c2.status, S.SUPPORTED)  # 7h from the original

    def test_night_window_boundaries(self):
        self.assertTrue(in_night_window(t(h=20)))
        self.assertFalse(in_night_window(t(h=19, mi=59)))
        self.assertTrue(in_night_window(t(h=3)))
        self.assertFalse(in_night_window(t(h=3, mi=1)))
        self.assertTrue(in_night_window(t(h=1)))

    def test_hotel_rules(self):
        night = dly(scheduled_departure=t(h=22), expected_departure=t(h=22) + timedelta(hours=6, minutes=1),
                    accommodation_needed=True)
        self.assertEqual(night.get("hotel_obligation").status, S.SUPPORTED)
        night6 = dly(scheduled_departure=t(h=22), expected_departure=t(h=22) + timedelta(hours=6))
        self.assertEqual(night6.get("hotel_obligation").status, S.NOT_SUPPORTED)
        day7 = dly(expected_departure=t(h=10) + timedelta(hours=7))
        self.assertEqual(day7.get("hotel_obligation").status, S.NOT_SUPPORTED)
        day24 = dly(expected_departure=t(h=10) + timedelta(hours=24, minutes=1))
        self.assertEqual(day24.get("hotel_obligation").status, S.REVIEW_REQUIRED)  # necessity unknown
        self.assertIn("whether hotel accommodation was needed", day24.missing)

    def test_extraordinary_circumstances_do_not_erase_alt_or_refund(self):
        a = dly(expected_departure=t(h=10) + timedelta(hours=8), extraordinary_claimed=True)
        self.assertEqual(a.get("meals_obligation").status, S.REVIEW_REQUIRED)
        self.assertEqual(a.get("alt_or_refund_obligation").status, S.SUPPORTED)

    def test_no_cash_compensation_for_delay(self):
        a = dly(expected_departure=t(h=10) + timedelta(hours=30))
        self.assertEqual(a.get("cash_compensation").status, S.NOT_SUPPORTED)

    def test_burden_of_proof_note_present(self):
        self.assertTrue(any("burden of proof" in n for n in dly().notes))

    def test_missing_times_give_unknown_everywhere(self):
        a = assess_delay(DelayFacts())
        self.assertEqual(a.get("meals_obligation").status, S.UNKNOWN)
        self.assertEqual(a.get("hotel_obligation").status, S.UNKNOWN)


class RefundTests(unittest.TestCase):
    def test_working_days(self):
        self.assertEqual(add_working_days(date(2026, 11, 20), 1), date(2026, 11, 23))  # Fri -> Mon
        self.assertEqual(add_working_days(date(2026, 3, 30), 14), date(2026, 4, 17))

    def r(self, **kw):
        base = dict(initiated_by="airline", payment_mode="credit_card", cancelled_at=t(mo=11, d=1),
                    as_of=date(2026, 11, 20), total_paid=5000, basic_fare=3000, fuel_charge=500,
                    statutory_fees=1500, cancellation_charge_levied=0, refund_received_amount=None,
                    refund_given_as_credit_shell=False)
        base.update(kw)
        return assess_refund(RefundFacts(**base))

    def test_credit_card_seven_days(self):
        late = self.r(refund_received_on=date(2026, 11, 9))
        self.assertEqual(late.get("refund_timeline_breach").status, S.SUPPORTED)
        ontime = self.r(refund_received_on=date(2026, 11, 8))
        self.assertEqual(ontime.get("refund_timeline_breach").status, S.NOT_SUPPORTED)

    def test_not_yet_due_is_not_a_breach(self):
        a = self.r(as_of=date(2026, 11, 5))
        self.assertEqual(a.get("refund_timeline_breach").status, S.NOT_SUPPORTED)

    def test_overdue_with_nothing_received(self):
        self.assertEqual(self.r().get("refund_timeline_breach").status, S.SUPPORTED)

    def test_agent_refund_uses_working_days(self):
        a = self.r(payment_mode="agent_portal", cancelled_at=t(mo=11, d=2), as_of=date(2026, 11, 20))  # Mon
        self.assertIn("2026-11-20", a.get("refund_timeline_breach").inputs["due_on"])  # +14 working days = Fri 20th

    def test_agent_refund_between_14_and_21_working_days_goes_to_review(self):
        base = dict(payment_mode="agent_portal", cancelled_at=t(mo=11, d=2))  # 14wd = Nov 20, 21wd = Dec 1
        mid = self.r(refund_received_on=date(2026, 11, 25), **base)
        self.assertEqual(mid.get("refund_timeline_breach").status, S.REVIEW_REQUIRED)
        late = self.r(as_of=date(2026, 12, 5), **base)
        self.assertEqual(late.get("refund_timeline_breach").status, S.SUPPORTED)
        ok = self.r(refund_received_on=date(2026, 11, 20), **base)
        self.assertEqual(ok.get("refund_timeline_breach").status, S.NOT_SUPPORTED)

    def test_statutory_fees_refund_even_if_fare_non_refundable(self):
        a = self.r(refund_received_amount=1000)
        self.assertEqual(a.get("statutory_fees_breach").status, S.SUPPORTED)
        ok = self.r(refund_received_amount=1500, initiated_by="passenger", cancellation_charge_levied=3500)
        self.assertEqual(ok.get("statutory_fees_breach").status, S.NOT_SUPPORTED)

    def test_airline_cancellation_shortfall(self):
        a = self.r(refund_received_amount=4200)
        self.assertEqual(a.amounts["expected_refund"], Decimal(5000))
        self.assertEqual(a.amounts["shortfall"], Decimal(800))

    def test_airline_cancellation_charge_is_a_breach(self):
        self.assertEqual(self.r(cancellation_charge_levied=500).get("cancellation_charge_breach").status, S.SUPPORTED)

    def test_passenger_charge_cap(self):
        over = self.r(initiated_by="passenger", cancellation_charge_levied=3600)
        self.assertEqual(over.get("cancellation_charge_breach").status, S.SUPPORTED)
        at = self.r(initiated_by="passenger", cancellation_charge_levied=3500)
        self.assertEqual(at.get("cancellation_charge_breach").status, S.NOT_SUPPORTED)
        agent = self.r(initiated_by="passenger", cancellation_charge_levied=3600, payment_mode="agent_portal")
        self.assertEqual(agent.get("cancellation_charge_breach").status, S.REVIEW_REQUIRED)

    def test_credit_shell_must_be_the_passengers_choice(self):
        forced = self.r(refund_given_as_credit_shell=True, credit_shell_accepted_voluntarily=False)
        self.assertEqual(forced.get("credit_shell_breach").status, S.SUPPORTED)
        chosen = self.r(refund_given_as_credit_shell=True, credit_shell_accepted_voluntarily=True)
        self.assertEqual(chosen.get("credit_shell_breach").status, S.NOT_SUPPORTED)
        unknown = self.r(refund_given_as_credit_shell=True, credit_shell_accepted_voluntarily=None)
        self.assertEqual(unknown.get("credit_shell_breach").status, S.UNKNOWN)
        self.assertIsNone(forced.amounts["shortfall"])  # no cash shortfall claimed when shell used

    def test_look_in(self):
        booked = t(mo=11, d=1, h=9)
        kw = dict(initiated_by="passenger", booked_via_airline_website=True, booked_at=booked,
                  flight_departure=booked + timedelta(days=8), cancellation_charge_levied=2000)
        yes = self.r(cancelled_at=booked + timedelta(hours=47), **kw)
        self.assertEqual(yes.get("look_in_eligible").status, S.SUPPORTED)
        late = self.r(cancelled_at=booked + timedelta(hours=49), **kw)
        self.assertEqual(late.get("look_in_eligible").status, S.NOT_SUPPORTED)
        near = dict(kw, flight_departure=booked + timedelta(days=6))
        self.assertEqual(self.r(cancelled_at=booked + timedelta(hours=10), **near).get("look_in_eligible").status,
                         S.NOT_SUPPORTED)
        third = dict(kw, booked_via_airline_website=False)
        self.assertEqual(self.r(cancelled_at=booked + timedelta(hours=10), **third).get("look_in_eligible").status,
                         S.NOT_APPLICABLE)

    def test_refund_assessment_carries_unverified_pack_warning(self):
        a = self.r()
        self.assertFalse(a.pack.verified)
        self.assertTrue(any("UNVERIFIED" in n for n in a.notes))


if __name__ == "__main__":
    unittest.main()
