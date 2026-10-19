"""Locate the Unity repository for tests that need the Unity compiler.

UNITY_REPO selects the checkout. Default: a sibling ``unity`` directory of this
repository; for a git worktree nested elsewhere, ~/Projects/unity is tried next.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _locate_unity_repo() -> Path:
    explicit = os.environ.get("UNITY_REPO")
    if explicit:
        return Path(explicit).expanduser()
    for candidate in (REPO_ROOT.parent / "unity", Path.home() / "Projects" / "unity"):
        if candidate.is_dir():
            return candidate
    return REPO_ROOT.parent / "unity"


UNITY_REPO = _locate_unity_repo()
UNITY_LEDGER_DIR = UNITY_REPO / "examples" / "ledger"
LEDGER_PY = UNITY_LEDGER_DIR / "ledger.py"
LEDGER_GO = UNITY_LEDGER_DIR / "ledger.go"


def unity_problem() -> str | None:
    """Return why Unity cannot be used by tests, or None if it can."""
    if importlib.util.find_spec("compiler") is None:
        return "the Unity compiler package ('compiler') is not importable; run scripts/dev-env.sh"
    if not LEDGER_PY.is_file():
        return f"Unity example not found at {LEDGER_PY}; set UNITY_REPO to a Unity checkout"
    return None
