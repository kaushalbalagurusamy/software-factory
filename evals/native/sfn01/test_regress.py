"""SFN-01 E-14: nothing existing breaks. The existing ops, hitl, CLI-delegation and hook suites must keep passing."""
from __future__ import annotations

import subprocess
import sys

from .conftest import REPO, child_env

EXISTING = [
    "tests/test_ops.py", "tests/test_ops_security.py", "tests/test_hitl.py", "tests/test_cli_tools.py",
    "tests/hooks/test_ledger_hooks.py", "tests/hooks/test_subagent_stop.py",
]


def test_E14_existing_ops_hitl_cli_and_hook_suites_still_pass_unedited():
    r = subprocess.run([sys.executable, "-m", "pytest", *EXISTING, "-q", "-p", "no:cacheprovider", "-x"],
                       cwd=str(REPO), capture_output=True, text=True, env=child_env(), timeout=100)
    assert r.returncode == 0, r.stdout[-2500:] + r.stderr[-500:]


def test_E14_the_listed_existing_test_files_exist():
    for rel in EXISTING:
        assert (REPO / rel).is_file(), rel
