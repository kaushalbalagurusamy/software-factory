import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate  # noqa: E402
from common import CONFIG, load_yaml  # noqa: E402

QS = load_yaml(CONFIG / "policy.yaml")["severity_questions"]


def answers(*yes_ids):
    out = []
    for q in QS:
        out.append({"id": q["id"], "q": q["q"], "a": q["id"] in yes_ids})
        if q["id"] in yes_ids:
            break
    return out


def finding(**kw):
    f = {"id": "F-001", "claim_ids": ["C-001"], "lens": "licensing", "status": "confirmed", "route": "retrieval",
         "evidence": [{"kind": "quote", "ref": "https://example.org", "quote": "x", "tier": "primary", "date": "2026-10-14"}],
         "severity": {"tier": "critical", "answers": answers("law-licence-terms-ethics")},
         "underlying_problem": "p", "disposition": "reframe", "spec_section": "legal-terms"}
    f.update(kw)
    return f


def reg(*findings, quarantine=()):
    return {"findings": list(findings), "quarantine": list(quarantine)}


class TierTest(unittest.TestCase):
    def test_first_yes_sets_tier(self):
        self.assertEqual(validate.expected_tier(answers("production-failure"), QS), "high")

    def test_all_no_is_low(self):
        self.assertEqual(validate.expected_tier([{"id": q["id"], "q": q["q"], "a": False} for q in QS], QS), "low")

    def test_skipped_question_is_unreproducible(self):
        self.assertIsNone(validate.expected_tier([{"id": "principal-reject", "q": "", "a": True}], QS))


class RegisterRulesTest(unittest.TestCase):
    def test_clean_register_passes(self):
        self.assertEqual(validate.check_register(reg(finding())), [])

    def test_tier_mismatch_fails(self):
        f = finding(severity={"tier": "medium", "answers": answers("law-licence-terms-ethics")})
        self.assertTrue(any("policy questions give critical" in e for e in validate.check_register(reg(f))))

    def test_confirmed_on_secondary_quote_only_fails(self):
        f = finding(evidence=[{"kind": "quote", "ref": "blog", "quote": "x", "tier": "secondary", "date": "2026-10-14"}])
        self.assertTrue(any("no primary evidence" in e for e in validate.check_register(reg(f))))

    def test_out_of_scope_dismissal_needs_consequence(self):
        f = finding(status="dismissed", dismissal_reason="Out of scope for the MVP")
        self.assertTrue(any("out of scope" in e for e in validate.check_register(reg(f))))
        f["out_of_scope_consequence"] = "Without BFT the relay can forge ordering; accepted by owner"
        self.assertEqual(validate.check_register(reg(f)), [])

    def test_quarantine_must_point_at_findings(self):
        r = reg(finding(), quarantine=[{"locator": "L3", "text": "t", "finding_ids": ["F-999"], "reason": "r"}])
        self.assertTrue(any("unknown finding F-999" in e for e in validate.check_register(r)))

    def test_gates(self):
        g = validate.gates(reg(finding(), finding(id="F-002", severity={"tier": "high", "answers": answers("production-failure")}, disposition=None)))
        self.assertEqual(g["blocking"], ["F-001"])
        self.assertEqual(g["needs_disposition"], ["F-002"])


if __name__ == "__main__":
    unittest.main()
