import time
import unittest

from flightback.crustdata import Crustdata, RateLimiter
from flightback.evidence_run import has_live_source, run_for_case, snapshot_only
from flightback.store import Store

URL = "https://www.goindigo.in/contact-us.html"
PAGE = ("menu " * 400 + "Customer Grievance Redressal\nNodal Officer, X Y at nodalofficer@goindigo.in; 0124\n"
        "Appellate Authority, Z at appellateauthority@goindigo.in\n" + "footer " * 400)
IDENT = [{"matched_on": "goindigo.in", "matches": [{"confidence_score": 1.0, "company_data": {
    "crustdata_company_id": 2247, "basic_info": {"name": "IndiGo", "crustdata_company_id": 2247, "primary_domain": "goindigo.in"}}}]}]
SNAP = {"airline": "IndiGo", "identity": {"crustdata_company_id": 2247},
        "grievance": {"status": "primary_verified", "retrieved_at": "2026-11-22T11:00:00+05:30", "passage_sha256": "0" * 64,
                      "contacts": {"nodal_officer_email": "nodalofficer@goindigo.in",
                                   "appellate_authority_email": "appellateauthority@goindigo.in"}}}


def page(status=200, content=PAGE):
    return [{"success": True, "url": URL, "http_status": status, "timestamp": int(time.time()), "content": content}]


class Seq:
    def __init__(self, *resp):
        self.resp = list(resp)

    def __call__(self, url, headers, body):
        r = self.resp.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def client(*resp, ceiling=3.0, store=None, run="case:FB-1"):
    return Crustdata(store or Store(":memory:"), run, ceiling, api_key="k", transport=Seq(*resp),
                     limiter=RateLimiter({"core": 99, "web": 99, "social": 99, "autocomplete": 99}, sleep=lambda s: None))


def ok(payload, credits):
    return 200, {"X-Credits-Used": credits}, payload


class EvidenceRunTests(unittest.TestCase):
    def test_credits_exhausted_or_endpoint_disabled_falls_back_instead_of_raising(self):
        for status in (402, 403):
            with self.subTest(status=status):
                block, rec = run_for_case(client((status, {}, {"error": "x"})), "6E", SNAP)
                self.assertEqual(block["mode"], "stale_snapshot")
                self.assertIn("error", block["reason"])
                self.assertEqual(rec["grievance"], SNAP["grievance"])
                self.assertEqual(block["calls"][0]["status"], "error")

    def test_live_verify_keeps_snapshot_contacts_the_page_does_not_carry(self):
        snap = {**SNAP, "grievance": {**SNAP["grievance"], "contacts": {
            **SNAP["grievance"]["contacts"], "customer_email": "Customer.experience@goindigo.in", "phone": "0124"}}}
        block, rec = run_for_case(client(ok(IDENT, "0.2"), ok(page(), "1.0")), "6E", snap)
        self.assertEqual(block["mode"], "live")
        self.assertEqual(rec["grievance"]["contacts"]["customer_email"], "Customer.experience@goindigo.in")
        self.assertEqual(rec["grievance"]["contacts"]["phone"], "0124")
        self.assertEqual(rec["grievance"]["contacts"]["nodal_officer_email"], "nodalofficer@goindigo.in")

    def test_live_run_reports_calls_credits_and_unchanged_contacts(self):
        block, rec = run_for_case(client(ok(IDENT, "0.2"), ok(page(), "1.0")), "6E", SNAP)
        self.assertEqual(block["mode"], "live")
        self.assertFalse(block["contacts_changed"])
        self.assertEqual([c["endpoint"] for c in block["calls"]], ["/company/identify", "/web/enrich/live"])
        self.assertAlmostEqual(block["spent"], 1.2)
        self.assertEqual(block["live_http_status"], 200)
        self.assertNotEqual(rec["grievance"]["passage_sha256"], "0" * 64)

    def test_second_assessment_of_the_same_case_is_cached_and_free(self):
        store = Store(":memory:")
        run_for_case(client(ok(IDENT, "0.2"), ok(page(), "1.0"), store=store), "6E", SNAP)
        block, _ = run_for_case(client(store=store), "6E", SNAP)  # no responses queued: any real call would fail
        self.assertEqual(block["mode"], "cached")
        self.assertTrue(all(c["cached"] for c in block["calls"]))
        self.assertEqual(len(block["calls"]), 2)  # only this run's calls, not the first run's
        self.assertAlmostEqual(block["spent"], 1.2)

    def test_changed_email_flags_contacts_and_uses_the_new_address(self):
        changed = PAGE.replace("nodalofficer@goindigo.in", "newnodal@goindigo.in")
        block, rec = run_for_case(client(ok(IDENT, "0.2"), ok(page(content=changed), "1.0")), "6E", SNAP)
        self.assertTrue(block["contacts_changed"])
        self.assertIn("newnodal@goindigo.in", block["changes"][0])
        self.assertEqual(rec["grievance"]["contacts"]["nodal_officer_email"], "newnodal@goindigo.in")

    def test_blocked_page_keeps_verified_snapshot_and_says_stale(self):
        block, rec = run_for_case(client(ok(IDENT, "0.2"), ok(page(status=403), "1.0")), "6E", SNAP)
        self.assertEqual(block["mode"], "stale_snapshot")
        self.assertFalse(block["contacts_changed"])
        self.assertEqual(rec["grievance"], SNAP["grievance"])  # a failed check never erases verified contacts

    def test_budget_ceiling_stops_the_run_and_falls_back(self):
        block, rec = run_for_case(client(ceiling=0.1), "6E", SNAP)
        self.assertEqual(block["mode"], "stale_snapshot")
        self.assertIn("budget_exceeded", block["reason"])
        self.assertEqual(rec["grievance"], SNAP["grievance"])
        self.assertEqual(block["spent"], 0.0)

    def test_network_failure_falls_back_instead_of_raising(self):
        err = ConnectionError("down")
        block, _ = run_for_case(client(err, err, err), "6E", SNAP)
        self.assertEqual(block["mode"], "stale_snapshot")

    def test_helpers(self):
        self.assertTrue(has_live_source("6E"))
        self.assertFalse(has_live_source("SG"))
        self.assertEqual(snapshot_only("SG", "x")["mode"], "snapshot_only")


if __name__ == "__main__":
    unittest.main()
