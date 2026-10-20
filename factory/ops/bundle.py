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

from .collect import COLLECTOR_VERSION, GitSource, WorkTreeSource, _git, collect_all, unavailable

SCHEMA = 1
REPO_ROOT = Path(__file__).resolve().parents[2]


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _check_inside(path: Path, root: Path) -> None:
    """Refuse to write through a symlink or outside the output root (a planted link must not redirect a write)."""
    root_abs = Path(os.path.abspath(root))
    target = Path(os.path.abspath(path))
    if root_abs != target and root_abs not in target.parents:
        raise ValueError(f"refusing to write outside the output root: {path}")
    cur = target
    while True:
        if cur.is_symlink():
            raise ValueError(f"refusing to write through a symlink: {cur}")
        if cur == root_abs or cur.parent == cur:
            break
        cur = cur.parent


def _atomic(path: Path, data: bytes, root: Path) -> None:
    _check_inside(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_inside(path, root)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def put_blob(out: Path, obj) -> str:
    data = canonical(obj)
    h = hashlib.sha256(data).hexdigest()
    p = out / "blobs" / f"{h}.json"
    if not p.exists():
        _atomic(p, data, out)
    return h


def build_viewer(out: Path) -> Path:
    """The dolls viewer with no embedded model: it loads ?model=<url>. Built from the skill template."""
    skill = REPO_ROOT / "skills" / "mermaid-nesting-dolls"
    tpl = (skill / "assets" / "template.html").read_text(encoding="utf-8")
    lib = (skill / "assets" / "vendor" / "mermaid.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    html = tpl.replace("/*__MERMAID__*/", lib).replace("__MODEL_JSON__", "")
    dest = out / "viewer.html"
    if not dest.exists() or dest.read_text(encoding="utf-8") != html:
        _atomic(dest, html.encode("utf-8"), out)
    return dest


def install_shell(out: Path) -> None:
    """Copy the static shell next to the data, unless it is already there."""
    src = REPO_ROOT / "ops" / "shell" / "index.html"
    dest = out / "shell" / "index.html"
    if src.exists() and src.resolve() != dest.resolve():
        _atomic(dest, src.read_bytes(), out)


def _commit_meta(repo: Path, sha: str) -> dict:
    out = _git(repo, "log", "-1", "--format=%H%x1f%cI%x1f%s", sha).decode("utf-8", "replace").strip()
    h, d, s = (out.split("\x1f") + ["", ""])[:3]
    return {"sha": h, "date": d, "subject": s}


def _when(text):
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


LOCAL_LOG_BYTES = 8_000_000


def _local_events(repo: Path, cut) -> list[dict]:
    """Events of the untracked working-tree log (C-50) stamped no later than the commit's committer date."""
    path = Path(repo) / "ops" / "events.jsonl"
    try:
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            return []
        with open(path, "rb") as f:
            text = f.read(LOCAL_LOG_BYTES).decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for ln in text.splitlines():
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        when = _when(e.get("at")) if isinstance(e, dict) else None
        if when is not None and (cut is None or when <= cut):
            out.append(e)
    return out


def _stage_events(tab: dict, commit_date: str, worktree: bool, repo: Path | None = None, tracked: bool = True) -> dict:
    """Stage events are history: use the committed log, or the local log when the commit does not track it, drop
    those stamped after the commit, and report none as unavailable, not an empty table."""
    cut = None if worktree else _when(commit_date)
    source = "commit"
    if not worktree and not tracked and repo is not None:
        local = _local_events(repo, cut)
        if local:
            if not tab["available"]:
                tab = {"available": True, "summary": {"count": 0, "slices": 0}, "items": [], "events": []}
            tab["events"], source = local, "local log"
    if not tab["available"]:
        return unavailable(f"no stage events recorded ({tab['reason']})")
    keep = [e for e in tab["events"] if "error" in e or cut is None or (_when(e.get("at")) or cut) <= cut]
    if not any("error" not in e for e in keep):
        return unavailable("no stage events recorded")
    tab["events"] = keep
    tab["events_source"] = source
    tab["summary"]["events"] = len(keep)
    return tab


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
        tabs["dev_journey"] = _stage_events(tabs["dev_journey"], meta["date"], worktree, repo, src.text("ops/events.jsonl") is not None)
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
        _atomic(mpath, json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"), out)
    # latest stage event, from the dev_journey blob of this very snapshot
    latest = None
    dj = manifest["tabs"].get("dev_journey", {})
    if dj.get("available"):
        evs = json.loads((out / "blobs" / f"{dj['blob']}.json").read_text(encoding="utf-8")).get("events", [])
        latest = evs[-1] if evs else None
    n = 0 if worktree else int(_git(repo, "rev-list", "--count", manifest["sha"]).strip() or 0)
    return {"sha": manifest["sha"], "date": manifest["date"], "subject": manifest["subject"], "n": n,
            "tabs": {k: manifest["tabs"][k]["available"] for k in sorted(manifest["tabs"])}, "latest_stage_event": latest}


def update_index(out: Path, entries: list[dict], head: str | None = None) -> dict:
    ip = out / "index.json"
    idx = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else {"schema": SCHEMA, "commits": []}
    by = {c["sha"]: c for c in idx["commits"]}
    for e in entries:
        if e["sha"] != "worktree":
            by[e["sha"]] = e
    if head:
        idx["head"] = head  # the commit the latest default (--sha HEAD) bundle ran from
    idx["commits"] = sorted(by.values(), key=lambda c: (c["date"], c.get("n", 0)), reverse=True)
    _atomic(ip, json.dumps(idx, indent=1).encode("utf-8"), out)
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
    update_index(out, entries, entries[-1]["sha"] if sha == "HEAD" and not worktree else None)
    if viewer:
        build_viewer(out)
    install_shell(out)
    return entries
