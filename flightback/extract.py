"""Deterministic fact suggestions from pasted airline messages or e-ticket text.

Everything returned is a *suggestion with its quote*; the passenger confirms each one in the UI. Nothing is
applied silently. Times without an offset are read as India time (IST).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

DT_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})"), "ymd"),
    (re.compile(r"(\d{1,2})[\s-]([A-Za-z]{3,9})[\s,-]+(\d{4}),?\s*(?:at\s*)?(\d{1,2}):(\d{2})"), "dMy"),
    (re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})[ ,]+(?:at\s*)?(\d{1,2}):(\d{2})"), "dmy"),  # day first, as in India
]
FIELD_HINTS = [
    ("scheduled_departure", r"scheduled|original|std\b|was due|planned|departure"),
    ("expected_departure", r"revised|rescheduled|new time|now depart|etd|delayed to|expected"),
    ("informed_at", r"informed|notified|sent|received|date:|at the time of this message"),
]
AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
AMOUNT_LABELS = [
    ("basic_fare", r"basic fare|base fare"),
    ("fuel_charge", r"fuel|yq"),
    ("statutory_fees", r"tax|udf|adf|psf|passenger service|user development|airport development"),
    ("total_paid", r"total|grand total|amount paid|fare paid"),
    ("refund_received_amount", r"refund"),
]
NAMED_EXTRAORDINARY = r"weather|fog|visibility|thunder|\batc\b|air traffic|strike|security|riot|flood|government order|insurrection|natural disaster"
OPERATIONAL = r"technical|operational|aircraft (?:issue|unavailab)|crew|rotation|maintenance"


def _snip(text: str, a: int, b: int, pad: int = 60) -> str:
    return re.sub(r"\s+", " ", text[max(0, a - pad): b + pad]).strip()


def _hint(text: str, pos: int, hints: list) -> Optional[str]:
    window = text[max(0, pos - 90): pos].lower()
    best, best_at = None, -1
    for name, pat in hints:
        for m in re.finditer(pat, window):
            if m.start() > best_at:
                best, best_at = name, m.start()
    return best


def _parse_dt(kind: str, g: tuple) -> Optional[datetime]:
    try:
        if kind == "ymd":
            y, mo, d, h, mi = map(int, g)
        elif kind == "dMy":
            d, mon, y, h, mi = int(g[0]), MONTHS.get(g[1][:3].lower()), int(g[2]), int(g[3]), int(g[4])
            if not mon:
                return None
            mo = mon
        else:
            d, mo, y, h, mi = map(int, g)
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


def suggest(text: str) -> dict:
    cands: list[dict] = []
    notes: list[str] = []
    seen = set()
    for pat, kind in DT_PATTERNS:
        for m in pat.finditer(text):
            dt = _parse_dt(kind, m.groups())
            if not dt or (m.start(), m.end()) in seen:
                continue
            seen.add((m.start(), m.end()))
            cands.append({"type": "datetime", "value": dt.strftime("%Y-%m-%dT%H:%M"), "suggested_field":
                          _hint(text, m.start(), FIELD_HINTS), "snippet": _snip(text, m.start(), m.end()),
                          "pos": m.start()})
    for m in AMOUNT.finditer(text):
        amt = float(m.group(1).replace(",", ""))
        ctx_before = text[max(0, m.start() - 40): m.start()].lower()
        ctx_after = text[m.end(): m.end() + 25].lower()
        label, nearest = None, -1
        for name, pat in AMOUNT_LABELS:  # the label closest before the amount wins
            for lm in re.finditer(pat, ctx_before):
                if lm.start() > nearest:
                    label, nearest = name, lm.start()
        if label is None:
            for name, pat in AMOUNT_LABELS:
                if re.search(pat, ctx_after):
                    label = name
                    break
        cands.append({"type": "amount", "value": amt, "suggested_field": label,
                      "snippet": _snip(text, m.start(), m.end(), 50), "pos": m.start()})
    low = text.lower()
    if re.search(r"cancel+ed|cancellation of (?:your )?flight", low):
        notes.append("The text mentions a cancellation: choose 'Flight cancelled by the airline'.")
    elif re.search(r"delay", low):
        notes.append("The text mentions a delay: choose 'Flight delayed'.")
    m = re.search(NAMED_EXTRAORDINARY, low)
    if m:
        cands.append({"type": "bool", "value": True, "suggested_field": "extraordinary_claimed",
                      "snippet": _snip(text, m.start(), m.end()), "pos": m.start(),
                      "note": "A cause named in CAR 1.4 / 1.5 is cited. It can bar compensation only if beyond the airline's control and unavoidable; "
                              "it does not remove the refund or alternate-flight duty."})
    else:
        m = re.search(OPERATIONAL, low)
        if m:
            cands.append({"type": "bool", "value": False, "suggested_field": "extraordinary_claimed",
                          "snippet": _snip(text, m.start(), m.end()), "pos": m.start(),
                          "note": "The cause cited looks operational, which is not one of the circumstances named in CAR 1.4 / 1.5. Confirm."})
    cands.sort(key=lambda c: c["pos"])
    for c in cands:
        c.pop("pos")
    if not cands:
        notes.append("No dates, amounts or reasons were recognised. Enter the facts by hand.")
    return {"candidates": cands, "notes": notes, "assumption": "Times without an offset are read as India time (IST)."}
