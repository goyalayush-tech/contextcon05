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


if __name__ == "__main__":
    unittest.main()
