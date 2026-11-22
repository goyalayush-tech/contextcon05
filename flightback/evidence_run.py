"""Per-case evidence run: re-check the operating airline's identity and grievance route with Crustdata while the case
is built, under that case's own credit ceiling, and say plainly how fresh the result is.

Outcomes (mode):
  live            at least one call went to Crustdata and the grievance page was re-read now
  cached          every call was answered from the 24h cache (0 credits, still a live-sourced page)
  stale_snapshot  the live check could not verify (blocked, empty, budget, network); the dated snapshot is used and labelled
  snapshot_only   no API key, or the airline has no live source configured

Only a live-verified page may replace the snapshot's contacts. A failed check never erases verified contacts.
"""
from __future__ import annotations

import copy
from typing import Optional

from .airlines import SOURCES, refresh_airline
from .crustdata import Crustdata


def run_for_case(cd: Crustdata, code: str, snapshot: dict) -> tuple[dict, dict]:
    """Returns (evidence_run block for the packet, airline record to use for the packet)."""
    snap_g = snapshot.get("grievance") or {}
    block: dict = {"run_id": cd.run_id, "ceiling": cd.ceiling, "airline": code,
                   "snapshot_retrieved_at": snap_g.get("retrieved_at")}
    before = len(cd.store.ledger_rows(cd.run_id))  # a re-assessed case keeps one ledger; show only this run's calls
    result = refresh_airline(cd, code, snapshot)
    rows = cd.store.ledger_rows(cd.run_id)[before:]
    block["calls"] = [{"endpoint": r["endpoint"], "credits": r["credits"], "cached": bool(r["cached"]),
                       "status": r["status"], "request_id": r["request_id"], "note": r["note"]} for r in rows]
    block["spent"], block["remaining"] = cd.spent, cd.remaining
    g = result.get("grievance") or {}
    record = copy.deepcopy(snapshot)

    if result["status"] != "refreshed":
        block.update(mode="stale_snapshot", reason=f"{result['status']}: {result.get('detail', '')}".strip(": "),
                     contacts_changed=False)
        return block, record

    if g.get("status") != "primary_verified":
        block.update(mode="stale_snapshot", contacts_changed=False,
                     reason=f"{g.get('status')}. {g.get('detail', '')}".strip())
        return block, record

    all_cached = bool(rows) and all(r["cached"] for r in rows if r["status"] == "ok")
    new_sha, old_sha = g.get("passage_sha256"), snap_g.get("passage_sha256")
    block.update(mode="cached" if all_cached else "live", live_retrieved_at=g.get("retrieved_at"),
                 live_http_status=g.get("http_status"), live_passage_sha256=new_sha, snapshot_passage_sha256=old_sha,
                 passage_changed=(new_sha != old_sha) if old_sha else None,
                 changes=result["changes"], contacts_changed=bool(result["changes"]))
    record["grievance"] = {**snap_g, **g}
    if result.get("identity") and "crustdata_company_id" in result["identity"]:
        record["identity"] = {**snapshot.get("identity", {}), **result["identity"]}
    return block, record


def snapshot_only(code: Optional[str], reason: str) -> dict:
    return {"mode": "snapshot_only", "airline": code, "reason": reason, "contacts_changed": False, "calls": [],
            "spent": 0.0}


def has_live_source(code: Optional[str]) -> bool:
    return bool(code and code in SOURCES and SOURCES[code].get("grievance_url"))
