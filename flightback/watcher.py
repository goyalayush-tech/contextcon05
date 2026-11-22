"""Crustdata Watcher integration (v2 entity watch on companies).

What the watch does: it tracks the six airlines' Crustdata company records and fires when a news item is ADDED.
New items arrive without us polling, are filtered into precedent leads (see leads.py) and are shown as
"lead, not proof".

What it does NOT do, so nobody oversells it: a company watch cannot see the contents of an airline's grievance
page. Contact changes on that page are caught by the Web Fetch hash check in evidence_run.py.

The watch is pull-only (no webhook): we read its runs with free GET calls. Crustdata bills 5 credits per change
notification on its side (the first baseline run is free), which is why the watch carries an expiry date.
"""
from __future__ import annotations

import os
from typing import Optional

from .airlines import SOURCES
from .crustdata import Crustdata, CrustdataError
from .leads import extract_leads
from .store import Store

SETTING = "watch_id"
EXPIRES_AT = os.environ.get("FLIGHTBACK_WATCH_EXPIRES", "2026-11-30")


def watch_body() -> dict:
    return {"entities": {"domains": [s["domain"] for s in SOURCES.values()]},
            "track": {"field": "news", "type": "added"},
            "fields": ["basic_info", "news"],
            "config": {"trigger": {"type": "interval", "every_hours": 24}, "max_results_per_run": 25,
                       "preferred_hour": 4, "expires_at": EXPIRES_AT},
            "notifications": []}


def watch_id(store: Store) -> Optional[int]:
    v = os.environ.get("FLIGHTBACK_WATCH_ID") or store.setting_get(SETTING)
    return int(v) if v else None


def ensure_watch(cd: Crustdata, store: Store, create: bool = False) -> Optional[int]:
    """Return the watch id. Creates the watch only when create=True and none is recorded (creation is free)."""
    wid = watch_id(store)
    if wid or not create:
        return wid
    res = cd.post("/watch/company", watch_body(), use_cache=False)
    wid = int(res.data["id"])
    store.setting_put(SETTING, str(wid))
    return wid


def status(cd: Crustdata, wid: int) -> dict:
    w = cd.get(f"/watch/{wid}").data
    runs = cd.get(f"/watch/{wid}/runs?limit=10").data
    rl = runs.get("runs", [])
    return {"id": wid, "status": w.get("status"), "tracks": w.get("track"), "entities": len(w["entities"]["domains"])
            if w.get("entities") else None, "expires_at": (w.get("config") or {}).get("expires_at"),
            "last_run_at": w.get("last_run_at"), "notifications_count": w.get("notifications_count"),
            "credits_consumed": w.get("credits_consumed"), "runs": [
                {"id": r["id"], "started_at": r["started_at"], "status": r["status"], "new_records": r["new_records_count"],
                 "credits_deducted": r["credits_deducted"]} for r in rl]}


def sync(cd: Crustdata, store: Store, code_by_company_id: dict[int, str], max_runs: int = 4) -> dict:
    """Read watch runs we have not seen, turn their news items into leads. Free: GET only."""
    wid = watch_id(store)
    if not wid:
        return {"status": "no_watch", "detail": "No watch is recorded. Create it first."}
    runs = cd.get(f"/watch/{wid}/runs?limit={max_runs}").data.get("runs", [])
    out = {"status": "ok", "watch_id": wid, "runs_read": 0, "records": 0, "leads_new": 0, "skipped_failed_runs": 0}
    for r in reversed(runs):  # oldest first
        if store.watch_run_seen(wid, r["id"]):
            continue
        if r["status"] != "SUCCESS":
            out["skipped_failed_runs"] += 1  # not marked seen, so a later sync tries again
            continue
        summ = cd.get(f"/watch/{wid}/runs/{r['id']}/summary?max_records=100").data
        for note in summ.get("notifications") or []:
            for item in (note.get("payload") or {}).get("notifications", []):
                rec = item.get("record") or {}
                code = code_by_company_id.get(rec.get("crustdata_company_id"))
                if not code:
                    continue  # a company we cannot map to an airline code is ignored, never guessed
                out["records"] += 1
                out["leads_new"] += store.leads_add(extract_leads(rec.get("news"), code, f"watch {wid} run {r['id']}"))
        store.watch_run_mark(wid, r["id"])
        out["runs_read"] += 1
    return out


__all__ = ["watch_body", "ensure_watch", "status", "sync", "watch_id", "CrustdataError"]
