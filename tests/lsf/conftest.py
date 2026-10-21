"""Helpers: a throwaway git repository and a runner for the lsf CLI (subprocess, like a user)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "skills" / "lsf"
LSF = SKILL / "scripts" / "lsf.py"


def run(repo, *args, env=None, stdin=None):
    e = dict(os.environ)
    e.pop("LSF_EVENTS", None)
    e.pop("SF_EVENTS", None)
    e.update(env or {})
    return subprocess.run([sys.executable, str(LSF), *args, "--root", str(repo)], capture_output=True, text=True,
                          input=stdin, env=e, timeout=60)


def at(t):
    return {"LSF_NOW": "2026-10-20T%s:00Z" % t}


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    for c in (["init", "-q"], ["config", "user.name", "t"], ["config", "user.email", "t@e"],
              ["commit", "-q", "--allow-empty", "-m", "first"]):
        subprocess.run(["git", "-C", str(r)] + c, check=True, capture_output=True)
    return r


def events(repo):
    p = Path(repo) / ".lsf" / "events.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
