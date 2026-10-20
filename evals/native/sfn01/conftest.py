"""Shared helpers for the SFN-01 acceptance tests. Public interfaces only: emit(), the sf CLI, files on disk."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SF_CODE = "import sys; from factory.cli import main; sys.exit(main(sys.argv[1:]))"
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t"]


def child_env(**extra) -> dict:
    env = dict(os.environ)
    env.pop("SF_EVENTS", None)
    env["PYTHONPATH"] = str(REPO)
    env.update(extra)
    return env


def git(repo, *args, env=None) -> str:
    p = subprocess.run(["git", "-C", str(repo), *GIT_ID, *args], capture_output=True, text=True, env=env)
    assert p.returncode == 0, f"git {args}: {p.stderr}"
    return p.stdout.strip()


def commit(repo, msg="c", files=None, date=None) -> str:
    """Commit (optionally with files {relpath: text}); returns the new HEAD sha."""
    for rel, text in (files or {}).items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        git(repo, "add", "--", rel)
    env = None
    if date:
        env = dict(os.environ, GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date)
    git(repo, "commit", "-q", "--allow-empty", "-m", msg, env=env)
    return git(repo, "rev-parse", "HEAD")


def sf(cwd, *args, env=None, timeout=60, stdin=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", SF_CODE, *args], cwd=str(cwd), capture_output=True, text=True,
                          env=env or child_env(), timeout=timeout, input=stdin)


def read_events(repo) -> list[dict]:
    p = Path(repo) / "ops" / "events.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def snapshot_tree(root) -> dict:
    """{relpath: bytes} of every regular file under root, for byte-identity checks."""
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(autouse=True)
def _events_on(monkeypatch):
    monkeypatch.delenv("SF_EVENTS", raising=False)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "init", {"README.md": "hello\n"})
    return r


@pytest.fixture
def bare_dir(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    return d


def emit_fn():
    """Imported lazily so collection succeeds before the feature exists."""
    from factory.ops.events import emit
    return emit
