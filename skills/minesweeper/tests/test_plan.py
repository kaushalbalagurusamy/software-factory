import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import plan  # noqa: E402
from common import ROOT, load_yaml  # noqa: E402


class PlanSelectsExpectedLenses(unittest.TestCase):
    """applies_when must load the lens of every trap an integration case expects; a skipped lens
    is a guaranteed miss that no sweep can recover."""

    def test_integration_cases(self):
        cases = sorted((ROOT / "integration").glob("*.yaml"))
        self.assertTrue(cases)
        for path in cases:
            case = load_yaml(path)
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as tmp:
                brief = Path(tmp) / "brief.md"
                brief.write_text(case["brief"])
                p = plan.plan(brief)
                applied = {l["id"] for g in p["groups"].values() for l in g["lenses"]}
                needed = {t.split(".", 1)[0] for t in case["expect"].get("traps", [])}
                needed |= {o.split(".", 1)[0] for o in case["expect"].get("omissions", [])}
                self.assertEqual(needed - applied, set())


if __name__ == "__main__":
    unittest.main()
