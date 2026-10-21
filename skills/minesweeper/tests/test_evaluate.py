import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import evaluate  # noqa: E402


def write_case(run: Path, case_id: str, findings: list) -> None:
    d = run / case_id
    d.mkdir()
    (d / "register.json").write_text(json.dumps({"findings": findings}))


class CleanIntegrationScoring(unittest.TestCase):
    CASE = {"id": "clean-int", "kind": "integration", "_lens": None, "expect": {"none_from_lens": True}}

    def score(self, findings, crashed=False):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            if crashed:
                (run / "clean-int").mkdir()
            else:
                write_case(run, "clean-int", findings)
            return evaluate.score_dir(run, {"clean-int": self.CASE}, {})["integration"]

    def test_no_findings_is_not_an_alarm(self):
        s = self.score([])
        self.assertEqual((s["clean"], s["alarm"]), (1, 0))

    def test_low_finding_is_not_an_alarm(self):
        s = self.score([{"trap_id": "x", "status": "plausible", "severity": {"tier": "low"}}])
        self.assertEqual(s["alarm"], 0)

    def test_finding_above_low_is_an_alarm(self):
        s = self.score([{"trap_id": "x", "status": "confirmed", "severity": {"tier": "high"}}])
        self.assertEqual(s["alarm"], 1)

    def test_dismissed_finding_is_not_an_alarm(self):
        s = self.score([{"trap_id": "x", "status": "dismissed", "severity": {"tier": "critical"}}])
        self.assertEqual(s["alarm"], 0)

    def test_crashed_run_counts_as_alarm(self):
        s = self.score([], crashed=True)
        self.assertEqual((s["clean"], s["alarm"], s["missing"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
