"""FLIGHTBACK web API. Run: .venv/bin/uvicorn flightback.app:app --reload"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import typing
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .env import load_env

load_env()

from . import documents, watcher
from .airlines import SOURCES, merge_grievance, refresh_airline
from .crustdata import RATE_LIMITS, Crustdata, CrustdataError, RateLimiter
from .evidence_run import has_live_source, run_for_case, snapshot_only
from .extract import suggest
from .leads import fetch_company_news, extract_leads
from .packet import KINDS, build_case, jsonable, load_evidence
from .rules import PART_II, PART_IV
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
store = Store(os.environ.get("FLIGHTBACK_DB", str(ROOT / "flightback.db")))
app = FastAPI(title="FLIGHTBACK", description="Passenger disruption recovery: evidence-backed cases, never auto-sent.")
RUN_ID = "airline-refresh"
CEILING = float(os.environ.get("FLIGHTBACK_CREDIT_CEILING", "20"))
CASE_CEILING = float(os.environ.get("FLIGHTBACK_CASE_CEILING", "3"))   # credits one case may spend on its evidence run
FRESH_HOURS = 72   # an airline record older than this is shown as stale on the freshness board
LIMITER = RateLimiter(RATE_LIMITS)   # one limiter for every client: the key's rate limit is shared
SAMPLES = {k: v for k, v in json.loads((ROOT / "data" / "samples.json").read_text()).items() if not k.startswith("_")}

ENUMS = {"initiated_by": ["airline", "passenger"], "payment_mode": ["credit_card", "cash", "agent_portal", "other"]}
HINTS = {"basic_fare": "Booked one-way basic fare, not the total ticket value",
         "fuel_charge": "Airline fuel charge from the fare break-up",
         "block_time_hours": "Gate-to-gate flight time in hours",
         "alt_or_refund_offered": "Did the airline offer an alternate flight or refund?",
         "contact_info_provided": "Email id or phone number given at booking",
         "extraordinary_claimed": "Did the airline cite weather, ATC, strike, etc.?",
         "reported_at_airport": "Were you already at the airport for the original flight?",
         "statutory_fees": "Statutory taxes plus UDF/ADF/PSF from the fare break-up"}


def evidence() -> dict:
    """Snapshot, overlaid with anything refreshed live through Crustdata."""
    ev = copy.deepcopy(load_evidence())
    for code, rec in store.evidence_all().items():
        if code in ev["airlines"]:
            cur = ev["airlines"][code]
            if "grievance" in rec:  # contacts merge key by key, so a stored refresh never hides snapshot contacts
                rec = {**rec, "grievance": merge_grievance(cur.get("grievance"), rec["grievance"])}
            cur.update(rec)
    return ev


_cd: Optional[Crustdata] = None


def crustdata() -> Crustdata:
    global _cd
    if not os.environ.get("CRUSTDATA_API_KEY"):
        raise HTTPException(503, "CRUSTDATA_API_KEY is not set. The app is replaying the committed evidence snapshot.")
    if _cd is None:
        _cd = Crustdata(store, RUN_ID, CEILING, limiter=LIMITER)
    return _cd


def case_client(case_id: str) -> Crustdata:
    """Each case gets its own run, ledger and credit ceiling; calls are cached across cases."""
    return Crustdata(store, f"case:{case_id}", CASE_CEILING, limiter=LIMITER)


def company_codes() -> dict:
    return {r["identity"]["crustdata_company_id"]: c for c, r in evidence()["airlines"].items()
            if r.get("identity", {}).get("crustdata_company_id")}


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


@app.get("/api/documents/capabilities")
def document_capabilities():
    """Whether this server can OCR scans and photos, or only read PDFs that have a text layer."""
    return documents.capabilities()


@app.post("/api/documents")
def upload_document(file: UploadFile = File(...)):
    """Read an e-ticket, airline email (as PDF) or screenshot: text layer first, OCR for scans and images. Returns
    fact suggestions with page, quote, method and confidence. The file is not stored; only its SHA-256 is returned."""
    data = file.file.read(documents.MAX_BYTES + 1)  # read one byte past the limit to detect oversize files
    try:
        return documents.suggest_from_document(file.filename or "uploaded document", data)
    except documents.DocumentError as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/rules")
def rules():
    return [jsonable(PART_IV), jsonable(PART_II)]


@app.get("/api/airlines")
def airlines():
    ev = evidence()
    return [{"code": c, "airline": r["airline"], "identity": r["identity"], "grievance_status": r["grievance"]["status"],
             "retrieved_at": r["grievance"].get("retrieved_at")} for c, r in ev["airlines"].items()]


@app.post("/api/case")
def create_case(payload: dict = Body(...), live: bool = True):
    """Build the case packet. With a Crustdata key and live=true, the operating airline's page is re-checked first,
    under this case's own credit ceiling; otherwise (or on any failure) the dated snapshot is used and labelled."""
    ev = evidence()
    try:
        packet = build_case(payload, ev)  # also validates the payload before any credits are spent
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    code = packet["airline"]["code"]
    run = None
    if code and code in ev["airlines"]:
        if not live:
            run = snapshot_only(code, "Live check switched off for this request.")
        elif not os.environ.get("CRUSTDATA_API_KEY"):
            run = snapshot_only(code, "No Crustdata key: replaying the dated snapshot.")
        elif not has_live_source(code):
            run = snapshot_only(code, "No live source is configured for this airline; identity only.")
        else:
            run, record = run_for_case(case_client(packet["case_id"]), code, ev["airlines"][code])
            ev = {**ev, "airlines": {**ev["airlines"], code: record}}
    packet = build_case(payload, ev, evidence_run=run, leads=store.leads_for(code) if code else [])
    store.case_save(packet["case_id"], packet)
    return load_case(packet["case_id"])


def load_case(case_id: str) -> dict:
    """The stored case as the UI needs it: packet, approval, follow-ups and the advised next step."""
    c = store.case_get(case_id)
    if not c:
        raise HTTPException(404, "unknown case")
    c["next_step"] = next_step(c)
    return c


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@app.get("/api/cases")
def list_cases(limit: int = 20):
    """Recent cases, newest first, for the case list."""
    return store.cases_list(max(1, min(limit, 100)))


@app.get("/api/case/{case_id}")
def get_case(case_id: str):
    return load_case(case_id)


@app.put("/api/case/{case_id}/draft")
def save_draft(case_id: str, body: dict = Body(...)):
    """Save the passenger's edits to the complaint draft. `text: null` restores the generated draft. Approval covers
    one exact text, so changing an approved draft withdraws the approval until the passenger approves again."""
    case = load_case(case_id)
    text = body.get("text")
    if text is not None:
        text = str(text)
        if not text.strip():
            raise HTTPException(422, "The draft cannot be empty. Restore the generated draft instead.")
        if len(text) > 20000:
            raise HTTPException(413, "The draft can be at most 20,000 characters.")
        if text == case["generated_draft"]:
            text = None  # identical to the generated draft: store nothing
    effective = text if text is not None else case["generated_draft"]
    revoked = store.case_set_draft(case_id, text, _sha(effective))
    out = load_case(case_id)
    out["approval_withdrawn"] = revoked
    return out


@app.post("/api/case/{case_id}/approve")
def approve(case_id: str, body: dict = Body(default={})):
    case = store.case_get(case_id)
    if not case:
        raise HTTPException(404, "unknown case")
    run = case.get("evidence_run") or {}
    if run.get("contacts_changed") and not body.get("acknowledge_contact_change"):
        raise HTTPException(409, "The airline's contact details changed since the snapshot: "
                                 + "; ".join(run.get("changes", [])) + ". Confirm them on the airline's website, then "
                                 "approve again with acknowledge_contact_change=true.")
    first = store.case_approve(case_id, _sha(case["complaint_draft"]))
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
    case = load_case(case_id)
    return {"recorded": added, "duplicate_ignored": not added, "next_step": case["next_step"], "followups": case["followups"]}


@app.post("/api/airline/{code}/refresh")
def refresh(code: str):
    if code not in SOURCES:
        raise HTTPException(404, "unknown airline code")
    cd = crustdata()
    snap = evidence()["airlines"][code]
    result = refresh_airline(cd, code, snap)
    if result["status"] == "refreshed" and result.get("grievance"):
        update = {"grievance": merge_grievance(snap["grievance"], result["grievance"])}
        if result.get("identity") and "crustdata_company_id" in result["identity"]:
            update["identity"] = {**snap["identity"], **result["identity"]}
        if result["grievance"]["status"] in ("primary_verified", "primary_blocked", "unverifiable"):
            store.evidence_put(code, update)
    return {**result, "ceiling": cd.ceiling, "spent": cd.spent, "remaining": cd.remaining}


def _watch_client() -> Crustdata:
    return crustdata()


@app.post("/api/watch/ensure")
def watch_ensure():
    """Create the airline news watch if none is recorded (free); otherwise return the existing one."""
    cd = _watch_client()
    return {"watch_id": watcher.ensure_watch(cd, store, create=True)}


@app.get("/api/watch")
def watch_status():
    cd = _watch_client()
    wid = watcher.watch_id(store)
    if not wid:
        return {"watch_id": None, "detail": "No watch yet. POST /api/watch/ensure creates it (free)."}
    try:
        return watcher.status(cd, wid)
    except CrustdataError as e:
        raise HTTPException(502, str(e))


@app.post("/api/watch/sync")
def watch_sync():
    cd = _watch_client()
    try:
        return watcher.sync(cd, store, company_codes())
    except CrustdataError as e:
        raise HTTPException(502, str(e))


@app.post("/api/leads/{code}/refresh")
def leads_refresh(code: str):
    """On-demand news fetch for one airline (about 2 credits, cached 24h, shared by every passenger)."""
    ev = evidence()["airlines"]
    if code not in ev:
        raise HTTPException(404, "unknown airline code")
    cd = crustdata()
    try:
        news = fetch_company_news(cd, ev[code]["identity"]["crustdata_company_id"])
    except CrustdataError as e:
        raise HTTPException(502, str(e))
    new = store.leads_add(extract_leads(news, code, "company enrich news"))
    return {"code": code, "news_items": len(news), "leads_new": new, "leads_total": store.leads_count(code),
            "spent": cd.spent, "remaining": cd.remaining}


@app.get("/api/leads")
def leads_latest(limit: int = 8):
    """Newest precedent leads across airlines. Every item is labelled LEAD, NOT PROOF."""
    return {"label": "LEAD, NOT PROOF", "items": store.leads_latest(max(1, min(limit, 50)))}


@app.get("/api/freshness")
def freshness():
    """One row per airline: how old the evidence is, what is verified, how many leads, plus the watch."""
    now = datetime.now().astimezone()
    rows = []
    for code, r in evidence()["airlines"].items():
        g = r["grievance"]
        ts = g.get("retrieved_at")
        age = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                age = round((now - (dt if dt.tzinfo else dt.astimezone())).total_seconds() / 3600, 1)
            except ValueError:
                age = None
        rows.append({"code": code, "airline": r["airline"], "grievance_status": g["status"], "retrieved_at": ts,
                     "age_hours": age, "stale": age is None or age > FRESH_HOURS,
                     "has_live_source": has_live_source(code), "leads": store.leads_count(code)})
    return {"fresh_within_hours": FRESH_HOURS, "airlines": rows, "watch_id": watcher.watch_id(store),
            "case_ceiling": CASE_CEILING}


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


DIST = STATIC / "dist"  # the React build: cd frontend && npm run build


def _ui_missing() -> HTMLResponse:
    return HTMLResponse("<h1>FLIGHTBACK</h1><p>The web UI is not built. Run <code>cd frontend && npm install && "
                        "npm run build</code>, then reload. The API is available under <code>/api</code>.</p>", 503)


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
if (DIST / "fonts").is_dir():
    app.mount("/fonts", StaticFiles(directory=DIST / "fonts"), name="fonts")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Serve the web app for every page URL (/, /new, /cases, /case/FB-..., /sources); unknown /api paths stay 404."""
    if path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    file = (DIST / path).resolve()
    if path and file.is_file() and DIST.resolve() in file.parents:  # top-level files such as favicon.svg
        return FileResponse(file)
    index = DIST / "index.html"
    return FileResponse(index) if index.is_file() else _ui_missing()
