import unittest

from flightback.crustdata import (BudgetExceeded, CreditsExhausted, Crustdata, EndpointDisabled,
                                  RateLimiter, estimate_cost)
from flightback.store import Store


class FakeTransport:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, body):
        self.calls.append((url, body))
        return self.responses.pop(0)


def ok(credits="0.15", rid="r1", payload=None):
    return 200, {"X-Credits-Used": credits, "X-Request-Id": rid}, payload or {"job_listings": []}


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make(responses, ceiling=10, run="run1", store=None):
    clock = Clock()
    store = store or Store(":memory:")
    cd = Crustdata(store, run, ceiling, api_key="k", transport=FakeTransport(responses),
                   limiter=RateLimiter({"core": 5, "web": 10, "social": 100, "autocomplete": 300},
                                       clock=clock.now, sleep=clock.sleep))
    return cd, clock, store


class ClientTests(unittest.TestCase):
    def test_identical_request_is_served_from_cache_and_costs_nothing(self):
        cd, _, _ = make([ok()])
        a = cd.job_search({"field": "x", "type": "=", "value": 1}, limit=5)
        b = cd.job_search({"field": "x", "type": "=", "value": 1}, limit=5)
        self.assertFalse(a.cached)
        self.assertTrue(b.cached)
        self.assertEqual(cd.spent, 0.15)
        self.assertEqual(len(cd.transport.calls), 1)

    def test_ledger_uses_header_credits_and_request_id(self):
        cd, _, store = make([ok("0.15", "abc")])
        cd.job_search({"f": 1}, limit=5)
        row = store.ledger_rows("run1")[0]
        self.assertEqual((row["credits"], row["request_id"], row["estimated"]), (0.15, "abc", 0))

    def test_missing_header_falls_back_to_estimate_and_is_flagged(self):
        cd, _, store = make([(200, {}, {"ok": 1})])
        cd.job_search({"f": 1}, limit=10)
        row = store.ledger_rows("run1")[0]
        self.assertEqual(row["credits"], 0.3)
        self.assertEqual(row["estimated"], 1)

    def test_call_over_ceiling_is_blocked_before_any_request(self):
        cd, _, store = make([], ceiling=0.1)
        with self.assertRaises(BudgetExceeded):
            cd.job_search({"f": 1}, limit=20)  # ~0.6 credits
        self.assertEqual(cd.transport.calls, [])
        self.assertEqual(store.ledger_rows("run1")[0]["status"], "blocked")

    def test_budget_cut_mid_run_takes_effect_and_survives_restart(self):
        cd, _, store = make([ok("0.15"), ok("0.15", "r2")], ceiling=1.0)
        cd.job_search({"a": 1}, limit=5)
        cd.cut_budget(0.2)
        with self.assertRaises(BudgetExceeded):
            cd.job_search({"b": 1}, limit=20)
        # "crash": new client object, same database and run id, ceiling argument ignored
        cd2, _, _ = make([], ceiling=999, store=store)
        self.assertEqual(cd2.ceiling, 0.2)
        self.assertEqual(cd2.spent, 0.15)

    def test_resume_replays_cache_without_paying_again(self):
        cd, _, store = make([ok("0.15")])
        cd.job_search({"a": 1}, limit=5)
        cd2, _, _ = make([], store=store)  # no responses available: any real call would fail
        r = cd2.job_search({"a": 1}, limit=5)
        self.assertTrue(r.cached)
        self.assertEqual(cd2.spent, 0.15)

    def test_429_waits_for_reset_then_retries(self):
        cd, clock, _ = make([(429, {"x-ratelimit-reset": "7"}, {}), ok()])
        r = cd.job_search({"a": 1}, limit=5)
        self.assertFalse(r.cached)
        self.assertIn(7.0, clock.slept)

    def test_limiter_blocks_sixth_core_call_inside_a_minute(self):
        cd, clock, _ = make([ok(rid=f"r{i}") for i in range(6)])
        for i in range(6):
            cd.job_search({"i": i}, limit=1)
        self.assertGreaterEqual(clock.t, 60)  # sixth call had to wait for the window

    def test_402_and_403_raise_typed_errors(self):
        cd, _, _ = make([(402, {}, {}), (403, {}, {})])
        with self.assertRaises(CreditsExhausted):
            cd.job_search({"a": 1}, limit=1)
        with self.assertRaises(EndpointDisabled):
            cd.job_search({"a": 2}, limit=1)

    def test_estimates(self):
        self.assertEqual(estimate_cost("/job/search", {"limit": 100}), 3.0)
        self.assertEqual(estimate_cost("/company/enrich", {}), 2.0)
        self.assertEqual(estimate_cost("/person/search/autocomplete", {}), 0.0)


if __name__ == "__main__":
    unittest.main()
