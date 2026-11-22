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
