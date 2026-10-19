"""The labelled-minimal-fixture demonstration must keep behaving as documented (bounded: it runs a few subprocesses)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "dogfood-limits" / "run_demo.py"


def test_demo_runs_every_step_as_stated(tmp_path):
    r = subprocess.run([sys.executable, str(DEMO), "--out", str(tmp_path / "out")], cwd=REPO,
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL STEPS AS EXPECTED" in r.stdout
    assert "FAIL " not in r.stdout
    assert (tmp_path / "out" / "explorer.html").stat().st_size > 1_000_000
