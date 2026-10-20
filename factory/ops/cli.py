from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import bundle as B
from . import runtime as R
from .collect import TABS

BEGIN, END = "# >>> sf ops autobundle >>>", "# <<< sf ops autobundle <<<"
BEHIND = 4  # `status` exit code when the snapshot is behind HEAD or missing


def _git(repo: Path, *args: str) -> str | None:
    """stdout of a git command, or None when it fails (not a repository, no commit, ...)."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _need_commit(repo: Path) -> str | None:
    head = _git(repo, "rev-parse", "--verify", "-q", "HEAD")
    if head is None:
        print(f"error: {repo} is not a git repository with at least one commit", file=sys.stderr)
    return head


def _init(dirp: Path) -> int:
    dirp = dirp.resolve()
    if _need_commit(dirp) is None:
        return 2
    out = dirp / "ops"
    for rel, data in (("config.json", b"{}\n"), ("events.jsonl", b"")):
        path = out / rel
        B._check_inside(path, out)
        if not path.exists():
            B._atomic(path, data, out)
    es = B.bundle(dirp, "HEAD", out)
    man = json.loads((out / "snapshots" / es[-1]["sha"] / "manifest.json").read_text(encoding="utf-8"))
    for name in TABS:
        t = man["tabs"].get(name, {})
        print(f"{name}: available" if t.get("available") else f"{name}: not available: {t.get('reason', 'unknown')}")
    return 0


def _backfill(repo: Path, limit: int) -> int:
    repo = repo.resolve()
    if _need_commit(repo) is None:
        return 2
    out = repo / "ops"
    shas = (_git(repo, "rev-list", f"-n{max(limit, 0)}", "HEAD") or "").split()
    built = skipped = 0
    failed: list[str] = []
    for sha in shas:
        if (out / "snapshots" / sha / "manifest.json").exists():
            skipped += 1
            continue
        try:
            B.bundle(repo, sha, out, viewer=False)
            built += 1
        except Exception as e:  # noqa: BLE001 - one bad commit must not stop the rest
            failed.append(f"{sha[:12]} {type(e).__name__}: {' '.join(str(e).split())[:160]}")
    print(f"built {built}, skipped {skipped}, failed {len(failed)}")
    for f in failed:
        print(f"failed: {f}")
    return 1 if failed else 0


def _status(repo: Path, as_json: bool) -> int:
    repo = repo.resolve()
    head = _need_commit(repo)
    if head is None:
        return 2
    out = repo / "ops"
    snap = None
    try:
        for c in json.loads((out / "index.json").read_text(encoding="utf-8")).get("commits", []):
            if (out / "snapshots" / c["sha"] / "manifest.json").exists():
                snap = c["sha"]
                break
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    n = _git(repo, "rev-list", "--count", f"{snap}..HEAD") if snap else None
    behind = int(n) if n and n.isdigit() else None
    try:
        events = sum(1 for ln in (out / "events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())
    except OSError:
        events = 0
    st = {"head": head, "snapshot": snap, "behind": behind, "events": events}
    if as_json:
        print(json.dumps(st))
    else:
        print(f"head: {head}\nsnapshot: {snap}\nbehind: {behind}\nevents: {events}")
    return 0 if behind == 0 else BEHIND


def _hook_path(repo: Path) -> Path | None:
    p = _git(repo, "rev-parse", "--git-path", "hooks")
    if p is None:
        return None
    hooks = Path(p)
    return (hooks if hooks.is_absolute() else repo / hooks) / "post-commit"


def _block() -> str:
    root = Path(__file__).resolve().parents[2]
    return f"""{BEGIN}
__sf_autobundle() {{
  T=""; command -v timeout >/dev/null 2>&1 && T="timeout 120"
  if command -v sf >/dev/null 2>&1; then $T sf ops bundle --sha HEAD
  else PYTHONPATH='{root}' $T '{sys.executable}' -m factory.cli ops bundle --sha HEAD; fi
}}
( __sf_autobundle ) >/dev/null 2>&1 &
{END}
"""


def _autobundle(action: str, repo: Path) -> int:
    repo = repo.resolve()
    hook = _hook_path(repo) if _git(repo, "rev-parse", "--git-dir") is not None else None
    if hook is None:
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 2
    if hook.is_symlink():
        print(f"error: refusing to touch a symlinked hook: {hook}", file=sys.stderr)
        return 1
    text = hook.read_text(encoding="utf-8") if hook.exists() else None
    has = text is not None and BEGIN in text and END in text
    if action == "status":
        print(f"installed: {hook}" if has else f"not installed: {hook}")
        return 0
    if action == "install":
        if not has:
            if text is None:
                new = "#!/bin/sh\n" + _block()
            else:
                new = text + ("" if text.endswith("\n") or not text else "\n") + ("\n" if text else "") + _block()
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text(new, encoding="utf-8")
        os.chmod(hook, hook.stat().st_mode | 0o111)
        print(f"installed: {hook}")
        return 0
    if has:  # uninstall: drop the block and the blank line install put before it
        a, b = text.index(BEGIN), text.index(END) + len(END)
        before, after = text[:a].rstrip("\n"), text[b:].lstrip("\n")
        rest = before + ("\n" if before and after else "") + after
        rest = rest + ("\n" if rest and not rest.endswith("\n") else "")
        if rest.strip() in ("", "#!/bin/sh"):
            hook.unlink()
        else:
            hook.write_text(rest, encoding="utf-8")
    print(f"uninstalled: {hook}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m factory.ops", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bundle", help="snapshot the historical tabs at a commit")
    b.add_argument("--repo", default=".")
    b.add_argument("--sha", default="HEAD")
    b.add_argument("--out", default="ops")
    b.add_argument("--backfill", type=int, default=0, help="also build the last N commits ending at --sha")
    b.add_argument("--worktree", action="store_true", help="read the working tree instead of a commit")
    b.add_argument("--no-viewer", action="store_true")
    i = sub.add_parser("init", help="create ops/config.json and events.jsonl, install the viewer, bundle HEAD")
    i.add_argument("--dir", default=".", help="the project (repository) directory; output goes to DIR/ops")
    bf = sub.add_parser("backfill", help="bundle the current branch's commits that have no snapshot yet")
    bf.add_argument("--limit", type=int, default=500)
    bf.add_argument("--repo", default=".")
    st = sub.add_parser("status", help="how far the newest snapshot is behind HEAD (exit 4 when behind or none)")
    st.add_argument("--repo", default=".")
    st.add_argument("--json", action="store_true")
    ab = sub.add_parser("autobundle", help="manage the post-commit hook block that runs `sf ops bundle --sha HEAD`")
    ab.add_argument("action", choices=["install", "uninstall", "status"])
    ab.add_argument("--repo", default=".")
    r = sub.add_parser("runtime", help="measure runtime telemetry now")
    r.add_argument("--config", default="ops/config.json")
    r.add_argument("--out", default="ops/runtime.json")
    s = sub.add_parser("serve", help="serve the dashboard read-only and refresh runtime.json")
    s.add_argument("--root", default="ops")
    s.add_argument("--config", default="ops/config.json")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--refresh-seconds", type=float, default=30)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        return _init(Path(a.dir))
    if a.cmd == "backfill":
        return _backfill(Path(a.repo), a.limit)
    if a.cmd == "status":
        return _status(Path(a.repo), a.json)
    if a.cmd == "autobundle":
        return _autobundle(a.action, Path(a.repo))
    if a.cmd == "bundle":
        es = B.bundle(Path(a.repo), a.sha, Path(a.out), a.backfill, a.worktree, not a.no_viewer)
        for e in es:
            avail = sum(e["tabs"].values())
            print(f"{e['sha'][:12]} {e['date']} tabs available {avail}/{len(e['tabs'])}  {e['subject']}")
        return 0
    if a.cmd == "runtime":
        d = R.write_runtime(Path(a.config), Path(a.out))
        m = sum(1 for f in d["figures"].values() if f["measured"])
        print(f"runtime as of {d['as_of']}: {m}/{len(d['figures'])} figures measured -> {a.out}")
        return 0
    R.serve(Path(a.root), Path(a.config), a.host, a.port, a.refresh_seconds)
    return 0
