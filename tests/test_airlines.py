import time
import unittest

from flightback.airlines import extract_contacts, extract_passage, refresh_airline
from flightback.crustdata import Crustdata, RateLimiter
from flightback.store import Store

URL_6E = "https://www.goindigo.in/contact-us.html"
PAGE = ("menu " * 400 + "Customer Grievance Redressal\nContact: Customer.experience@goindigo.in;\n"
        "Nodal Officer, X Y at nodalofficer@goindigo.in; 0124\nAppellate Authority, Z at appellateauthority@goindigo.in\n" + "footer " * 400)
IDENT = [{"matched_on": "goindigo.in", "matches": [{"confidence_score": 1.0, "company_data": {
    "crustdata_company_id": 2247, "basic_info": {"name": "IndiGo", "crustdata_company_id": 2247, "primary_domain": "goindigo.in"}}}]}]
SNAP = {"grievance": {"contacts": {"nodal_officer_email": "nodalofficer@goindigo.in",
                                   "appellate_authority_email": "appellateauthority@goindigo.in"}}}


class Seq:
    def __init__(self, *resp):
        self.resp, self.calls = list(resp), []

    def __call__(self, url, headers, body):
        self.calls.append(url)
        return self.resp.pop(0)


def client(*resp, ceiling=10):
    class C:  # no real sleeping in tests
        t = 0.0
    return Crustdata(Store(":memory:"), "r", ceiling, api_key="k", transport=Seq(*resp),
                     limiter=RateLimiter({"core": 99, "web": 99, "social": 99, "autocomplete": 99}, sleep=lambda s: None))


def ok(payload, credits="0.2"):
    return 200, {"X-Credits-Used": credits}, payload


def fetch(status=200, content=PAGE, success=True):
    return [{"success": success, "url": URL_6E, "http_status": status, "timestamp": int(time.time()), "title": "t", "content": content}]


class AirlineRefreshTests(unittest.TestCase):
    def test_extracts_only_the_relevant_passage(self):
        p = extract_passage(PAGE)
        self.assertLess(len(p), 1500)
        self.assertEqual(extract_contacts(p), {"nodal_officer_email": "nodalofficer@goindigo.in",
                                               "appellate_authority_email": "appellateauthority@goindigo.in"})

    def test_good_refresh_is_primary_verified_with_hash_and_no_changes(self):
        cd = client(ok(IDENT), ok(fetch(), "1.0"))
        r = refresh_airline(cd, "6E", SNAP)
        self.assertEqual(r["grievance"]["status"], "primary_verified")
        self.assertEqual(len(r["grievance"]["passage_sha256"]), 64)
        self.assertEqual(r["changes"], [])
        self.assertEqual(r["identity"]["crustdata_company_id"], 2247)
        self.assertAlmostEqual(r["credits"], 1.2)

    def test_changed_email_is_reported(self):
        changed = PAGE.replace("nodalofficer@goindigo.in", "newnodal@goindigo.in")
        r = refresh_airline(client(ok(IDENT), ok(fetch(content=changed))), "6E", SNAP)
        self.assertEqual(r["changes"], ["nodal_officer_email changed: nodalofficer@goindigo.in -> newnodal@goindigo.in"])

    def test_http_403_is_blocked_even_when_success_is_true(self):
        r = refresh_airline(client(ok(IDENT), ok(fetch(status=403, content="403 ERROR", success=True))), "6E", SNAP)
        self.assertEqual(r["grievance"]["status"], "primary_blocked")
        self.assertIn("CANNOT VERIFY", r["grievance"]["status_for_packet"])

    def test_empty_content_is_unverifiable_not_no_data(self):
        r = refresh_airline(client(ok(IDENT), ok(fetch(content=""))), "6E", SNAP)
        self.assertEqual(r["grievance"]["status"], "unverifiable")

    def test_page_without_officer_emails_is_unverifiable(self):
        r = refresh_airline(client(ok(IDENT), ok(fetch(content="just a marketing page " * 50))), "6E", SNAP)
        self.assertEqual(r["grievance"]["status"], "unverifiable")

    def test_low_confidence_identity_goes_to_review(self):
        weak = [{"matches": [{"confidence_score": 0.5, "company_data": {"basic_info": {"primary_domain": "x.com"}}}]}]
        r = refresh_airline(client(ok(weak), ok(fetch())), "6E", SNAP)
        self.assertEqual(r["identity"]["status"], "REVIEW_REQUIRED")

    def test_budget_ceiling_stops_the_refresh_before_any_call(self):
        cd = client(ceiling=0.05)
        r = refresh_airline(cd, "6E", SNAP)
        self.assertEqual(r["status"], "budget_exceeded")
        self.assertEqual(cd.transport.calls, [])

    def test_repeat_refresh_is_served_from_cache_for_free(self):
        cd = client(ok(IDENT), ok(fetch(), "1.0"))
        refresh_airline(cd, "6E", SNAP)
        r2 = refresh_airline(cd, "6E", SNAP)
        self.assertEqual(r2["credits"], 0.0)
        self.assertEqual(len(cd.transport.calls), 2)

    def test_airline_without_a_grievance_url_is_not_collected(self):
        r = refresh_airline(client(ok(IDENT)), "SG", {})
        self.assertEqual(r["grievance"]["status"], "not_collected")


if __name__ == "__main__":
    unittest.main()
