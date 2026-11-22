import json
import os
import sqlite3
import tempfile
import unittest

os.environ.setdefault("FLIGHTBACK_DB", tempfile.mktemp(suffix=".db"))  # never the real flightback.db
os.environ.setdefault("CRUSTDATA_API_KEY", "")

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "needs fastapi + httpx")
class CaseLifecycleApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flightback import app as appmod
        cls.appmod, cls.c = appmod, TestClient(appmod.app)
        cls.sample = cls.c.get("/api/samples/cancel_clear_win").json()

    def new_case(self, pnr):
        p = json.loads(json.dumps(self.sample))
        p["flight"]["pnr"] = pnr
        r = self.c.post("/api/case", json=p)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_case_list_shows_newest_first_with_a_summary(self):
        a, b = self.new_case("LIST1"), self.new_case("LIST2")
        rows = self.c.get("/api/cases").json()
        ids = [r["case_id"] for r in rows]
        self.assertLess(ids.index(b["case_id"]), ids.index(a["case_id"]))
        row = next(r for r in rows if r["case_id"] == b["case_id"])
        self.assertEqual((row["case_type"], row["airline"], row["payable_compensation"]), ("cancellation", "6E", "3650"))
        self.assertEqual(row["approval"], "awaiting_passenger_approval")
        self.assertNotIn("complaint_draft", row)  # a summary, not the packet

    def test_every_case_response_carries_the_next_step(self):
        c = self.new_case("NEXT1")
        self.assertIn("approve", c["next_step"])
        self.assertIn("approve", self.c.get(f"/api/case/{c['case_id']}").json()["next_step"])

    def test_edited_draft_is_saved_and_survives_a_reload(self):
        c = self.new_case("DRAFT1")
        edited = c["complaint_draft"] + "\nPS: my boarding pass is attached."
        r = self.c.put(f"/api/case/{c['case_id']}/draft", json={"text": edited}).json()
        self.assertTrue(r["draft_edited"])
        again = self.c.get(f"/api/case/{c['case_id']}").json()
        self.assertEqual(again["complaint_draft"], edited)
        self.assertEqual(again["generated_draft"], c["complaint_draft"])
        restored = self.c.put(f"/api/case/{c['case_id']}/draft", json={"text": None}).json()
        self.assertFalse(restored["draft_edited"])
        self.assertEqual(restored["complaint_draft"], c["complaint_draft"])

    def test_changing_an_approved_draft_withdraws_the_approval(self):
        c = self.new_case("DRAFT2")
        cid = c["case_id"]
        self.assertEqual(self.c.post(f"/api/case/{cid}/approve").status_code, 200)
        same = self.c.put(f"/api/case/{cid}/draft", json={"text": c["complaint_draft"]}).json()
        self.assertFalse(same["approval_withdrawn"])  # saving the approved text again changes nothing
        self.assertEqual(same["approval"]["state"], "approved_by_passenger")
        changed = self.c.put(f"/api/case/{cid}/draft", json={"text": c["complaint_draft"] + "\nEdited."}).json()
        self.assertTrue(changed["approval_withdrawn"])
        self.assertEqual(changed["approval"]["state"], "awaiting_passenger_approval")
        self.assertTrue(self.c.post(f"/api/case/{cid}/approve").json()["first_time"])  # approve the new text

    def test_draft_validation(self):
        cid = self.new_case("DRAFT3")["case_id"]
        self.assertEqual(self.c.put(f"/api/case/{cid}/draft", json={"text": "   "}).status_code, 422)
        self.assertEqual(self.c.put(f"/api/case/{cid}/draft", json={"text": "x" * 20001}).status_code, 413)
        self.assertEqual(self.c.put("/api/case/FB-nope/draft", json={"text": "hi"}).status_code, 404)

    def test_page_urls_serve_the_app_and_unknown_api_paths_stay_404(self):
        dist = self.appmod.DIST / "index.html"
        for path in ("/", "/new", "/cases", "/sources", "/case/FB-abc123"):
            r = self.c.get(path)
            self.assertEqual(r.status_code, 200 if dist.is_file() else 503, path)
        self.assertEqual(self.c.get("/api/nope").status_code, 404)
        for probe in ("/%2e%2e/flightback.db", "/%2e%2e/%2e%2e/flightback.db", "/..%2fapp.py"):
            body = self.c.get(probe).content
            self.assertNotIn(b"SQLite format", body, probe)  # never a file from outside dist
            self.assertNotIn(b"FastAPI(", body, probe)


class StoreMigrationTests(unittest.TestCase):
    def test_a_database_from_before_draft_support_is_upgraded_in_place(self):
        path = tempfile.mktemp(suffix=".db")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE cases (case_id TEXT PRIMARY KEY, created_at REAL NOT NULL, packet TEXT NOT NULL, "
                   "approval TEXT NOT NULL DEFAULT 'awaiting_passenger_approval', approved_at REAL)")
        db.execute("INSERT INTO cases (case_id, created_at, packet) VALUES ('FB-old', 1, ?)",
                   (json.dumps({"complaint_draft": "old draft", "case_type": "delay"}),))
        db.commit()
        db.close()
        from flightback.store import Store
        s = Store(path)
        c = s.case_get("FB-old")
        self.assertEqual((c["complaint_draft"], c["draft_edited"]), ("old draft", False))
        self.assertFalse(s.case_set_draft("FB-old", "new draft", "sha"))
        self.assertEqual(s.case_get("FB-old")["complaint_draft"], "new draft")


if __name__ == "__main__":
    unittest.main()
