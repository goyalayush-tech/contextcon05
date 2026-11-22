"""FLIGHTBACK web API. Run: .venv/bin/uvicorn flightback.app:app --reload"""
from __future__ import annotations

import copy
import json
import os
import typing
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .env import load_env

load_env()

from .airlines import SOURCES, refresh_airline
from .crustdata import Crustdata
from .extract import suggest
from .packet import KINDS, build_case, jsonable, load_evidence
from .rules import PART_II, PART_IV
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
store = Store(os.environ.get("FLIGHTBACK_DB", str(ROOT / "flightback.db")))
app = FastAPI(title="FLIGHTBACK", description="Passenger disruption recovery: evidence-backed cases, never auto-sent.")
RUN_ID = "airline-refresh"
CEILING = float(os.environ.get("FLIGHTBACK_CREDIT_CEILING", "20"))
SAMPLES = {k: v for k, v in json.loads((ROOT / "data" / "samples.json").read_text()).items() if not k.startswith("_")}

ENUMS = {"initiated_by": ["airline", "passenger"], "payment_mode": ["credit_card", "cash", "agent_portal", "other"]}
HINTS = {"basic_fare": "Booked one-way basic fare, not the total ticket value",
         "fuel_charge": "Airline fuel charge from the fare break-up",
         "block_time_hours": "Gate-to-gate flight time in hours",
         "alt_or_refund_offered": "Did the airline offer an alternate flight or refund?",
         "contact_info_provided": "Email id or phone number given at booking",
         "extraordinary_claimed": "Did the airline cite weather, ATC, strike, etc.?",
         "statutory_fees": "Statutory taxes plus UDF/ADF/PSF from the fare break-up"}


def evidence() -> dict:
    """Snapshot, overlaid with anything refreshed live through Crustdata."""
    ev = copy.deepcopy(load_evidence())
    for code, rec in store.evidence_all().items():
        if code in ev["airlines"]:
            ev["airlines"][code].update(rec)
    return ev


_cd: Optional[Crustdata] = None


def crustdata() -> Crustdata:
    global _cd
    if not os.environ.get("CRUSTDATA_API_KEY"):
        raise HTTPException(503, "CRUSTDATA_API_KEY is not set. The app is replaying the committed evidence snapshot.")
    if _cd is None:
        _cd = Crustdata(store, RUN_ID, CEILING)
    return _cd


def _ftype(tp: Any) -> str:
    args = [a for a in typing.get_args(tp) if a is not type(None)] or [tp]
    t = args[0]
    if t is datetime:
        return "datetime"
    if t is date:
        return "date"
    if t is bool:
        return "bool"
    if t is str:
        return "text"
    return "number"


@app.get("/api/health")
def health():
    cd = _cd
    return {"crustdata_key_present": bool(os.environ.get("CRUSTDATA_API_KEY")), "ceiling": cd.ceiling if cd else CEILING,
            "spent": cd.spent if cd else store.spent(RUN_ID)}


@app.get("/api/schema")
def schema():
    out = {}
    for kind, (cls, _) in KINDS.items():
        hints = typing.get_type_hints(cls)
        out[kind] = [{"name": f.name, "label": f.name.replace("_", " "), "type": "enum" if f.name in ENUMS else _ftype(hints[f.name]),
                      "options": ENUMS.get(f.name), "hint": HINTS.get(f.name)} for f in fields(cls) if f.name != "domestic"]
    return out


@app.get("/api/samples")
def samples():
    return [{"key": k, "title": v["title"], "case_type": v["case_type"]} for k, v in SAMPLES.items()]


@app.get("/api/samples/{key}")
def sample(key: str):
    if key not in SAMPLES:
        raise HTTPException(404, "unknown sample")
    return {k: v for k, v in SAMPLES[key].items() if k not in ("expect", "title")}


@app.post("/api/extract")
def extract(body: dict = Body(...)):
    text = str(body.get("text", ""))
    if len(text) > 20000:
        raise HTTPException(413, "Paste at most 20,000 characters")
    return suggest(text)


@app.get("/api/rules")
def rules():
    return [jsonable(PART_IV), jsonable(PART_II)]


@app.get("/api/airlines")
def airlines():
    ev = evidence()
    return [{"code": c, "airline": r["airline"], "identity": r["identity"], "grievance_status": r["grievance"]["status"],
             "retrieved_at": r["grievance"].get("retrieved_at")} for c, r in ev["airlines"].items()]


@app.post("/api/case")
def create_case(payload: dict = Body(...)):
    try:
        packet = build_case(payload, evidence())
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    store.case_save(packet["case_id"], packet)
    return store.case_get(packet["case_id"])


@app.get("/api/case/{case_id}")
def get_case(case_id: str):
    c = store.case_get(case_id)
    if not c:
        raise HTTPException(404, "unknown case")
    return c


@app.post("/api/case/{case_id}/approve")
def approve(case_id: str):
    if not store.case_get(case_id):
        raise HTTPException(404, "unknown case")
    first = store.case_approve(case_id)
    return {"approved": True, "first_time": first, "sent": False,
            "note": "Approval records your consent only. FLIGHTBACK never sends anything; submit through the airline or AirSewa."}


def next_step(case: dict) -> str:
    fu = case.get("followups", [])
    kinds = [f["kind"] for f in fu]
    route = case["escalation"]
    if "refund_received" in kinds:
        got = [f for f in fu if f["kind"] == "refund_received"][-1]["data"].get("amount")
        exp = (case.get("amounts") or {}).get("expected_refund")
        if got is not None and exp is not None and float(got) < float(exp):
            return f"Refund received is Rs {float(exp) - float(got):.2f} below the expected Rs {exp}. Ask the airline to explain the deduction in writing, then escalate."
        return "Refund received. If it matches your expected amount, the case can be closed."
    rejections = [f for f in fu if f["kind"] == "airline_rejection"]
    if rejections:
        reason = str(rejections[-1]["data"].get("reason", "")).lower()
        level = min(len(rejections) + 1, len(route))
        who = route[level - 1]
        extra = ""
        if any(w in reason for w in ("extraordinary", "weather", "atc", "air traffic", "strike", "security")):
            extra = " The airline cited an extraordinary circumstance: ask for the records supporting it (CAR 1.4, 1.5). It bars compensation only, not the refund or alternate-flight duty."
        return f"Escalate to {who['to']} ({who['how']}), quoting the airline's reference number and its rejection.{extra}"
    if "complaint_submitted" in kinds and "airline_response" not in kinds:
        return f"No airline response recorded. Check the response time in the airline's passenger charter; if it has passed, escalate to {route[1]['to'] if len(route) > 1 else 'AirSewa'}."
    if "airline_response" in kinds:
        return "Record whether the response resolves the complaint. If not, log the rejection reason so the next escalation can address it."
    if case["approval"]["state"] != "approved_by_passenger":
        return "Review the facts and the draft, then approve. Approval does not send anything."
    return f"Submit the approved complaint manually via {route[0]['to']} ({route[0]['how']}) and record the reference number here."


@app.post("/api/case/{case_id}/followup")
def followup(case_id: str, body: dict = Body(...)):
    case = store.case_get(case_id)
    if not case:
        raise HTTPException(404, "unknown case")
    kind = body.get("kind")
    if kind not in ("complaint_submitted", "airline_response", "airline_rejection", "refund_received"):
        raise HTTPException(422, "kind must be complaint_submitted, airline_response, airline_rejection or refund_received")
    added = store.followup_add(case_id, kind, body.get("data", {}))
    case = store.case_get(case_id)
    return {"recorded": added, "duplicate_ignored": not added, "next_step": next_step(case), "followups": case["followups"]}


@app.post("/api/airline/{code}/refresh")
def refresh(code: str):
    if code not in SOURCES:
        raise HTTPException(404, "unknown airline code")
    cd = crustdata()
    snap = evidence()["airlines"][code]
    result = refresh_airline(cd, code, snap)
    if result["status"] == "refreshed" and result.get("grievance"):
        update = {"grievance": {**snap["grievance"], **result["grievance"]}}
        if result.get("identity") and "crustdata_company_id" in result["identity"]:
            update["identity"] = {**snap["identity"], **result["identity"]}
        if result["grievance"]["status"] in ("primary_verified", "primary_blocked", "unverifiable"):
            store.evidence_put(code, update)
    return {**result, "ceiling": cd.ceiling, "spent": cd.spent, "remaining": cd.remaining}


@app.get("/api/crustdata/ledger")
def ledger():
    cd = _cd
    return {"ceiling": cd.ceiling if cd else CEILING, "spent": cd.spent if cd else store.spent(RUN_ID),
            "rows": store.ledger_rows(RUN_ID)[-50:], "rate_limits_per_minute": {"core": 5, "web": 10}}


@app.post("/api/crustdata/ceiling")
def set_ceiling(body: dict = Body(...)):
    cd = crustdata()
    new = float(body["ceiling"])
    cd.cut_budget(new)
    return {"ceiling": cd.ceiling, "spent": cd.spent, "remaining": cd.remaining}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
