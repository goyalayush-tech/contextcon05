"""Airline evidence refresh through Crustdata.

Three rules learned from the live probes:
  * Web Fetch can return success=true with http_status 403: trust http_status, not success.
  * Web Fetch returns empty content for PDFs and script-only pages: that is "cannot verify", not "no data".
  * Officer names differ between pages of the same airline; email addresses and the retrieval time are what we quote.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from .crustdata import BudgetExceeded, Crustdata, CrustdataError

IST = timezone(timedelta(hours=5, minutes=30))
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

SOURCES = {
    "6E": {"domain": "goindigo.in", "grievance_url": "https://www.goindigo.in/contact-us.html"},
    "AI": {"domain": "airindia.com", "grievance_url": "https://www.airindia.com/in/en/contact-us/grievance-resolution.html"},
    "QP": {"domain": "akasaair.com", "grievance_url": "https://www.akasaair.com/customer-support/grievance-redressal-process"},
    "IX": {"domain": "airindiaexpress.com", "grievance_url": None},
    "SG": {"domain": "spicejet.com", "grievance_url": None},
    "9I": {"domain": "allianceair.in", "grievance_url": None},
}


def extract_passage(text: str, before: int = 250, after: int = 900) -> Optional[str]:
    """Keep only the part of a long page that talks about the grievance officers."""
    m = re.search(r"nodal\s+officer", text, re.I)
    if not m:
        return None
    chunk = text[max(0, m.start() - before): m.end() + after]
    return re.sub(r"[ \t]*\n[ \t\n]*", "\n", chunk).strip()


def extract_contacts(passage: str) -> dict:
    emails = list(dict.fromkeys(EMAIL.findall(passage)))
    out = {}
    for e in emails:
        low = e.lower()
        if "nodal" in low:
            out["nodal_officer_email"] = e
        elif "appellate" in low:
            out["appellate_authority_email"] = e
    return out


def refresh_airline(cd: Crustdata, code: str, snapshot: dict) -> dict:
    """Re-collect identity and grievance route for one airline. Never raises for data problems; returns a status."""
    src = SOURCES.get(code)
    if not src:
        return {"code": code, "status": "unknown_airline"}
    result: dict = {"code": code, "status": "refreshed", "identity": None, "grievance": None, "changes": [], "credits": 0.0}
    spent_before = cd.spent
    try:
        ident = cd.post("/company/identify", {"domains": [src["domain"]]})
        match = None
        for block in ident.data or []:
            for m in block.get("matches", []):
                match = m
                break
        if match and match["confidence_score"] >= 0.9 and match["company_data"]["basic_info"]["primary_domain"] == src["domain"]:
            bi = match["company_data"]["basic_info"]
            result["identity"] = {"endpoint": "/company/identify", "matched_on": src["domain"], "match_type": "domain",
                                  "confidence": match["confidence_score"], "crustdata_company_id": bi["crustdata_company_id"],
                                  "name": bi["name"], "primary_domain": bi["primary_domain"],
                                  "retrieved_on": datetime.now(IST).date().isoformat()}
        else:
            result["identity"] = {"status": "REVIEW_REQUIRED", "detail": "No confident domain match."}

        if not src["grievance_url"]:
            result["grievance"] = {"status": "not_collected", "detail": "No grievance page configured for this airline."}
        else:
            page = cd.post("/web/enrich/live", {"urls": [src["grievance_url"]]})
            item = next((i for i in (page.data or []) if i.get("url") == src["grievance_url"]), None)
            base = {"source_url": src["grievance_url"], "retrieved_via": "Crustdata /web/enrich/live"}
            if item is None:
                result["grievance"] = {**base, "status": "unverifiable", "detail": "No entry returned for the URL."}
            else:
                retrieved = datetime.fromtimestamp(item["timestamp"], IST).isoformat(timespec="seconds") \
                    if item.get("timestamp") else datetime.now(IST).isoformat(timespec="seconds")
                base.update({"http_status": item.get("http_status"), "retrieved_at": retrieved})
                if item.get("http_status") != 200:
                    result["grievance"] = {**base, "status": "primary_blocked",
                                           "detail": f"Crustdata success={item.get('success')} but the site returned "
                                                     f"HTTP {item.get('http_status')}. No primary text captured.",
                                           "status_for_packet": "CANNOT VERIFY from primary source. Check the airline's website."}
                elif not (item.get("content") or "").strip():
                    result["grievance"] = {**base, "status": "unverifiable",
                                           "detail": "Page returned no text (PDF or script-rendered page).",
                                           "status_for_packet": "CANNOT VERIFY from primary source."}
                else:
                    passage = extract_passage(item["content"])
                    contacts = extract_contacts(passage) if passage else {}
                    if not passage or not contacts:
                        result["grievance"] = {**base, "status": "unverifiable",
                                               "detail": "Page fetched but no nodal officer / appellate authority emails found.",
                                               "status_for_packet": "CANNOT VERIFY from primary source."}
                    else:
                        result["grievance"] = {**base, "status": "primary_verified", "passage": passage,
                                               "passage_sha256": hashlib.sha256(passage.encode()).hexdigest(),
                                               "contacts": contacts}
                        old = (snapshot.get("grievance") or {}).get("contacts", {})
                        for k, v in contacts.items():
                            if old.get(k) and old[k].lower() != v.lower():
                                result["changes"].append(f"{k} changed: {old[k]} -> {v}")
    except BudgetExceeded as e:
        result.update(status="budget_exceeded", detail=str(e))
    except CrustdataError as e:
        result.update(status="error", detail=str(e))
    result["credits"] = round(cd.spent - spent_before, 4)
    return result
