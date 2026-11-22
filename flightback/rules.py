"""Deterministic passenger-rights engine for Indian domestic flights.

No LLM and no network in here. Every condition returns one of five statuses and carries
the paragraph it applies, the inputs it used and what was missing, so a case packet can
show its working. Three separate engines, as the spec requires:

  * assess_cancellation  -> DGCA CAR Section 3 Series M Part IV, paras 3.3.x
  * assess_delay         -> DGCA CAR Section 3 Series M Part IV, paras 3.4.x
  * assess_refund        -> DGCA CAR Section 3 Series M Part II

Condition ids ending in `_breach` or `_obligation` are phrased as the passenger's claim:
SUPPORTED means the facts support it, NOT_SUPPORTED means they contradict it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Union

Number = Union[int, float, str, Decimal]


class Status(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class RulePack:
    id: str
    title: str
    revision: str
    dated: str
    effective: str
    source_url: Optional[str]
    verified: bool
    note: str


PART_IV = RulePack(
    id="DGCA-CAR-S3-M-IV",
    title="Facilities to be provided to passengers by airlines due to denied boarding, "
          "cancellation of flights and delays in flights",
    revision="Rev. 4", dated="2023-01-25", effective="2023-02-15",
    source_url="https://www.dgca.gov.in/digigov-portal/Upload?flag=iframeAttachView&attachId=we1PSlOuQhYdHcwKKrm7ew%3D%3D",
    verified=True,
    note="Paragraph text checked against the official PDF on 2026-11-22. Re-check for later amendments before release.",
)

PART_II = RulePack(
    id="DGCA-CAR-S3-M-II",
    title="Refund of airline tickets to passengers of public transport undertakings",
    revision="Rev. 3", dated="2026-02-24", effective="2026-03-26",
    source_url=None,
    verified=False,
    note="Primary Rev. 3 text could not be retrieved. The dgca.gov.in file found is an older version "
         "(21 working days; look-in barred inside 5 days). The 14 working days and 7-day look-in figures "
         "come from news reports of the 2026 revision only. Treat refund timing as UNVERIFIED.",
)


@dataclass
class Condition:
    id: str
    rule_ref: str
    label: str
    status: Status
    detail: str
    inputs: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)


@dataclass
class Assessment:
    kind: str
    pack: RulePack
    conditions: list
    amounts: dict
    notes: list = field(default_factory=list)

    def get(self, cid: str) -> Condition:
        return next(c for c in self.conditions if c.id == cid)

    @property
    def missing(self) -> list:
        out: list = []
        for c in self.conditions:
            for m in c.missing:
                if m not in out:
                    out.append(m)
        return out


def D(v: Optional[Number]) -> Optional[Decimal]:
    return None if v is None else Decimal(str(v))


def _cond(id: str, ref: str, label: str, status: Status, detail: str, inputs: Optional[dict] = None,
          missing: Optional[list] = None) -> Condition:
    return Condition(id, ref, label, status, detail, inputs or {}, missing or [])


def _fmt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# =====================================================================================
# Cancellation (Part IV, 3.3)
# =====================================================================================
@dataclass
class CancellationFacts:
    domestic: Optional[bool] = True
    scheduled_departure: Optional[datetime] = None
    informed_at: Optional[datetime] = None
    block_time_hours: Optional[Number] = None
    basic_fare: Optional[Number] = None          # booked one-way basic fare, NOT total ticket value
    fuel_charge: Optional[Number] = None         # airline fuel charge
    alt_or_refund_offered: Optional[bool] = None
    alternate_accepted: Optional[bool] = None    # passenger accepted an alternate flight
    contact_info_provided: Optional[bool] = None  # email id or phone number given at booking/ticketing
    extraordinary_claimed: Optional[bool] = None  # airline cited extraordinary circumstances
    same_ticket_connection_missed: Optional[bool] = None


def compensation_cap(block_time_hours: Number) -> Decimal:
    """Para 3.3.2 (a)-(c). Boundaries: <=1h, >1h and <=2h, >2h."""
    h = D(block_time_hours)
    assert h is not None
    if h <= 1:
        return Decimal(5000)
    if h <= 2:
        return Decimal(7500)
    return Decimal(10000)


def assess_cancellation(f: CancellationFacts) -> Assessment:
    pack = PART_IV
    if f.domestic is False:
        c = _cond("scope", "-", "Domestic flight", Status.NOT_APPLICABLE,
                  "International flights need a separate, jurisdiction-specific rule pack.")
        return Assessment("cancellation", pack, [c], {})
    conds: list[Condition] = []

    # --- 3.3.1: was the passenger informed as the CAR requires? ------------------------
    lead: Optional[timedelta] = None
    if f.scheduled_departure and f.informed_at:
        lead = f.scheduled_departure - f.informed_at
    if lead is None:
        informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.UNKNOWN,
                         "Need both the scheduled departure and when the passenger was told.",
                         missing=["scheduled departure time", "time the passenger was informed"])
        window = None
    else:
        inputs = {"scheduled_departure": _fmt(f.scheduled_departure), "informed_at": _fmt(f.informed_at),
                  "notice_hours": round(lead.total_seconds() / 3600, 2)}
        if lead >= timedelta(days=14):
            window = "at least two weeks"
            informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.SUPPORTED,
                             "Informed at least two weeks before departure.", inputs)
        elif lead >= timedelta(hours=24):
            window = "less than two weeks and at least 24 hours"
            if f.alt_or_refund_offered is True:
                informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.SUPPORTED,
                                 "Informed 24h-2 weeks before and an alternate flight or refund was offered.", inputs)
            elif f.alt_or_refund_offered is False:
                informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.NOT_SUPPORTED,
                                 "Informed 24h-2 weeks before, but no alternate flight or refund was offered.", inputs)
            else:
                informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.UNKNOWN,
                                 "In this window the CAR requires an alternate flight or refund offer; "
                                 "whether one was made is not known.", inputs,
                                 ["whether the airline offered an alternate flight or refund"])
        else:
            window = "less than 24 hours (or after departure)"
            informed = _cond("informed_per_331", "3.3.1", "Passenger informed as per 3.3.1", Status.NOT_SUPPORTED,
                             "Informed less than 24 hours before departure, outside the notice windows in 3.3.1.",
                             inputs)
    conds.append(informed)

    conds.append(_cond(
        "alt_or_refund_obligation", "3.3.1, 3.3.5", "Alternate flight or refund owed", Status.SUPPORTED,
        "On cancellation the airline must arrange an alternate flight or a full refund as the passenger chooses; "
        "refunds follow CAR Part II." + (f" Notice window: {window}." if window else ""),
        {"alt_or_refund_offered": f.alt_or_refund_offered}))

    # --- 3.3.2: compensation trigger --------------------------------------------------
    if f.same_ticket_connection_missed is True:
        trig = _cond("compensation_trigger", "3.3.2", "Compensation trigger met", Status.SUPPORTED,
                     "Passenger missed a connecting flight booked on the same ticket number.")
    elif informed.status == Status.NOT_SUPPORTED:
        trig = _cond("compensation_trigger", "3.3.2", "Compensation trigger met", Status.SUPPORTED,
                     "Passenger was not informed as per 3.3.1.")
    elif informed.status == Status.SUPPORTED:
        trig = _cond("compensation_trigger", "3.3.2", "Compensation trigger met", Status.NOT_SUPPORTED,
                     "Passenger was informed as per 3.3.1 and no same-ticket connection was missed.")
    else:
        trig = _cond("compensation_trigger", "3.3.2", "Compensation trigger met", Status.UNKNOWN,
                     "Cannot decide until the notification facts are known.", missing=informed.missing)
    conds.append(trig)

    # --- 3.3.3 contact information exception -----------------------------------------
    if f.contact_info_provided is False:
        contact = _cond("contact_exception", "3.3.3", "No-contact-information exception applies", Status.SUPPORTED,
                        "No email id or phone number was given at booking or ticketing: no financial compensation, "
                        "but the refund or alternate-travel obligation and waiting facilities remain.")
    elif f.contact_info_provided is True:
        contact = _cond("contact_exception", "3.3.3", "No-contact-information exception applies",
                        Status.NOT_SUPPORTED, "Passenger gave an email id or phone number.")
    else:
        contact = _cond("contact_exception", "3.3.3", "No-contact-information exception applies", Status.UNKNOWN,
                        "Not known whether contact details were given at booking.",
                        missing=["whether an email or phone number was given at booking"])
    conds.append(contact)

    # --- 3.3.4 extraordinary circumstances (compensation only) -----------------------
    if f.extraordinary_claimed is True:
        extra = _cond("extraordinary_exception", "3.3.4, 1.4, 1.5", "Extraordinary-circumstances exception",
                      Status.REVIEW_REQUIRED,
                      "The airline cited extraordinary circumstances. Compensation is barred only if they were "
                      "beyond the airline's control and unavoidable (1.4, 1.5; includes ATC, weather, security). "
                      "This cannot be verified from passenger documents. The refund or alternate-flight "
                      "obligation is not affected.")
    elif f.extraordinary_claimed is False:
        extra = _cond("extraordinary_exception", "3.3.4, 1.4, 1.5", "Extraordinary-circumstances exception",
                      Status.NOT_SUPPORTED, "No extraordinary circumstance was cited.")
    else:
        extra = _cond("extraordinary_exception", "3.3.4, 1.4, 1.5", "Extraordinary-circumstances exception",
                      Status.UNKNOWN, "Reason for cancellation is not known.",
                      missing=["reason the airline gave for the cancellation"])
    conds.append(extra)

    # --- amount ----------------------------------------------------------------------
    block, basic, fuel = D(f.block_time_hours), D(f.basic_fare), D(f.fuel_charge)
    amt_missing = [n for n, v in (("flight block time", block), ("booked one-way basic fare", basic),
                                  ("airline fuel charge", fuel)) if v is None]
    cap = compensation_cap(block) if block is not None else None
    base = (basic + fuel) if basic is not None and fuel is not None else None
    potential = min(cap, base) if cap is not None and base is not None else None
    formula = None
    if potential is not None:
        formula = f"min({cap}, {basic} + {fuel}) = {potential}"

    # --- final compensation status ---------------------------------------------------
    if trig.status == Status.NOT_SUPPORTED:
        final, why, miss = Status.NOT_SUPPORTED, "Trigger not met.", []
    elif f.alternate_accepted is True:
        final, why, miss = Status.NOT_APPLICABLE, "Passenger accepted an alternate flight, which satisfies 3.3.2.", []
    elif contact.status == Status.SUPPORTED:
        final, why, miss = Status.NOT_SUPPORTED, "No-contact-information exception (3.3.3).", []
    elif extra.status == Status.REVIEW_REQUIRED:
        final, why, miss = Status.REVIEW_REQUIRED, "Airline cited extraordinary circumstances (3.3.4).", amt_missing
    elif any(c.status == Status.UNKNOWN for c in (trig, contact, extra)) or amt_missing:
        miss = list(dict.fromkeys(trig.missing + contact.missing + extra.missing + amt_missing))
        final, why = Status.UNKNOWN, "Inputs missing."
    else:
        final, why, miss = Status.SUPPORTED, "Trigger met, no exception, amount computable.", []
    conds.append(_cond(
        "compensation", "3.3.2", "Financial compensation (in addition to full refund)", final,
        why + (f" Formula: {formula}." if formula else ""),
        {"cap": str(cap) if cap is not None else None,
         "basic_fare_plus_fuel": str(base) if base is not None else None}, miss))

    amounts = {"potential_compensation": potential, "payable_compensation":
               potential if final == Status.SUPPORTED else None, "formula": formula}

    # --- waiting facilities ----------------------------------------------------------
    conds.append(_cond(
        "waiting_facilities", "3.3.2, 3.3.3, 3.8.1(a)", "Meals and refreshments while waiting at the airport",
        Status.UNKNOWN if f.alternate_accepted is None else (Status.SUPPORTED if f.alternate_accepted else Status.NOT_APPLICABLE),
        "Owed if the passenger had already reported for the original flight and is waiting for an alternate flight.",
        missing=["whether the passenger reported at the airport and waited for an alternate"]
        if f.alternate_accepted is None else []))
    return Assessment("cancellation", pack, conds, amounts)


# =====================================================================================
# Delay (Part IV, 3.4)
# =====================================================================================
@dataclass
class DelayFacts:
    domestic: Optional[bool] = True
    scheduled_departure: Optional[datetime] = None        # published/original, with timezone offset
    expected_departure: Optional[datetime] = None         # latest revised or actual departure
    previous_revised_departure: Optional[datetime] = None  # an earlier revised time, if any
    previous_revision_informed_at: Optional[datetime] = None
    block_time_hours: Optional[Number] = None
    checked_in_on_time: Optional[bool] = None
    extraordinary_claimed: Optional[bool] = None
    accommodation_needed: Optional[bool] = None


def meal_threshold(block_time_hours: Number) -> timedelta:
    """Para 3.4.1 (a)-(c)."""
    h = D(block_time_hours)
    assert h is not None
    if h <= Decimal("2.5"):
        return timedelta(hours=2)
    if h <= 5:
        return timedelta(hours=3)
    return timedelta(hours=4)


def in_night_window(dt: datetime) -> bool:
    """Scheduled between 2000 and 0300 hrs in the departure airport's local time (the dt's own offset)."""
    t = dt.timetz().replace(tzinfo=None)
    return t.hour >= 20 or t.hour < 3 or (t.hour == 3 and t.minute == 0 and t.second == 0)


def assess_delay(f: DelayFacts) -> Assessment:
    pack = PART_IV
    if f.domestic is False:
        c = _cond("scope", "-", "Domestic flight", Status.NOT_APPLICABLE,
                  "International flights need a separate, jurisdiction-specific rule pack.")
        return Assessment("delay", pack, [c], {})
    conds: list[Condition] = []
    notes = ["Para 3.4.5: the burden of proof about whether and when the passenger was informed of the delay "
             "rests with the operating airline. Keep every notification you received."]

    if not (f.scheduled_departure and f.expected_departure):
        miss = [m for m, v in (("scheduled departure time", f.scheduled_departure),
                               ("expected or actual departure time", f.expected_departure)) if not v]
        for cid, ref, label in (("meals_obligation", "3.4.1", "Meals and refreshments"),
                                ("alt_or_refund_obligation", "3.4.2", "Alternate flight within 6 hours or full refund"),
                                ("hotel_obligation", "3.4.3", "Hotel accommodation")):
            conds.append(_cond(cid, ref, label, Status.UNKNOWN, "Delay cannot be measured.", missing=miss))
    else:
        sched, exp = f.scheduled_departure, f.expected_departure
        total = exp - sched
        hours = round(total.total_seconds() / 3600, 2)
        base_inputs = {"scheduled_departure": _fmt(sched), "expected_departure": _fmt(exp), "delay_hours": hours}

        # 3.4.1 meals
        if f.block_time_hours is None:
            conds.append(_cond("meals_obligation", "3.4.1", "Meals and refreshments", Status.UNKNOWN,
                               "Flight block time is needed to pick the threshold.", base_inputs,
                               ["flight block time"]))
        elif f.checked_in_on_time is False:
            conds.append(_cond("meals_obligation", "3.4.1", "Meals and refreshments", Status.NOT_SUPPORTED,
                               "Passenger did not check in on time.", base_inputs))
        else:
            thr = meal_threshold(f.block_time_hours)
            met = total >= thr
            inputs = {**base_inputs, "threshold_hours": thr.total_seconds() / 3600}
            if not met:
                conds.append(_cond("meals_obligation", "3.4.1", "Meals and refreshments", Status.NOT_SUPPORTED,
                                   f"Expected delay {hours}h is below the {thr.total_seconds()/3600:g}h threshold.", inputs))
            elif f.checked_in_on_time is None:
                conds.append(_cond("meals_obligation", "3.4.1", "Meals and refreshments", Status.UNKNOWN,
                                   "Delay threshold met; timely check-in is required and not yet shown.", inputs,
                                   ["proof of timely check-in"]))
            elif f.extraordinary_claimed is True:
                conds.append(_cond("meals_obligation", "3.4.1, 3.4.4", "Meals and refreshments", Status.REVIEW_REQUIRED,
                                   "Threshold met, but the airline cited extraordinary circumstances, which can "
                                   "relieve Para 3.8 facilities (3.4.4).", inputs))
            else:
                conds.append(_cond("meals_obligation", "3.4.1", "Meals and refreshments", Status.SUPPORTED,
                                   f"Checked in on time and expected delay {hours}h meets the "
                                   f"{thr.total_seconds()/3600:g}h threshold.", inputs))

        # 3.4.2 alternate flight within 6h or full refund
        if f.domestic is None:
            conds.append(_cond("alt_or_refund_obligation", "3.4.2", "Alternate flight within 6 hours or full refund",
                               Status.UNKNOWN, "Domestic or international is not known.",
                               missing=["whether the flight is domestic"]))
        else:
            baseline, label = sched, "published scheduled departure"
            prev, prev_inf = f.previous_revised_departure, f.previous_revision_informed_at
            if prev and prev_inf and (sched - prev_inf) > timedelta(hours=24):
                baseline, label = prev, "previously revised departure (communicated more than 24h before the original)"
            delay = exp - baseline
            inputs = {**base_inputs, "baseline": label, "baseline_time": _fmt(baseline),
                      "delay_hours": round(delay.total_seconds() / 3600, 2)}
            if delay > timedelta(hours=6):
                conds.append(_cond("alt_or_refund_obligation", "3.4.2", "Alternate flight within 6 hours or full refund",
                                   Status.SUPPORTED, f"Delay of {inputs['delay_hours']}h exceeds 6h from the {label}. "
                                   "The airline must offer an alternate flight within 6 hours or a full refund. "
                                   "The extraordinary-circumstances relief in 3.4.4 does not cover this paragraph.",
                                   inputs))
            else:
                conds.append(_cond("alt_or_refund_obligation", "3.4.2", "Alternate flight within 6 hours or full refund",
                                   Status.NOT_SUPPORTED, f"Delay of {inputs['delay_hours']}h from the {label} is "
                                   "not more than 6h (exactly 6h does not qualify).", inputs))

        # 3.4.3 hotel
        night = in_night_window(sched)
        thr_hit = total > timedelta(hours=24) or (night and total > timedelta(hours=6))
        inputs = {**base_inputs, "scheduled_in_2000_0300_window": night}
        if not thr_hit:
            conds.append(_cond("hotel_obligation", "3.4.3", "Hotel accommodation", Status.NOT_SUPPORTED,
                               "Delay is not more than 24h, nor more than 6h for a flight scheduled 2000-0300.", inputs))
        elif f.extraordinary_claimed is True:
            conds.append(_cond("hotel_obligation", "3.4.3, 3.4.4, 3.8.1(b)", "Hotel accommodation",
                               Status.REVIEW_REQUIRED, "Threshold met, but the airline cited extraordinary circumstances "
                               "(3.4.4).", inputs))
        elif f.accommodation_needed is None:
            conds.append(_cond("hotel_obligation", "3.4.3, 3.8.1(b)", "Hotel accommodation", Status.REVIEW_REQUIRED,
                               "Threshold met. Hotel accommodation (with transfers) is owed when necessary: confirm "
                               "whether the passenger needed it.", inputs, ["whether hotel accommodation was needed"]))
        elif f.accommodation_needed:
            conds.append(_cond("hotel_obligation", "3.4.3, 3.8.1(b)", "Hotel accommodation", Status.SUPPORTED,
                               "Threshold met and accommodation was necessary.", inputs))
        else:
            conds.append(_cond("hotel_obligation", "3.4.3, 3.8.1(b)", "Hotel accommodation", Status.NOT_SUPPORTED,
                               "Threshold met but accommodation was not necessary.", inputs))

    conds.append(_cond("cash_compensation", "3.4", "Statutory cash compensation for delay", Status.NOT_SUPPORTED,
                       "Part IV sets no cash-compensation formula for delays. Do not promise any. Other entitlements "
                       "(contract, insurance) are separate."))
    return Assessment("delay", pack, conds, {}, notes)


# =====================================================================================
# Refund (Part II)
# =====================================================================================
@dataclass
class RefundFacts:
    initiated_by: Optional[str] = None            # "airline" | "passenger"
    payment_mode: Optional[str] = None            # "credit_card" | "cash" | "agent_portal" | "other"
    cancelled_at: Optional[datetime] = None
    refund_received_on: Optional[date] = None
    as_of: Optional[date] = None
    total_paid: Optional[Number] = None
    basic_fare: Optional[Number] = None
    fuel_charge: Optional[Number] = None
    statutory_fees: Optional[Number] = None        # statutory taxes + UDF/ADF/PSF
    cancellation_charge_levied: Optional[Number] = None
    refund_received_amount: Optional[Number] = None
    refund_given_as_credit_shell: Optional[bool] = None
    credit_shell_accepted_voluntarily: Optional[bool] = None
    booked_via_airline_website: Optional[bool] = None
    booked_at: Optional[datetime] = None
    flight_departure: Optional[datetime] = None
    domestic: Optional[bool] = True


def add_working_days(start: date, n: int) -> date:
    """Mon-Fri only. Public holidays are not modelled; the case packet says so."""
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def refund_due_date(mode: Optional[str], cancelled_on: date) -> Optional[date]:
    if mode == "credit_card":
        return cancelled_on + timedelta(days=7)
    if mode == "cash":
        return cancelled_on
    if mode == "agent_portal":
        return add_working_days(cancelled_on, 14)
    return None


def assess_refund(f: RefundFacts) -> Assessment:
    pack = PART_II
    conds: list[Condition] = []
    notes = [pack.note, "Working days are counted Monday-Friday; public holidays are not modelled."]
    total, basic, fuel = D(f.total_paid), D(f.basic_fare), D(f.fuel_charge)
    fees, charge, got = D(f.statutory_fees), D(f.cancellation_charge_levied), D(f.refund_received_amount)

    # timeline
    due = refund_due_date(f.payment_mode, f.cancelled_at.date()) if f.cancelled_at else None
    if due is None:
        conds.append(_cond("refund_timeline_breach", "3(a)-(c)", "Refund paid late", Status.UNKNOWN,
                           "Need the cancellation date and a payment mode of credit card, cash or agent/portal.",
                           missing=["cancellation date", "payment mode and booking channel"]))
    else:
        inputs = {"cancelled_at": _fmt(f.cancelled_at), "payment_mode": f.payment_mode, "due_on": due.isoformat()}
        if f.refund_received_on:
            late = f.refund_received_on > due
            conds.append(_cond("refund_timeline_breach", "3(a)-(c)", "Refund paid late",
                               Status.SUPPORTED if late else Status.NOT_SUPPORTED,
                               f"Refund received {f.refund_received_on}, due by {due}.", inputs))
        elif f.as_of:
            overdue = f.as_of > due
            conds.append(_cond("refund_timeline_breach", "3(a)-(c)", "Refund paid late",
                               Status.SUPPORTED if overdue else Status.NOT_SUPPORTED,
                               f"No refund received; due by {due}, today is {f.as_of}." if overdue
                               else f"Not yet due: due by {due}.", inputs))
        else:
            conds.append(_cond("refund_timeline_breach", "3(a)-(c)", "Refund paid late", Status.UNKNOWN,
                               "Need the refund receipt date or today's date.", inputs, ["refund received date"]))

    # statutory taxes and fees
    if fees is None or got is None:
        conds.append(_cond("statutory_fees_breach", "3(d)", "Statutory taxes and UDF/ADF/PSF not fully refunded",
                           Status.UNKNOWN, "Need the statutory fee amount and the refund received.",
                           missing=[m for m, v in (("statutory taxes and UDF/ADF/PSF amount", fees),
                                                   ("actual refund amount received", got)) if v is None]))
    else:
        short = got < fees and f.refund_given_as_credit_shell is not True
        conds.append(_cond("statutory_fees_breach", "3(d)", "Statutory taxes and UDF/ADF/PSF not fully refunded",
                           Status.SUPPORTED if short else Status.NOT_SUPPORTED,
                           f"Received {got}; statutory taxes and fees are {fees}. These are refundable even on "
                           "non-refundable fares.", {"received": str(got), "statutory_fees": str(fees)}))

    # cancellation charge cap
    if f.initiated_by == "airline":
        if charge is None:
            conds.append(_cond("cancellation_charge_breach", "3(i), 3(j)", "Cancellation or processing charge levied",
                               Status.UNKNOWN, "Not known whether any charge was deducted.",
                               missing=["any charge deducted from the refund"]))
        else:
            conds.append(_cond("cancellation_charge_breach", "3(i), 3(j)", "Cancellation or processing charge levied",
                               Status.SUPPORTED if charge > 0 else Status.NOT_SUPPORTED,
                               "Airline-initiated cancellations carry no passenger cancellation charge; no charge may "
                               "be levied to process the refund." if charge > 0 else "No charge deducted."))
    elif f.initiated_by == "passenger":
        cap = (basic + fuel) if basic is not None and fuel is not None else None
        if charge is None or cap is None:
            conds.append(_cond("cancellation_charge_breach", "3(i)", "Cancellation charge above basic fare + fuel charge",
                               Status.UNKNOWN, "Need the charge levied, basic fare and fuel charge.",
                               missing=[m for m, v in (("cancellation charge levied", charge), ("basic fare", basic),
                                                       ("fuel charge", fuel)) if v is None]))
        elif charge > cap:
            st = Status.REVIEW_REQUIRED if f.payment_mode == "agent_portal" else Status.SUPPORTED
            conds.append(_cond("cancellation_charge_breach", "3(i)", "Cancellation charge above basic fare + fuel charge",
                               st, f"Charge {charge} exceeds basic fare + fuel charge {cap}."
                               + (" Fully disclosed travel-agent charges are excluded: check the booking terms."
                                  if st == Status.REVIEW_REQUIRED else ""),
                               {"charge": str(charge), "cap": str(cap)}))
        else:
            conds.append(_cond("cancellation_charge_breach", "3(i)", "Cancellation charge above basic fare + fuel charge",
                               Status.NOT_SUPPORTED, f"Charge {charge} is within the cap {cap}."))
    else:
        conds.append(_cond("cancellation_charge_breach", "3(i), 3(j)", "Cancellation charge", Status.UNKNOWN,
                           "Need to know who cancelled.", missing=["who cancelled: airline or passenger"]))

    # credit shell
    if f.refund_given_as_credit_shell is not True:
        st, det, miss = Status.NOT_APPLICABLE, "No credit shell was used.", []
        if f.refund_given_as_credit_shell is None:
            st, det, miss = Status.UNKNOWN, "Not known whether the refund was given as a credit shell.", \
                ["whether the refund was given as a credit shell"]
        conds.append(_cond("credit_shell_breach", "3(f)", "Credit shell imposed", st, det, missing=miss))
    elif f.credit_shell_accepted_voluntarily is None:
        conds.append(_cond("credit_shell_breach", "3(f)", "Credit shell imposed", Status.UNKNOWN,
                           "Holding a refund in a credit shell is the passenger's choice; did the passenger choose it?",
                           missing=["whether the passenger chose the credit shell"]))
    else:
        conds.append(_cond("credit_shell_breach", "3(f)", "Credit shell imposed",
                           Status.NOT_SUPPORTED if f.credit_shell_accepted_voluntarily else Status.SUPPORTED,
                           "Passenger chose the credit shell." if f.credit_shell_accepted_voluntarily
                           else "A credit shell is the passenger's prerogative, not the airline's default."))

    # look-in (passenger-initiated only)
    if f.initiated_by == "airline":
        conds.append(_cond("look_in_eligible", "3(e)", "48-hour look-in option", Status.NOT_APPLICABLE,
                           "Look-in applies to passenger-initiated changes."))
    elif f.booked_via_airline_website is not True:
        conds.append(_cond("look_in_eligible", "3(e)", "48-hour look-in option",
                           Status.NOT_APPLICABLE if f.booked_via_airline_website is False else Status.UNKNOWN,
                           "Look-in is stated for tickets booked directly on the airline website; check the exact "
                           "provision for third-party bookings." if f.booked_via_airline_website is False
                           else "Not known whether booked on the airline website.",
                           missing=[] if f.booked_via_airline_website is False else ["booking channel"]))
    elif not (f.booked_at and f.cancelled_at and f.flight_departure and f.domestic is not None):
        conds.append(_cond("look_in_eligible", "3(e)", "48-hour look-in option", Status.UNKNOWN,
                           "Need booking time, cancellation time and flight departure.",
                           missing=["booking time", "cancellation time", "flight departure"]))
    else:
        min_days = 7 if f.domestic else 15
        in_window = (f.cancelled_at - f.booked_at) <= timedelta(hours=48)
        far_enough = (f.flight_departure - f.booked_at) >= timedelta(days=min_days)
        conds.append(_cond("look_in_eligible", "3(e)", "48-hour look-in option",
                           Status.SUPPORTED if in_window and far_enough else Status.NOT_SUPPORTED,
                           f"Cancelled within 48h: {in_window}; departure at least {min_days} days after booking: "
                           f"{far_enough}. The 7/15-day figures are UNVERIFIED (2026 revision, news reports only)."))

    # amounts
    expected = None
    if total is not None:
        if f.initiated_by == "airline":
            expected = total
        elif f.initiated_by == "passenger" and charge is not None:
            look_in = next(c for c in conds if c.id == "look_in_eligible").status == Status.SUPPORTED
            expected = total if look_in else max(total - charge, fees or Decimal(0))
    shortfall = None
    if expected is not None and got is not None and f.refund_given_as_credit_shell is not True:
        shortfall = max(expected - got, Decimal(0))
    amounts = {"expected_refund": expected, "refund_received": got, "shortfall": shortfall,
               "statutory_fees": fees}
    return Assessment("refund", pack, conds, amounts, notes)
