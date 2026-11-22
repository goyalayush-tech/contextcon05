"""Crustdata client: rate limits, cache, credit ceiling and ledger in one place.

Design rules (from the ContextCon handbook):
  * every run has a credit ceiling that can be cut mid-run, and the ceiling is stored
    in SQLite so it survives a crash;
  * every call lands in a ledger with the request id and credits used;
  * identical requests are answered from cache, so resuming a run never pays twice;
  * 429 -> wait for x-ratelimit-reset; 402 -> credits exhausted; 403 -> endpoint disabled.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .store import Store

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"

# Limits observed on the ContextCon key (requests per minute), by endpoint group.
RATE_LIMITS = {"core": 5, "web": 10, "social": 100, "autocomplete": 300}

# Price list from /account credit costs (credits). Used for pre-flight checks only;
# the ledger records the real X-Credits-Used header when the API sends it.
PER_RESULT = 0.03


class BudgetExceeded(Exception):
    """The next call would push the run past its credit ceiling."""


class CreditsExhausted(Exception):
    """HTTP 402 from Crustdata: the account itself is out of credits."""


class EndpointDisabled(Exception):
    """HTTP 403: this endpoint is not enabled on the key."""


class CrustdataError(Exception):
    pass


def endpoint_group(path: str) -> str:
    if "autocomplete" in path:
        return "autocomplete"
    if path.startswith("/web/"):
        return "web"
    if "social" in path:
        return "social"
    return "core"


def estimate_cost(path: str, body: dict) -> float:
    """Upper-bound estimate in credits, used before the call is made."""
    if path.endswith("/autocomplete"):
        return 0.0
    if path in ("/job/search", "/company/search", "/person/search"):
        return round(float(body.get("limit", 20)) * PER_RESULT, 4)
    if path == "/company/enrich":
        return 2.0 + (2.0 if "technographics" in json.dumps(body) else 0.0)
    if path == "/person/enrich":
        return 1.0
    if path == "/person/identify":
        return 1.0 * max(1, len(body.get("identifiers", []) or [1]))
    if path == "/company/identify":
        return 0.2 * max(1, len(body.get("names", []) or body.get("domains", []) or [1]))
    if path.startswith("/web/"):
        return 1.0 * max(1, len(body.get("urls", []) or [1]))
    return 1.0  # unknown endpoint: assume 1 credit, never 0


@dataclass
class Result:
    data: Any
    cached: bool
    credits: float
    fetched_at: float
    request_id: Optional[str]


class RateLimiter:
    """Sliding one-minute window per endpoint group."""

    def __init__(self, limits: dict[str, int], clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.limits, self.clock, self.sleep = limits, clock, sleep
        self._hits: dict[str, deque] = {g: deque() for g in limits}

    def acquire(self, group: str) -> float:
        """Block until a slot is free; return seconds waited."""
        limit = self.limits.get(group, self.limits["core"])
        hits = self._hits.setdefault(group, deque())
        waited = 0.0
        while True:
            now = self.clock()
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) < limit:
                hits.append(now)
                return waited
            wait = 60 - (now - hits[0]) + 0.05
            self.sleep(wait)
            waited += wait


def _http_post(url: str, headers: dict, body: dict, timeout: float = 60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw[:500].decode("utf-8", "replace")}
        return e.code, dict(e.headers), payload


class Crustdata:
    def __init__(self, store: Store, run_id: str, ceiling: float, api_key: Optional[str] = None,
                 transport: Callable = _http_post, limiter: Optional[RateLimiter] = None,
                 cache_ttl_s: Optional[float] = 24 * 3600):
        self.store, self.run_id = store, run_id
        self.api_key = api_key or os.environ.get("CRUSTDATA_API_KEY", "")
        self.transport = transport
        self.limiter = limiter or RateLimiter(RATE_LIMITS)
        self.cache_ttl_s = cache_ttl_s
        # a resumed run keeps its (possibly already cut) ceiling
        self.store.run_ensure(run_id, ceiling)

    # -- budget --------------------------------------------------------
    @property
    def ceiling(self) -> float:
        return self.store.run_ceiling(self.run_id)

    def cut_budget(self, new_ceiling: float) -> None:
        self.store.run_set_ceiling(self.run_id, new_ceiling)

    @property
    def spent(self) -> float:
        return self.store.spent(self.run_id)

    @property
    def remaining(self) -> float:
        return round(self.ceiling - self.spent, 4)

    def can_afford(self, path: str, body: dict) -> bool:
        return estimate_cost(path, body) <= self.remaining

    # -- calls ---------------------------------------------------------
    @staticmethod
    def _key(path: str, body: dict) -> str:
        return hashlib.sha256((path + json.dumps(body, sort_keys=True)).encode()).hexdigest()

    def post(self, path: str, body: dict, *, use_cache: bool = True, max_retries: int = 4) -> Result:
        key = self._key(path, body)
        if use_cache:
            hit = self.store.cache_get(key, self.cache_ttl_s)
            if hit:
                self.store.ledger_add(self.run_id, path, key, 0.0, estimated=False, cached=True,
                                      request_id=hit["request_id"], status="ok", note="cache")
                return Result(hit["response"], True, 0.0, hit["fetched_at"], hit["request_id"])

        est = estimate_cost(path, body)
        if est > self.remaining:
            self.store.ledger_add(self.run_id, path, key, 0.0, estimated=True, cached=False,
                                  request_id=None, status="blocked",
                                  note=f"needs ~{est}, remaining {self.remaining}")
            raise BudgetExceeded(f"{path} needs ~{est} credits, only {self.remaining} left in this run")

        headers = {"authorization": f"Bearer {self.api_key}", "x-api-version": API_VERSION,
                   "content-type": "application/json"}
        group = endpoint_group(path)
        attempt = 0
        while True:
            self.limiter.acquire(group)
            status, resp_headers, payload = self.transport(BASE_URL + path, headers, body)
            h = {k.lower(): v for k, v in resp_headers.items()}
            request_id = h.get("x-request-id")

            if status == 429 and attempt < max_retries:
                attempt += 1
                self.limiter.sleep(_reset_seconds(h.get("x-ratelimit-reset"), self.limiter.clock))
                continue
            if status >= 500 and attempt < 2:
                attempt += 1
                self.limiter.sleep(2 ** attempt)
                continue
            if status == 402:
                self._log_error(path, key, request_id, "402 credits exhausted")
                raise CreditsExhausted("Crustdata account is out of credits")
            if status == 403:
                self._log_error(path, key, request_id, "403 endpoint disabled")
                raise EndpointDisabled(f"{path} is not enabled on this key")
            if status >= 400:
                self._log_error(path, key, request_id, f"{status} {json.dumps(payload)[:200]}")
                raise CrustdataError(f"{path} -> HTTP {status}: {json.dumps(payload)[:300]}")
            break

        header_credits = h.get("x-credits-used")
        estimated = header_credits is None
        credits = float(header_credits) if header_credits is not None else est
        fetched_at = self.store.cache_put(key, path, body, payload, request_id)
        self.store.ledger_add(self.run_id, path, key, credits, estimated=estimated, cached=False,
                              request_id=request_id, status="ok")
        return Result(payload, False, credits, fetched_at, request_id)

    def _log_error(self, path: str, key: str, request_id: Optional[str], note: str) -> None:
        self.store.ledger_add(self.run_id, path, key, 0.0, estimated=False, cached=False,
                              request_id=request_id, status="error", note=note)

    # -- convenience wrappers -----------------------------------------
    def job_search(self, filters: dict, *, limit: int = 20, fields: Optional[list] = None,
                   sorts: Optional[list] = None, cursor: Optional[str] = None) -> Result:
        body: dict = {"filters": filters, "limit": limit}
        if fields:
            body["fields"] = fields
        if sorts:
            body["sorts"] = sorts
        if cursor:
            body["cursor"] = cursor
        return self.post("/job/search", body)

    def company_search(self, filters: dict, *, limit: int = 20, fields: Optional[list] = None,
                       cursor: Optional[str] = None) -> Result:
        body: dict = {"filters": filters, "limit": limit}
        if fields:
            body["fields"] = fields
        if cursor:
            body["cursor"] = cursor
        return self.post("/company/search", body)


def _reset_seconds(value: Optional[str], clock: Callable[[], float]) -> float:
    """x-ratelimit-reset may be seconds-until-reset or an epoch timestamp; handle both."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 30.0
    if v > 1e9:  # epoch seconds
        v = v - time.time()
    return max(1.0, min(v, 90.0))
