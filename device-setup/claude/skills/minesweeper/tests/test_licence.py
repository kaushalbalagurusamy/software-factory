import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from checks import licence  # noqa: E402


class FamilyTest(unittest.TestCase):
    def fam(self, s):
        return licence.family(s)["family"]

    def test_agpl_is_network_copyleft_not_gpl(self):
        self.assertEqual(self.fam("AGPL-3.0-only"), "network-copyleft")

    def test_gpl_is_strong_copyleft(self):
        self.assertEqual(self.fam("GPL-3.0-or-later"), "strong-copyleft")

    def test_lgpl_is_weak(self):
        self.assertEqual(self.fam("LGPL-2.1-only"), "weak-copyleft")

    def test_source_available(self):
        for s in ("SSPL-1.0", "BUSL-1.1", "Elastic-2.0"):
            self.assertEqual(self.fam(s), "source-available", s)

    def test_boost_is_permissive_but_busl_is_not(self):
        self.assertEqual(self.fam("BSL-1.0"), "permissive")
        self.assertEqual(self.fam("BUSL-1.1"), "source-available")

    def test_non_commercial(self):
        self.assertEqual(self.fam("CC-BY-NC-4.0"), "non-commercial")

    def test_permissive(self):
        for s in ("MIT", "Apache-2.0", "BSD-3-Clause", "ISC"):
            self.assertEqual(self.fam(s), "permissive", s)

    def test_missing_licence_is_unknown_not_permissive(self):
        self.assertEqual(self.fam(None), "unknown")

    def test_dual_licence_is_mixed_with_note(self):
        r = licence.family("Elastic-2.0 OR AGPL-3.0-only")
        self.assertEqual(r["family"], "mixed")
        self.assertIn("dual", r["note"])


if __name__ == "__main__":
    unittest.main()
