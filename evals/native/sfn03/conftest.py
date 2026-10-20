"""Shared helpers for the SFN-03 acceptance tests. Public interfaces only: collectors, CLIs, stores, files on disk."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
HARNESS = Path(__file__).with_name("shell_harness.js")
SHELL = REPO / "ops" / "shell" / "index.html"
SF_CODE = "import sys; from factory.cli import main; sys.exit(main(sys.argv[1:]))"
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@t"]
TABS_SHELL = ["overview", "ops", "architecture", "research", "experiments", "adrs", "prd", "langfuse",
              "evals", "journey", "git", "hitl"]


def env(**extra) -> dict:
    e = dict(os.environ)
    e.pop("SF_EVENTS", None)
    e["PYTHONPATH"] = str(REPO)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e.update(extra)
    return e


def git(repo, *args) -> str:
    p = subprocess.run(["git", "-C", str(repo), *GIT_ID, *args], capture_output=True, text=True)
    assert p.returncode == 0, f"git {args}: {p.stderr}"
    return p.stdout.strip()


def write(repo, files: dict) -> None:
    for rel, text in files.items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def commit(repo, files: dict | None = None, msg="c") -> str:
    write(repo, files or {})
    for rel in (files or {}):
        git(repo, "add", "--", rel)
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def mkrepo(tmp_path, files: dict | None = None, name="repo") -> Path:
    r = Path(tmp_path) / name
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, {"README.md": "hello\n", **(files or {})}, "init")
    return r


def run(repo, *args, module="factory.ops", extra_env=None, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", module, *args], cwd=str(repo), capture_output=True, text=True,
                          env=env(**(extra_env or {})), timeout=timeout)


def sf(repo, *args, extra_env=None, timeout=90) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", SF_CODE, *args], cwd=str(repo), capture_output=True, text=True,
                          env=env(**(extra_env or {})), timeout=timeout)


def collect(repo, tab, sha="HEAD"):
    from factory.ops import collect as C
    return C.COLLECTORS[tab](C.GitSource(Path(repo), sha))


def find_key(obj, key):
    """Every value stored under `key` anywhere in a JSON-like structure."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out += find_key(v, key)
    elif isinstance(obj, list):
        for v in obj:
            out += find_key(v, key)
    return out


def dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def runtime(repo, config: dict | None = None) -> dict:
    """Run `python -m factory.ops runtime` in the repo and return the written runtime.json."""
    if config is not None:
        write(repo, {"ops/config.json": json.dumps(config)})
    elif not (Path(repo) / "ops" / "config.json").exists():
        write(repo, {"ops/config.json": "{}"})
    p = run(repo, "runtime", "--config", "ops/config.json", "--out", "ops/runtime.json")
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads((Path(repo) / "ops" / "runtime.json").read_text())


def tab_blob(repo, sha, tab, out="ops") -> dict:
    out = Path(repo) / out
    man = json.loads((out / "snapshots" / sha / "manifest.json").read_text())
    t = man["tabs"][tab]
    if not t["available"]:
        return t
    return json.loads((out / "blobs" / f"{t['blob']}.json").read_text())


def tree(root) -> dict:
    root = Path(root)
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def shell_text(repo, tab: str, ops="ops", with_runtime=True) -> str:
    """Run the real dashboard shell script in node against the files under repo/ops; return all rendered text."""
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    files = {}
    base = Path(repo) / ops
    for p in base.rglob("*.json"):
        rel = str(p.relative_to(base))
        if rel == "runtime.json" and not with_runtime:
            continue
        files[rel] = json.loads(p.read_text())
    cfg = Path(repo) / ".shell-cfg.json"
    cfg.write_text(json.dumps({"hash": f"#/{tab}", "files": files}))
    p = subprocess.run(["node", str(HARNESS), str(SHELL), str(cfg)], capture_output=True, text=True, timeout=15)
    cfg.unlink()
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)["text"]


def onepager(journeys, pad_after_title=0, title="# Core PRD") -> str:
    """journeys: list of (name, slices_or_None, steps). Blank padding goes after the title."""
    lines = [title] + [""] * pad_after_title
    for name, slices, steps in journeys:
        lines += ["", f"## Journey: {name}"]
        if slices is not None:
            lines.append("Slices: " + ", ".join(slices))
        lines += [f"- {s}" for s in steps]
    return "\n".join(lines) + "\n"


def onepager_with_lines(total: int) -> str:
    j = [("Last journey", ["s1"], ["only step"])]
    n = len(onepager(j).splitlines())
    page = onepager(j, pad_after_title=total - n)
    assert len(page.splitlines()) == total
    return page


@pytest.fixture(autouse=True)
def _events_on(monkeypatch):
    monkeypatch.delenv("SF_EVENTS", raising=False)
