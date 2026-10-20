"""Shared harness for SFN-06 (lsf lite) acceptance tests.

Public interfaces only: `python3 skills/lsf/scripts/lsf.py ...` via subprocess in tmp git repos with HOME
redirected, HTTP against `lsf serve --port N`, file contents, static checks of the shipped files.

Clarifications assumed (literal readings; see the author's report):
  * LSF_NOW=<ISO UTC, e.g. 2026-10-20T10:00:00Z> overrides the clock for every command (events, budget, status).
  * `--root DIR` is accepted after the sub-command (and its arguments).
  * profile.json: {"session_minutes", "phases": [{"id","group"}...], "weights": {"align","review","build"},
    "checkpoints": {phase: bool}, "editor", "workspace_root"}.
  * `lsf budget --json`: {"groups": {"align": {"planned_minutes","actual_minutes","percent_of_plan","flag"}...},
    "waiting_on_human_minutes": N}; unmeasured actual is null or "not measured".
  * `lsf bundle --json`: {"tabs": {<tab>: {"available", "items"|"reason"}}, ...}; tab names equal
    factory.ops.collect.TABS where both implement, plus "docs". Tolerant lookup (any depth <= 3) is used.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LSF = REPO / "skills" / "lsf" / "scripts" / "lsf.py"
SKILL = REPO / "skills" / "lsf"
PY = sys.executable
T0 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
PHASES = ["0-intake", "1-sweep", "2-research", "3-experiments", "4-prd", "5-evals", "6-decide",
          "7-implement", "8-qa", "9-review", "10-docs"]
GROUP = {**{p: "align" for p in PHASES[:7]}, "7-implement": "build", "8-qa": "build",
         "9-review": "review", "10-docs": "review"}
CHECKPOINTED = PHASES[:7]


def at(minutes: float = 0) -> str:
    return (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def require_lsf():
    if not LSF.is_file():
        pytest.fail(f"{LSF} does not exist yet (SFN-06 not implemented)", pytrace=False)


def clean_env(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SF_", "LSF_", "CLAUDE_", "PYTEST_")) and k != "PYTHONPATH"}
    env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1", LANG="C.UTF-8", **extra)
    return env


def walk(obj):
    """Yield every dict inside a JSON value."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def find_key(obj, key, depth=0, maxdepth=3):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        if depth < maxdepth:
            for v in obj.values():
                r = find_key(v, key, depth + 1, maxdepth)
                if r is not None:
                    return r
    elif isinstance(obj, list) and depth < maxdepth:
        for v in obj:
            r = find_key(v, key, depth + 1, maxdepth)
            if r is not None:
                return r
    return None


class Rig:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.home = tmp / "home"
        self.repo.mkdir()
        self.home.mkdir()
        self.env = clean_env(self.home)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        (self.repo / "README.md").write_text("# fixture\n")
        self.commit("README.md", "first")

    # ---- git
    def git(self, *a, cwd=None):
        p = subprocess.run(["git", *a], cwd=str(cwd or self.repo), capture_output=True, text=True, env=self.env)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip()

    def commit(self, path, msg):
        self.git("add", "--", *([path] if isinstance(path, str) else path))
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            p.write_bytes(text)
        else:
            p.write_text(text)
        return p

    # ---- lsf
    def _env(self, now, env):
        e = dict(self.env)
        if now is not None:
            e["LSF_NOW"] = now if isinstance(now, str) else at(now)
        e.update(env or {})
        return e

    def run(self, *args, now=None, env=None, input=None, cwd=None, timeout=20):
        require_lsf()
        return subprocess.run([PY, str(LSF), *map(str, args)], cwd=str(cwd or self.repo), env=self._env(now, env),
                              input=input, capture_output=True, text=True, timeout=timeout)

    def popen(self, *args, now=None, env=None):
        require_lsf()
        return subprocess.Popen([PY, str(LSF), *map(str, args)], cwd=str(self.repo), env=self._env(now, env),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def init(self, *args, now=0):
        p = self.run("init", *args, now=now)
        assert p.returncode == 0, p.stdout + p.stderr
        return p

    # ---- state readers
    @property
    def lsf_dir(self):
        return self.repo / ".lsf"

    def events(self):
        f = self.lsf_dir / "events.jsonl"
        if not f.is_file():
            return []
        return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]

    def phase_events(self, name):
        return [e for e in self.events() if e.get("phase") == name or e.get("stage") == name]

    def profile(self):
        return json.loads((self.lsf_dir / "profile.json").read_text())

    def edit_profile(self, fn):
        p = self.profile()
        fn(p)
        (self.lsf_dir / "profile.json").write_text(json.dumps(p, indent=2))

    def stop_lines(self):
        f = self.lsf_dir / "stops.jsonl"
        return f.read_text().splitlines() if f.is_file() else []

    def hitl(self, now=None):
        p = self.run("hitl", "status", "--json", now=now)
        try:
            data = json.loads(p.stdout)
        except json.JSONDecodeError:
            data = None
        return p, data

    def stop(self, name, now=None):
        _, data = self.hitl(now)
        for d in walk(data):
            if d.get("name") == name:
                return d
        return None

    def budget(self, now):
        p = self.run("budget", "--json", now=now)
        assert p.returncode == 0, p.stdout + p.stderr
        return json.loads(p.stdout)

    def phase(self, verb, name, now, *extra):
        return self.run("phase", verb, name, *extra, now=now)

    def bundle(self, now=None):
        p = self.run("bundle", "--json", now=now, timeout=30)
        assert p.returncode == 0, p.stdout + p.stderr
        return json.loads(p.stdout)


def group_of(budget, name):
    g = budget.get("groups", budget)
    if isinstance(g, dict):
        return g[name]
    for x in g:
        if name in (x.get("group"), x.get("name")):
            return x
    raise KeyError(name)


def minutes(d, prefix):
    for k, v in d.items():
        if k.startswith(prefix) and isinstance(v, (int, float)) and not isinstance(v, bool):
            return v / 60 if k.endswith(("_s", "_sec", "_seconds")) else v
    return None


def raw(d, prefix):
    for k, v in d.items():
        if k.startswith(prefix):
            return v
    return None


def waiting(budget):
    for d in walk(budget):
        for k, v in d.items():
            if "wait" in k.lower():
                if isinstance(v, dict):
                    v = next((x for x in v.values() if isinstance(x, (int, float))), None)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return v / 60 if k.lower().endswith(("_s", "_sec", "_seconds")) else v
    return None


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.fixture
def inited(rig):
    rig.init()
    return rig


# ------------------------------------------------------------------ HTTP server harness
class Server:
    def __init__(self, rig: Rig, *extra):
        require_lsf()
        self.rig = rig
        self.port = free_port()
        self.out = []
        self.proc = subprocess.Popen([PY, str(LSF), "serve", "--port", str(self.port), "--root", str(rig.repo), *extra],
                                     cwd=str(rig.repo), env=rig.env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=self._pump, daemon=True).start()
        self.token = None
        end = time.time() + 15
        while time.time() < end and self.token is None:
            m = re.search(r"#token=([A-Za-z0-9_\-]+)", "".join(self.out))
            if m:
                self.token = m.group(1)
            elif self.proc.poll() is not None:
                break
            else:
                time.sleep(0.05)
        if self.token is None:
            self.stop()
            pytest.fail("serve did not print http://127.0.0.1:PORT/#token=... :\n" + "".join(self.out), pytrace=False)
        end = time.time() + 10
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.5).close()
                break
            except OSError:
                time.sleep(0.05)

    def _pump(self):
        for line in self.proc.stdout:
            self.out.append(line)

    def output(self):
        return "".join(self.out)

    def req(self, method, path, body=None, headers=None, host="default"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", f"127.0.0.1:{self.port}" if host == "default" else host)
        for k, v in (headers or {}).items():
            c.putheader(k, v)
        data = body.encode() if isinstance(body, str) else body
        if data is not None:
            c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        out = (r.status, {k.lower(): v for k, v in r.getheaders()}, r.read())
        c.close()
        return out

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def release(self, name, note="", token="default", extra_headers=None, host="default"):
        h = {"Content-Type": "application/json"}
        if token == "default":
            token = self.token
        if token is not None:
            h["X-LSF-Token"] = token
        h.update(extra_headers or {})
        return self.req("POST", "/api/hitl/release", json.dumps({"name": name, "note": note}), h, host=host)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
