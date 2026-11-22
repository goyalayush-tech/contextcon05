"""SQLite store: response cache, credit ledger and run settings.

Everything that must survive a crash lives here, so a restarted run resumes
from the cache instead of paying for the same Crustdata call twice.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    endpoint   TEXT NOT NULL,
    body       TEXT NOT NULL,
    response   TEXT NOT NULL,
    request_id TEXT,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    run_id     TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    key        TEXT NOT NULL,
    credits    REAL NOT NULL,
    estimated  INTEGER NOT NULL,   -- 1 when the header was missing and we used the price list
    cached     INTEGER NOT NULL,   -- 1 when served from cache (credits = 0)
    request_id TEXT,
    status     TEXT NOT NULL,      -- ok | error | blocked
    note       TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    ceiling    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    packet      TEXT NOT NULL,
    approval    TEXT NOT NULL DEFAULT 'awaiting_passenger_approval',
    approved_at REAL
);
CREATE TABLE IF NOT EXISTS followups (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    ts      REAL NOT NULL,
    dedupe  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    data    TEXT NOT NULL,
    UNIQUE(case_id, dedupe)
);
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leads (
    url       TEXT PRIMARY KEY,
    code      TEXT NOT NULL,
    title     TEXT NOT NULL,
    published TEXT,
    publisher TEXT,
    matched   TEXT NOT NULL,
    via       TEXT NOT NULL,
    seen_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_runs_seen (
    watch_id INTEGER NOT NULL,
    run_id   INTEGER NOT NULL,
    ts       REAL NOT NULL,
    PRIMARY KEY (watch_id, run_id)
);
CREATE TABLE IF NOT EXISTS airline_evidence (
    code         TEXT PRIMARY KEY,
    record       TEXT NOT NULL,
    retrieved_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str = "flightback.db"):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # -- cache ---------------------------------------------------------
    def cache_get(self, key: str, max_age_s: Optional[float]) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        if max_age_s is not None and time.time() - row["fetched_at"] > max_age_s:
            return None
        return {
            "response": json.loads(row["response"]),
            "request_id": row["request_id"],
            "fetched_at": row["fetched_at"],
        }

    def cache_put(self, key: str, endpoint: str, body: Any, response: Any, request_id: Optional[str]) -> float:
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?,?)",
                (key, endpoint, json.dumps(body, sort_keys=True), json.dumps(response), request_id, now),
            )
            self._db.commit()
        return now

    # -- ledger --------------------------------------------------------
    def ledger_add(self, run_id: str, endpoint: str, key: str, credits: float, *, estimated: bool,
                   cached: bool, request_id: Optional[str], status: str, note: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO ledger (ts,run_id,endpoint,key,credits,estimated,cached,request_id,status,note)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), run_id, endpoint, key, credits, int(estimated), int(cached), request_id, status, note),
            )
            self._db.commit()

    def spent(self, run_id: str) -> float:
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(credits),0) AS s FROM ledger WHERE run_id=? AND status='ok'", (run_id,)
            ).fetchone()
        return float(row["s"])

    def ledger_rows(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM ledger WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    # -- runs ----------------------------------------------------------
    def run_ensure(self, run_id: str, ceiling: float) -> float:
        """Create the run if new; return its (possibly previously cut) ceiling."""
        with self._lock:
            row = self._db.execute("SELECT ceiling FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row:
                return float(row["ceiling"])
            self._db.execute("INSERT INTO runs VALUES (?,?,?)", (run_id, time.time(), ceiling))
            self._db.commit()
            return ceiling

    def run_set_ceiling(self, run_id: str, ceiling: float) -> None:
        with self._lock:
            self._db.execute("UPDATE runs SET ceiling=? WHERE run_id=?", (ceiling, run_id))
            self._db.commit()

    def run_ceiling(self, run_id: str) -> float:
        with self._lock:
            row = self._db.execute("SELECT ceiling FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return float(row["ceiling"])

    # -- cases (idempotent: re-saving, re-approving or repeating a follow-up never duplicates) ------
    def case_save(self, case_id: str, packet: dict) -> None:
        with self._lock:
            row = self._db.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if row:
                self._db.execute("UPDATE cases SET packet=? WHERE case_id=?", (json.dumps(packet), case_id))
            else:
                self._db.execute("INSERT INTO cases (case_id, created_at, packet) VALUES (?,?,?)",
                                 (case_id, time.time(), json.dumps(packet)))
            self._db.commit()

    def case_get(self, case_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            return None
        packet = json.loads(row["packet"])
        packet["approval"] = {"state": row["approval"], "approved_at": row["approved_at"],
                              "note": "Nothing is ever sent by FLIGHTBACK. Submit manually through the airline or AirSewa."}
        packet["followups"] = self.followups(case_id)
        return packet

    def case_approve(self, case_id: str) -> bool:
        """Returns True only the first time; a repeat is a no-op."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE cases SET approval='approved_by_passenger', approved_at=? "
                "WHERE case_id=? AND approval!='approved_by_passenger'", (time.time(), case_id))
            self._db.commit()
            return cur.rowcount == 1

    def followup_add(self, case_id: str, kind: str, data: dict) -> bool:
        import hashlib
        dedupe = hashlib.sha256((kind + json.dumps(data, sort_keys=True)).encode()).hexdigest()[:16]
        with self._lock:
            try:
                self._db.execute("INSERT INTO followups (case_id, ts, dedupe, kind, data) VALUES (?,?,?,?,?)",
                                 (case_id, time.time(), dedupe, kind, json.dumps(data)))
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def followups(self, case_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM followups WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
        return [{"ts": r["ts"], "kind": r["kind"], "data": json.loads(r["data"])} for r in rows]

    # -- refreshed airline evidence -----------------------------------------------------------
    def evidence_put(self, code: str, record: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO airline_evidence VALUES (?,?,?)",
                             (code, json.dumps(record), time.time()))
            self._db.commit()

    def evidence_all(self) -> dict:
        with self._lock:
            rows = self._db.execute("SELECT code, record FROM airline_evidence").fetchall()
        return {r["code"]: json.loads(r["record"]) for r in rows}

    # -- settings, leads, watch bookkeeping ----------------------------------------------------
    def setting_get(self, k: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        return row["v"] if row else None

    def setting_put(self, k: str, v: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (k, v))
            self._db.commit()

    def leads_add(self, leads: list[dict]) -> int:
        """Insert new leads (one row per URL). Returns how many were new."""
        n = 0
        with self._lock:
            for l in leads:
                cur = self._db.execute(
                    "INSERT OR IGNORE INTO leads (url,code,title,published,publisher,matched,via,seen_at) VALUES (?,?,?,?,?,?,?,?)",
                    (l["url"], l["code"], l["title"], l["published"], l["publisher"], json.dumps(l["matched"]), l["via"], time.time()))
                n += cur.rowcount
            self._db.commit()
        return n

    def leads_for(self, code: str, limit: int = 5) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM leads WHERE code=? ORDER BY published DESC, seen_at DESC LIMIT ?",
                                    (code, limit)).fetchall()
        return [{"code": r["code"], "title": r["title"], "url": r["url"], "published": r["published"],
                 "publisher": r["publisher"], "matched": json.loads(r["matched"]), "via": r["via"],
                 "label": "LEAD, NOT PROOF"} for r in rows]

    def leads_count(self, code: str) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) c FROM leads WHERE code=?", (code,)).fetchone()["c"]

    def watch_run_seen(self, watch_id: int, run_id: int) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM watch_runs_seen WHERE watch_id=? AND run_id=?",
                                    (watch_id, run_id)).fetchone() is not None

    def watch_run_mark(self, watch_id: int, run_id: int) -> None:
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO watch_runs_seen VALUES (?,?,?)", (watch_id, run_id, time.time()))
            self._db.commit()
