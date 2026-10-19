"""Write content-addressed snapshots of the historical tabs: ops/blobs, ops/snapshots/<sha>, ops/index.json.

Only historical (git-derived) data goes in here. Runtime telemetry is ``runtime.py`` and never enters a manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .collect import COLLECTOR_VERSION, GitSource, WorkTreeSource, _git, collect_all

SCHEMA = 1
REPO_ROOT = Path(__file__).resolve().parents[2]


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def put_blob(out: Path, obj) -> str:
    data = canonical(obj)
    h = hashlib.sha256(data).hexdigest()
    p = out / "blobs" / f"{h}.json"
    if not p.exists():
        _atomic(p, data)
    return h


def build_viewer(out: Path) -> Path:
    """The dolls viewer with no embedded model: it loads ?model=<url>. Built from the skill template."""
    skill = REPO_ROOT / "skills" / "mermaid-nesting-dolls"
    tpl = (skill / "assets" / "template.html").read_text(encoding="utf-8")
    lib = (skill / "assets" / "vendor" / "mermaid.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    html = tpl.replace("/*__MERMAID__*/", lib).replace("__MODEL_JSON__", "")
    dest = out / "viewer.html"
    if not dest.exists() or dest.read_text(encoding="utf-8") != html:
        _atomic(dest, html.encode("utf-8"))
    return dest


def install_shell(out: Path) -> None:
    """Copy the static shell next to the data, unless it is already there."""
    src = REPO_ROOT / "ops" / "shell" / "index.html"
    dest = out / "shell" / "index.html"
    if src.exists() and src.resolve() != dest.resolve():
        _atomic(dest, src.read_bytes())


def _commit_meta(repo: Path, sha: str) -> dict:
    out = _git(repo, "log", "-1", "--format=%H%x1f%cI%x1f%s", sha).decode("utf-8", "replace").strip()
    h, d, s = (out.split("\x1f") + ["", ""])[:3]
    return {"sha": h, "date": d, "subject": s}


def snapshot(repo: Path, sha: str, out: Path, worktree: bool = False) -> dict:
    """Build (or find) the snapshot for one commit; returns its index entry. Idempotent per sha."""
    meta = _commit_meta(repo, "HEAD" if worktree else sha)
    snap_id = "worktree" if worktree else meta["sha"]
    mpath = out / "snapshots" / snap_id / "manifest.json"
    if mpath.exists() and not worktree:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    else:
        src = WorkTreeSource(repo) if worktree else GitSource(repo, meta["sha"])
        tabs_out, tabs = {}, collect_all(src)
        for name, tab in tabs.items():
            entry: dict = {"available": tab["available"]}
            if not tab["available"]:
                entry["reason"] = tab["reason"]
            else:
                entry["summary"] = tab["summary"]
                if name == "architecture":
                    models = []
                    for it in tab["items"]:
                        if "model" in it:
                            it["model_blob"] = put_blob(out, it.pop("model"))
                            models.append(it["model_blob"])
                    entry["model_blobs"] = models
            entry["blob"] = put_blob(out, tab)
            tabs_out[name] = entry
        manifest = {
            "schema": SCHEMA, "sha": snap_id, "date": meta["date"], "subject": meta["subject"],
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "collector_version": COLLECTOR_VERSION, "kind": "historical", "tabs": tabs_out,
        }
        _atomic(mpath, json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
    # latest stage event, from the dev_journey blob of this very snapshot
    latest = None
    dj = manifest["tabs"].get("dev_journey", {})
    if dj.get("available"):
        evs = json.loads((out / "blobs" / f"{dj['blob']}.json").read_text(encoding="utf-8")).get("events", [])
        latest = evs[-1] if evs else None
    n = 0 if worktree else int(_git(repo, "rev-list", "--count", manifest["sha"]).strip() or 0)
    return {"sha": manifest["sha"], "date": manifest["date"], "subject": manifest["subject"], "n": n,
            "tabs": {k: manifest["tabs"][k]["available"] for k in sorted(manifest["tabs"])}, "latest_stage_event": latest}


def update_index(out: Path, entries: list[dict]) -> dict:
    ip = out / "index.json"
    idx = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else {"schema": SCHEMA, "commits": []}
    by = {c["sha"]: c for c in idx["commits"]}
    for e in entries:
        if e["sha"] != "worktree":
            by[e["sha"]] = e
    idx["commits"] = sorted(by.values(), key=lambda c: (c["date"], c.get("n", 0)), reverse=True)
    _atomic(ip, json.dumps(idx, indent=1).encode("utf-8"))
    return idx


def bundle(repo: Path, sha: str = "HEAD", out: Path = Path("ops"), backfill: int = 0, worktree: bool = False,
           viewer: bool = True) -> list[dict]:
    repo = Path(repo).resolve()
    out = Path(out)
    if not out.is_absolute():
        out = repo / out
    shas = [sha]
    if backfill > 0 and not worktree:
        shas = _git(repo, "rev-list", f"-n{backfill}", sha).decode().split()[::-1]
    entries = [snapshot(repo, s, out, worktree) for s in shas]
    update_index(out, entries)
    if viewer:
        build_viewer(out)
    install_shell(out)
    return entries
