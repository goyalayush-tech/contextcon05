"""Turn raw case facts into a recovery packet: assessments, timeline, evidence index,
airline escalation route and a complaint draft. Nothing here sends anything.

Facts arrive as {name: value} or {name: {"value": ..., "doc": ..., "snippet": ...}}. A fact
without a document is kept but labelled "stated by passenger, no document" in the evidence index.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .rules import (Assessment, CancellationFacts, DelayFacts, RefundFacts, Status, assess_cancellation,
                    assess_delay, assess_refund)

IST = timezone(timedelta(hours=5, minutes=30))
EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "data" / "airline_evidence.json"

DATETIME_FIELDS = {"scheduled_departure", "informed_at", "expected_departure", "previous_revised_departure",
                   "previous_revision_informed_at", "cancelled_at", "booked_at", "flight_departure"}
DATE_FIELDS = {"refund_received_on", "as_of"}
KINDS = {"cancellation": (CancellationFacts, assess_cancellation), "delay": (DelayFacts, assess_delay),
         "refund": (RefundFacts, assess_refund)}


def load_evidence(path: Path = EVIDENCE_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _unwrap(raw: dict) -> tuple[dict, list]:
    """Split facts into plain values and an evidence index."""
    values, index = {}, []
    for name, item in raw.items():
        if isinstance(item, dict) and "value" in item:
            values[name] = item["value"]
            index.append({"fact": name, "value": item["value"], "doc": item.get("doc"),
                          "snippet": item.get("snippet"),
                          "provenance": "document" if item.get("doc") else "stated by passenger, no document"})
        else:
            values[name] = item
            index.append({"fact": name, "value": item, "doc": None, "snippet": None,
                          "provenance": "stated by passenger, no document"})
    return values, index


def _coerce(name: str, v: Any) -> Any:
    if v is None or v == "":
        return None
    if name in DATETIME_FIELDS and isinstance(v, str):
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=IST)
    if name in DATE_FIELDS and isinstance(v, str):
        return date.fromisoformat(v)
    return v


def jsonable(o: Any) -> Any:
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if is_dataclass(o) and not isinstance(o, type):
        return {k: jsonable(v) for k, v in asdict(o).items()}
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


def resolve_airline(flight: dict, evidence: dict) -> dict:
    """Operating carrier decides who owes what (CAR 1.3, 3.1.3). Never assume the ticket's first airline."""
    operating, marketing = flight.get("operating_carrier"), flight.get("marketing_carrier")
    notes: list[str] = []
    if not operating:
        return {"status": "REVIEW_REQUIRED", "code": None, "record": None,
                "notes": ["Operating carrier is not stated. The ticket may show a marketing carrier or a travel "
                          "agent; the airline that actually operated the flight is the one that owes the passenger. "
                          "Check the e-ticket or boarding pass for 'operated by'."]}
    if marketing and marketing != operating:
        notes.append(f"Ticket shows marketing carrier {marketing}; operating carrier is {operating}. "
                     "The complaint goes to the operating carrier.")
    rec = evidence["airlines"].get(operating)
    if not rec:
        return {"status": "CANNOT_VERIFY", "code": operating, "record": None,
                "notes": notes + [f"No airline record for '{operating}'. Cannot verify the airline or its grievance route."]}
    return {"status": "RESOLVED", "code": operating, "record": rec, "notes": notes}


def _route(airline: dict) -> list[dict]:
    rec, g = airline.get("record"), None
    steps: list[dict] = []
    if rec:
        g = rec["grievance"]
        name = rec["airline"]
        if g["status"] == "primary_verified":
            c = g["contacts"]
            steps.append({"step": 1, "to": f"{name} customer support",
                          "how": c.get("portal") or c.get("customer_email") or "airline customer support",
                          "note": g.get("advice", "Write first and keep the reference number it issues (CAR 3.10.5).")})
            steps.append({"step": 2, "to": f"{name} Nodal Officer", "how": c["nodal_officer_email"],
                          "note": "If the first reply is unsatisfactory."})
            steps.append({"step": 3, "to": f"{name} Appellate Authority", "how": c["appellate_authority_email"],
                          "note": "If still unsatisfied; quote the original grievance."})
            steps.append({"step": 4, "to": "AirSewa (Ministry of Civil Aviation)", "how": "https://airsewa.gov.in/#/home",
                          "note": "CAR 3.9.2: the passenger may file on the Air Sewa app or portal."})
            return steps
        steps.append({"step": 1, "to": f"{name} grievance route", "how": "CANNOT VERIFY",
                      "note": g.get("status_for_packet") or g.get("detail", "Check the airline's website.")})
    steps.append({"step": len(steps) + 1, "to": "AirSewa (Ministry of Civil Aviation)",
                  "how": "https://airsewa.gov.in/#/home", "note": "CAR 3.9.2 (verified)."})
    return steps


def _timeline(vals: dict, kind: str) -> list[dict]:
    labels = {"booked_at": "Ticket booked", "informed_at": "Airline informed the passenger",
              "scheduled_departure": "Original scheduled departure", "expected_departure": "Revised / actual departure",
              "previous_revised_departure": "Earlier revised departure", "cancelled_at": "Ticket cancelled",
              "flight_departure": "Flight departure", "previous_revision_informed_at": "Earlier revision communicated",
              "refund_received_on": "Refund received"}
    events = []
    for k, label in labels.items():
        v = vals.get(k)
        if v is None:
            continue
        v = _coerce(k, v)
        sortkey = v if isinstance(v, datetime) else datetime(v.year, v.month, v.day, tzinfo=IST)
        events.append({"time": v.isoformat(), "event": label, "field": k, "_k": sortkey})
    events.sort(key=lambda e: e["_k"])
    for e in events:
        e.pop("_k")
    return events


ENTITLEMENTS = {"alt_or_refund_obligation", "compensation", "meals_obligation", "hotel_obligation", "waiting_facilities",
                "refund_timeline_breach", "statutory_fees_breach", "cancellation_charge_breach", "credit_shell_breach"}


def _headline(a: Assessment) -> list[str]:
    out = []
    for c in a.conditions:
        if c.id not in ENTITLEMENTS:
            continue
        if c.status == Status.SUPPORTED:
            out.append(f"SUPPORTED: {c.label} (para {c.rule_ref}). {c.detail}")
        elif c.status == Status.REVIEW_REQUIRED:
            out.append(f"NEEDS REVIEW: {c.label} (para {c.rule_ref}). {c.detail}")
    return out


def _complaint(kind: str, flight: dict, vals: dict, a: Assessment, airline: dict) -> str:
    rec = airline.get("record")
    name = rec["airline"] if rec else (airline.get("code") or "the operating airline")
    g = rec["grievance"] if rec else {}
    to = g.get("contacts", {}).get("nodal_officer_email", "[verify the nodal officer address on the airline's website]")
    fno, fdate = flight.get("flight_number", "[flight number]"), flight.get("date", "[date]")
    lines = [f"DRAFT, NOT SENT. Review every line and attach your documents before sending.", "",
             f"To: The Nodal Officer, {name} <{to}>",
             f"Subject: Complaint under DGCA CAR Section 3, Series M, Part {'II' if kind == 'refund' else 'IV'}: "
             f"flight {fno} on {fdate}" + (f", booking reference {flight['pnr']}" if flight.get("pnr") else ""), "",
             "Dear Sir/Madam,", "",
             f"I was booked on {fno} from {flight.get('origin', '[origin]')} to {flight.get('destination', '[destination]')} "
             f"on {fdate}. The following facts are taken from my documents:"]
    for k in ("scheduled_departure", "informed_at", "expected_departure", "cancelled_at", "refund_received_on"):
        if vals.get(k) is not None:
            lines.append(f"  - {k.replace('_', ' ')}: {_coerce(k, vals[k]).isoformat()}")
    lines += ["", "On these facts I ask the airline to:"]
    asks = {
        "alt_or_refund_obligation": ("offer me an alternate flight within 6 hours or a full refund of my ticket"
                                     if kind == "delay" else
                                     "provide an alternate flight acceptable to me, or a full refund of my ticket"),
        "compensation": "pay financial compensation in addition to the full refund",
        "meals_obligation": "provide meals and refreshments for the waiting period",
        "hotel_obligation": "provide hotel accommodation, including transfers",
        "waiting_facilities": "provide meals and refreshments while I wait at the airport",
        "refund_timeline_breach": "pay my refund, which is overdue under the CAR refund timeline",
        "statutory_fees_breach": "refund the statutory taxes and UDF/ADF/PSF in full",
        "cancellation_charge_breach": "reverse the cancellation or processing charge, which the CAR does not allow",
        "credit_shell_breach": "refund to my original payment method; holding a credit shell is my choice, not the default",
    }
    n = 0
    for c in a.conditions:
        if c.status == Status.SUPPORTED and c.id in asks:
            n += 1
            ask = asks[c.id]
            if c.id == "compensation" and a.amounts.get("payable_compensation") is not None:
                ask += f" of Rs {a.amounts['payable_compensation']} ({a.amounts['formula']})"
            lines.append(f"  {n}. {ask}. [CAR Part {'II' if kind == 'refund' else 'IV'}, para {c.rule_ref}]")
    sf = a.amounts.get("shortfall")
    if sf:
        lines.append(f"  {n + 1}. Pay the refund shortfall of Rs {sf}.")
        n += 1
    for c in a.conditions:
        if c.status == Status.REVIEW_REQUIRED:
            lines.append(f"  - Regarding '{c.label}': if the airline relies on extraordinary circumstances, please "
                         "state them and provide the supporting records.")
    if n == 0:
        lines.append("  (No claim is supported by the facts provided yet. See the missing-information list.)")
    if kind == "delay":
        lines.append("  - Under para 3.4.5 the burden of proof about whether and when I was informed of the delay "
                     "rests with the airline; please provide its notification records.")
    lines += ["", "Please acknowledge with a reference number and reply within the timeline in your passenger charter.",
              "", "Yours faithfully,", "[Passenger name]", "[Contact details]"]
    return "\n".join(lines)


def build_case(payload: dict, evidence: Optional[dict] = None) -> dict:
    evidence = evidence or load_evidence()
    kind = payload.get("case_type")
    if kind not in KINDS:
        raise ValueError(f"case_type must be one of {sorted(KINDS)}")
    flight = payload.get("flight", {})
    raw_vals, index = _unwrap(payload.get("facts", {}))
    cls, engine = KINDS[kind]
    allowed = {f.name for f in fields(cls)}
    unknown = sorted(set(raw_vals) - allowed)
    vals = {k: _coerce(k, v) for k, v in raw_vals.items() if k in allowed}
    if "domestic" not in vals and flight.get("domestic") is not None:
        vals["domestic"] = flight["domestic"]
    if "block_time_hours" in allowed and "block_time_hours" not in vals and flight.get("block_time_hours") is not None:
        vals["block_time_hours"] = flight["block_time_hours"]
    assessment = engine(cls(**vals))
    airline = resolve_airline(flight, evidence)

    missing = list(assessment.missing)
    if airline["status"] != "RESOLVED":
        missing.insert(0, "operating airline (check the e-ticket or boarding pass)" if airline["status"] ==
                       "REVIEW_REQUIRED" else f"airline record for {airline['code']}")
    counts: dict[str, int] = {}
    for c in assessment.conditions:
        counts[c.status.value] = counts.get(c.status.value, 0) + 1

    warnings = list(assessment.notes)
    if not assessment.pack.verified:
        warnings.insert(0, f"Rule pack {assessment.pack.id} {assessment.pack.revision} is NOT verified against primary "
                           "text. Do not rely on its timing figures without checking.")
    if unknown:
        warnings.append(f"Ignored unrecognised facts: {', '.join(unknown)}")
    g = airline["record"]["grievance"] if airline["record"] else None
    if g and g.get("conflicts"):
        warnings.extend(f"Airline source conflict: {c}" for c in g["conflicts"])

    case_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return jsonable({
        "case_id": f"FB-{case_hash}", "case_type": kind,
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "rule_pack": assessment.pack,
        "flight": flight,
        "airline": {"status": airline["status"], "code": airline["code"], "notes": airline["notes"],
                    "identity": airline["record"]["identity"] if airline["record"] else None,
                    "grievance": g},
        "timeline": _timeline(vals, kind),
        "conditions": assessment.conditions,
        "amounts": assessment.amounts,
        "headline": _headline(assessment),
        "status_counts": counts,
        "missing": missing,
        "evidence_index": index,
        "escalation": _route(airline),
        "complaint_draft": _complaint(kind, flight, vals, assessment, airline),
        "approval": {"state": "awaiting_passenger_approval",
                     "note": "Nothing has been sent. Submit manually through the airline's channels or AirSewa."},
        "warnings": warnings,
    })
