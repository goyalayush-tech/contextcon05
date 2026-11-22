import json
import unittest
from pathlib import Path

from flightback.packet import build_case, load_evidence

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = {k: v for k, v in json.loads((ROOT / "data" / "samples.json").read_text()).items() if not k.startswith("_")}
EVIDENCE = load_evidence()


def cond(case, cid):
    return next(c for c in case["conditions"] if c["id"] == cid)["status"]


class PacketTests(unittest.TestCase):
    def build(self, name):
        return build_case(SAMPLES[name], EVIDENCE)

    def test_every_sample_meets_its_expectation(self):
        for name, s in SAMPLES.items():
            case = self.build(name)
            for key, want in s["expect"].items():
                with self.subTest(sample=name, check=key):
                    if key == "payable":
                        self.assertEqual(case["amounts"]["payable_compensation"], want)
                    elif key == "shortfall":
                        self.assertEqual(case["amounts"]["shortfall"], want)
                    elif key == "airline":
                        self.assertEqual(case["airline"]["status"], want)
                    elif key == "airline_route":
                        self.assertEqual(case["escalation"][0]["how"], want)
                    else:
                        self.assertEqual(cond(case, key), want)

    def test_nothing_is_ever_marked_sent(self):
        for name in SAMPLES:
            case = self.build(name)
            self.assertEqual(case["approval"]["state"], "awaiting_passenger_approval")
            self.assertTrue(case["complaint_draft"].startswith("DRAFT, NOT SENT"))

    def test_complaint_only_asserts_supported_claims(self):
        draft = self.build("cancel_long_notice")["complaint_draft"]
        self.assertNotIn("financial compensation", draft)  # not owed with 20 days' notice
        self.assertIn("full refund of my ticket", draft)  # refund duty still stated

    def test_compensation_formula_appears_in_the_draft(self):
        c = self.build("cancel_clear_win")
        self.assertIn("min(5000, 3200 + 450) = 3650", c["complaint_draft"])

    def test_missing_operating_carrier_is_flagged_not_guessed(self):
        c = self.build("cancel_operating_missing")
        self.assertIsNone(c["airline"]["code"])
        self.assertTrue(any("operating airline" in m for m in c["missing"]))

    def test_unverified_pack_warning_on_refund(self):
        c = self.build("refund_overdue_shortfall")
        self.assertTrue(any("NOT verified" in w for w in c["warnings"]))
        self.assertFalse(c["rule_pack"]["verified"])

    def test_blocked_airline_source_is_never_presented_as_verified(self):
        c = self.build("cancel_akasa_blocked")
        self.assertEqual(c["airline"]["grievance"]["status"], "primary_blocked")
        self.assertIn("CANNOT VERIFY", c["escalation"][0]["how"])

    def test_every_fact_has_a_provenance_label(self):
        c = self.build("cancel_clear_win")
        labels = {e["provenance"] for e in c["evidence_index"]}
        self.assertEqual(labels, {"document", "stated by passenger, no document"})

    def test_airline_source_conflicts_surface_as_warnings(self):
        c = self.build("cancel_clear_win")
        self.assertTrue(any("Airline source conflict" in w for w in c["warnings"]))

    def test_unknown_case_type_is_rejected(self):
        with self.assertRaises(ValueError):
            build_case({"case_type": "lost_bag"}, EVIDENCE)


if __name__ == "__main__":
    unittest.main()
