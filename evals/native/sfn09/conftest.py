"""SFN-09 harness: reuses the SFN-06 rig/server; adds decision helpers built on the public CLI/HTTP only."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from evals.native.sfn06.conftest import (  # noqa: F401  (re-exported for the test modules)
    LSF, PY, REPO, SKILL, Rig, Server, at, clean_env, free_port, require_lsf, walk,
)

# agent-graph commit before SFN-09; used to author a genuine pre-SFN-09 ledger.
OLD_LSF_COMMIT = "8e612b4ed43887a31131383622efdb84fb19d72e"
STALE = "0" * 64


def canon_hash(question, options, artifacts):
    """The D-2 proposal hash, computed independently. artifacts: list of (path, sha256-or-None)."""
    doc = {"question": question, "options": list(options),
           "artifacts": [{"path": p, "sha256": s} for p, s in artifacts]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ask(rig, name, options=(), artifacts=(), question="Which one?", now=None):
    args = ["hitl", "request", name, "--question", question]
    for a in artifacts:
        args += ["--artifact", a]
    for o in options:
        args += ["--option", o]
    return rig.run(*args, now=now)


def ask_ok(rig, name, options=("Alpha", "Beta"), **kw):
    p = ask(rig, name, options, **kw)
    assert p.returncode == 0, p.stdout + p.stderr
    return p


def answer(rig, name, ans, note="", *extra, now=None):
    args = ["hitl", "release", name, "--answer", ans]
    if note:
        args += ["--note", note]
    return rig.run(*args, *extra, now=now)


def record(rig, name, where, *extra):
    return rig.run("hitl", "recorded", name, "--where", where, *extra)


def apply_(rig, name, evidence, *extra):
    return rig.run("hitl", "applied", name, "--evidence", evidence, *extra)


def state_of(rig, name):
    s = rig.stop(name)
    return None if s is None else s.get("state")


def out(p):
    return p.stdout + p.stderr


def to_applied(rig, name="d", options=("Alpha", "Beta"), choose="Alpha"):
    """Drive one decision through asked -> answered -> recorded -> applied via the CLI."""
    rig.write("docs/rec.md", "recorded here\n")
    ask_ok(rig, name, options)
    assert answer(rig, name, choose).returncode == 0
    assert record(rig, name, "docs/rec.md").returncode == 0
    assert apply_(rig, name, "tests pass").returncode == 0


def post_release(srv, body, token="default"):
    h = {"Content-Type": "application/json"}
    tok = srv.token if token == "default" else token
    if tok is not None:
        h["X-LSF-Token"] = tok
    return srv.req("POST", "/api/hitl/release", body if isinstance(body, str) else json.dumps(body), h)


def api_state(srv):
    s, _, b = srv.get("/api/state")
    assert s == 200
    return json.loads(b.decode())


def api_stop(srv, name):
    for d in walk(api_state(srv)):
        if d.get("name") == name:
            return d
    return None


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.fixture
def inited(rig):
    rig.init()
    return rig


@pytest.fixture
def serve():
    """Factory: serve(rig, *extra) -> Server, all stopped at teardown."""
    made = []

    def make(rig, *extra):
        s = Server(rig, *extra)
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop()


@pytest.fixture
def old_lsf(tmp_path):
    """The pre-SFN-09 skill tree exported from git, to author a genuine old-format ledger."""
    d = Path(tempfile.mkdtemp(prefix="oldlsf-", dir=str(tmp_path)))
    tar = subprocess.run(["git", "archive", OLD_LSF_COMMIT, "skills/lsf"], cwd=str(REPO), capture_output=True)
    if tar.returncode != 0:
        pytest.skip("pinned pre-SFN-09 commit not available in this clone")
    subprocess.run(["tar", "-x", "-C", str(d)], input=tar.stdout, check=True)
    return d / "skills" / "lsf" / "scripts" / "lsf.py"
