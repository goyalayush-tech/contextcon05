import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except Exception:  # fastapi/httpx not installed: run these with the project venv
    TestClient = None

ROOT = Path(__file__).resolve().parent.parent
DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["FLIGHTBACK_DB"] = DB
os.environ["CRUSTDATA_API_KEY"] = ""  # empty (not absent) so .env is never loaded into tests


@unittest.skipIf(TestClient is None, "needs fastapi + httpx (use .venv/bin/python)")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flightback import app as appmod
        cls.appmod = appmod
        cls.c = TestClient(appmod.app)
        cls.sample = cls.c.get("/api/samples/cancel_clear_win").json()

    def make(self):
        r = self.c.post("/api/case", json=self.sample)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_creating_the_same_case_twice_gives_the_same_id(self):
        self.assertEqual(self.make()["case_id"], self.make()["case_id"])

    def test_approval_is_idempotent_and_nothing_is_sent(self):
        cid = self.make()["case_id"]
        first = self.c.post(f"/api/case/{cid}/approve").json()
        second = self.c.post(f"/api/case/{cid}/approve").json()
        self.assertTrue(first["first_time"])
        self.assertFalse(second["first_time"])
        self.assertFalse(first["sent"])
        self.assertEqual(self.c.get(f"/api/case/{cid}").json()["approval"]["state"], "approved_by_passenger")

    def test_duplicate_followup_is_ignored(self):
        cid = self.make()["case_id"]
        body = {"kind": "complaint_submitted", "data": {"reference": "ABC123"}}
        a = self.c.post(f"/api/case/{cid}/followup", json=body).json()
        b = self.c.post(f"/api/case/{cid}/followup", json=body).json()
        self.assertTrue(a["recorded"])
        self.assertTrue(b["duplicate_ignored"])
        self.assertEqual(len(b["followups"]), 1)

    def test_rejection_citing_extraordinary_circumstances_gets_the_right_advice(self):
        cid = self.make()["case_id"]
        r = self.c.post(f"/api/case/{cid}/followup", json={"kind": "airline_rejection",
                        "data": {"reason": "Cancelled due to weather"}}).json()
        self.assertIn("extraordinary", r["next_step"])
        self.assertIn("not the refund", r["next_step"])

    def test_refund_shortfall_is_called_out(self):
        s = self.c.get("/api/samples/refund_overdue_shortfall").json()
        cid = self.c.post("/api/case", json=s).json()["case_id"]
        r = self.c.post(f"/api/case/{cid}/followup", json={"kind": "refund_received", "data": {"amount": 4200}}).json()
        self.assertIn("800", r["next_step"])

    def test_case_survives_a_restart(self):
        cid = self.make()["case_id"]
        from flightback.store import Store
        again = Store(DB)  # a brand new process opening the same database
        self.assertIsNotNone(again.case_get(cid))

    def test_bad_case_type_is_a_422(self):
        self.assertEqual(self.c.post("/api/case", json={"case_type": "lost_bag"}).status_code, 422)

    def test_unknown_case_is_a_404(self):
        self.assertEqual(self.c.get("/api/case/FB-nope").status_code, 404)

    def test_refresh_without_a_key_is_refused_not_faked(self):
        r = self.c.post("/api/airline/6E/refresh")
        self.assertEqual(r.status_code, 503)
        self.assertIn("snapshot", r.json()["detail"])

    def test_extract_suggests_facts_with_quotes_and_never_applies_them(self):
        r = self.c.post("/api/extract", json={"text": "Flight cancelled. Scheduled 20 Nov 2026 17:00. Basic fare Rs 3,200."}).json()
        fields = {c["suggested_field"]: c for c in r["candidates"]}
        self.assertEqual(fields["scheduled_departure"]["value"], "2026-11-20T17:00")
        self.assertEqual(fields["basic_fare"]["value"], 3200.0)
        self.assertIn("20 Nov 2026 17:00", fields["scheduled_departure"]["snippet"])

    def test_oversized_paste_is_rejected(self):
        self.assertEqual(self.c.post("/api/extract", json={"text": "x" * 20001}).status_code, 413)

    def test_schema_covers_all_three_case_types(self):
        self.assertEqual(set(self.c.get("/api/schema").json()), {"cancellation", "delay", "refund"})

    def test_rules_endpoint_reports_verification(self):
        packs = {p["id"]: p for p in self.c.get("/api/rules").json()}
        self.assertTrue(packs["DGCA-CAR-S3-M-IV"]["verified"])
        self.assertFalse(packs["DGCA-CAR-S3-M-II"]["verified"])


class _Seq:
    def __init__(self, *resp):
        self.resp = list(resp)

    def __call__(self, url, headers, body):
        return self.resp.pop(0)


@unittest.skipIf(TestClient is None, "needs fastapi + httpx (use .venv/bin/python)")
class LiveCasePathTests(unittest.TestCase):
    """The per-case evidence run, with Crustdata replaced by a fake transport (no credits, no network)."""

    @classmethod
    def setUpClass(cls):
        from flightback import app as appmod
        cls.appmod, cls.c = appmod, TestClient(appmod.app)
        cls.sample = cls.c.get("/api/samples/cancel_clear_win").json()
        snap = json.loads((ROOT / "data" / "airline_evidence.json").read_text())["airlines"]["6E"]["grievance"]
        cls.url, cls.contacts = snap["source_url"], snap["contacts"]

    def page(self, nodal=None):
        n = nodal or self.contacts["nodal_officer_email"]
        return ("menu " * 300 + f"Nodal Officer, X Y at {n}; 0124\nAppellate Authority, Z at "
                f"{self.contacts['appellate_authority_email']}\n" + "footer " * 300)

    def make(self, *responses, pnr):
        from unittest import mock
        from flightback.crustdata import Crustdata, RateLimiter
        from flightback.store import Store
        sample = json.loads(json.dumps(self.sample))
        sample["flight"]["pnr"] = pnr
        ident = [{"matched_on": "goindigo.in", "matches": [{"confidence_score": 1.0, "company_data": {
            "crustdata_company_id": 2247, "basic_info": {"name": "IndiGo", "crustdata_company_id": 2247,
                                                         "primary_domain": "goindigo.in"}}}]}]
        item = {"success": True, "url": self.url, "http_status": 200, "timestamp": 1_795_000_000, "content": responses[0]}
        seq = _Seq((200, {"X-Credits-Used": "0.2"}, ident), (200, {"X-Credits-Used": "1.0"}, [item]))
        factory = lambda cid: Crustdata(Store(":memory:"), f"case:{cid}", 3.0, api_key="k", transport=seq,
                                        limiter=RateLimiter({"core": 99, "web": 99, "social": 99, "autocomplete": 99},
                                                            sleep=lambda s: None))
        with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": "k"}), mock.patch.object(self.appmod, "case_client", factory):
            return self.c.post("/api/case", json=sample).json()

    def test_no_key_means_snapshot_only_and_says_why(self):
        r = self.c.post("/api/case", json=self.sample).json()
        self.assertEqual(r["evidence_run"]["mode"], "snapshot_only")
        self.assertIn("No Crustdata key", r["evidence_run"]["reason"])
        self.assertEqual(r["leads"]["label"], "LEAD, NOT PROOF")

    def test_live_case_records_its_calls_and_credits(self):
        r = self.make(self.page(), pnr="LIVE1")
        run = r["evidence_run"]
        self.assertEqual(run["mode"], "live")
        self.assertFalse(run["contacts_changed"])
        self.assertAlmostEqual(run["spent"], 1.2)
        self.assertEqual(self.c.post(f"/api/case/{r['case_id']}/approve").status_code, 200)

    def test_changed_contact_warns_and_blocks_approval_until_acknowledged(self):
        r = self.make(self.page(nodal="newnodal@goindigo.in"), pnr="LIVE2")
        self.assertTrue(r["evidence_run"]["contacts_changed"])
        self.assertTrue(r["warnings"][0].startswith("AIRLINE CONTACT CHANGED"))
        self.assertIn("newnodal@goindigo.in", r["complaint_draft"])
        cid = r["case_id"]
        blocked = self.c.post(f"/api/case/{cid}/approve")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(self.c.get(f"/api/case/{cid}").json()["approval"]["state"], "awaiting_passenger_approval")
        done = self.c.post(f"/api/case/{cid}/approve", json={"acknowledge_contact_change": True})
        self.assertEqual(done.status_code, 200)
        self.assertTrue(done.json()["first_time"])

    def test_airline_without_a_live_source_is_snapshot_only(self):
        from unittest import mock
        sample = json.loads(json.dumps(self.sample))
        sample["flight"].update(operating_carrier="SG", marketing_carrier="SG", pnr="SGX")
        with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": "k"}):
            r = self.c.post("/api/case", json=sample).json()
        self.assertEqual(r["evidence_run"]["mode"], "snapshot_only")
        self.assertIn("identity only", r["evidence_run"]["reason"])

    def test_freshness_lists_every_airline_with_age_and_leads(self):
        f = self.c.get("/api/freshness").json()
        self.assertEqual(len(f["airlines"]), 6)
        self.assertTrue(all("age_hours" in a and "leads" in a and "stale" in a for a in f["airlines"]))

    def test_watch_endpoints_need_a_key(self):
        self.assertEqual(self.c.get("/api/watch").status_code, 503)
        self.assertEqual(self.c.post("/api/watch/sync").status_code, 503)


if __name__ == "__main__":
    unittest.main()
