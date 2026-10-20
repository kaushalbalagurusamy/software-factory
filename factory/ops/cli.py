from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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


def _exclude_events(repo: Path) -> None:
    """List ops/events.jsonl in the repository's local exclude file (never a tracked .gitignore); idempotent."""
    p = _git(repo, "rev-parse", "--git-path", "info/exclude")
    if p is None:
        return
    path = Path(p) if Path(p).is_absolute() else repo / p
    line = "ops/events.jsonl"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if line in (x.strip() for x in text.splitlines()):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + line + "\n", encoding="utf-8")


def _clean_host(url: str) -> str | None:
    """An https URL without userinfo, query or fragment (a password in the URL is never kept); None if not https."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url.strip())
        host = u.hostname
        port = f":{u.port}" if u.port else ""
    except ValueError:
        return None
    if u.scheme.lower() != "https" or not host:
        return None
    return f"https://{host}{port}{u.path.rstrip('/')}"


def _init(dirp: Path, langfuse_host: str | None = None, langfuse_project: str | None = None) -> int:
    dirp = dirp.resolve()
    host = None
    if langfuse_host is not None:
        host = _clean_host(langfuse_host)
        if host is None:
            print("error: --langfuse-host must be an https:// URL", file=sys.stderr)
            return 2
    if _need_commit(dirp) is None:
        return 2
    cfg_path = dirp / "ops" / "config.json"
    cfg = None
    if host is not None:
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
            if not isinstance(cfg, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as e:
            print(f"error: {cfg_path} is not a readable JSON object ({type(e).__name__}); nothing written", file=sys.stderr)
            return 2
    _exclude_events(dirp)
    out = dirp / "ops"
    for rel, data in (("config.json", b"{}\n"), ("events.jsonl", b"")):
        path = out / rel
        B._check_inside(path, out)
        if not path.exists():
            B._atomic(path, data, out)
    if cfg is not None:
        lf = dict(cfg.get("langfuse") or {}) if isinstance(cfg.get("langfuse"), dict) else {}
        lf["host"] = host
        if langfuse_project:
            lf["project"] = langfuse_project
        cfg["langfuse"] = lf
        B._atomic(cfg_path, (json.dumps(cfg, indent=2, sort_keys=True) + "\n").encode("utf-8"), out)
        print(f"langfuse host recorded: {host}")
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
    try:
        indexed = {c["sha"] for c in json.loads((out / "index.json").read_text(encoding="utf-8")).get("commits", [])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        indexed = set()
    for sha in shas:
        if (out / "snapshots" / sha / "manifest.json").exists():
            skipped += 1
            if sha not in indexed:  # a lost index entry: the manifest is there, so re-list it without rebuilding
                try:
                    B.bundle(repo, sha, out, viewer=False)
                except Exception as e:  # noqa: BLE001
                    failed.append(f"{sha[:12]} {type(e).__name__}: {' '.join(str(e).split())[:160]}")
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


SHELLS = {"sh", "bash", "dash", "zsh"}


def _block() -> str:
    root = shlex.quote(str(Path(__file__).resolve().parents[2]))
    py = shlex.quote(sys.executable)
    return f"""{BEGIN}
__sf_autobundle() {{
  top=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  [ -f "$top/ops/config.json" ] || return 0  # only repositories that opted in (sf ops init / autobundle install)
  cd "$top" || return 0
  T=""; command -v timeout >/dev/null 2>&1 && T="timeout 120"
  if command -v sf >/dev/null 2>&1; then $T sf ops bundle --sha HEAD
  elif [ -d {root} ] && [ -x {py} ]; then PYTHONPATH={root} $T {py} -m factory.cli ops bundle --sha HEAD; fi
}}
( __sf_autobundle ) >/dev/null 2>&1 &
{END}
"""


def _shebang_problem(text: str | None) -> str | None:
    """Why a hook's interpreter cannot run the shell block, or None."""
    if not text or not text.startswith("#!"):
        return None
    try:
        words = shlex.split(text.split("\n", 1)[0][2:])
    except ValueError:
        return "unreadable shebang"
    if words and Path(words[0]).name == "env":
        words = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
    name = Path(words[0]).name if words else ""
    return None if name in SHELLS else f"shebang is not sh, bash, dash or zsh: {text.splitlines()[0]}"


def _unreachable(text: str) -> str | None:
    for ln in text[:text.index(BEGIN)].splitlines():
        if re.match(r"\s*(exit|exec)\b", ln):
            return f"a line before the block ends the hook: {ln.strip()}"
    return None


def _autobundle(action: str, repo: Path) -> int:
    repo = repo.resolve()
    top = _git(repo, "rev-parse", "--show-toplevel")
    hook = _hook_path(repo) if top is not None else None
    if hook is None:
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 2
    if hook.is_symlink():
        print(f"error: refusing to touch a symlinked hook: {hook}", file=sys.stderr)
        return 1
    text = hook.read_text(encoding="utf-8") if hook.exists() else None
    has = text is not None and BEGIN in text and END in text
    half = text is not None and not has and (BEGIN in text or END in text)
    if action == "status":
        if half:
            print(f"not effective: the sf ops autobundle markers in {hook} are incomplete")
            return 1
        if not has:
            print(f"not installed: {hook}")
            return 0
        why = (_shebang_problem(text) or _unreachable(text)
               or (None if os.access(hook, os.X_OK) else "the hook is not executable")
               or (None if (Path(top) / "ops" / "config.json").is_file() else "ops/config.json is missing, so the block does nothing"))
        if why:
            print(f"not effective: {why}")
            return 1
        print(f"installed: {hook}")
        return 0
    if action == "install":
        why = _shebang_problem(text) or ("the sf ops autobundle markers are incomplete; fix or remove them first" if half else None)
        if why:
            print(f"error: not installing into {hook}: {why}", file=sys.stderr)
            return 1
        if not has:
            if text is None:
                new = "#!/bin/sh\n" + _block()
            elif text.startswith("#!"):  # right after the shebang, so a later top-level exit cannot skip it
                first, _, rest = text.partition("\n")
                new = first + "\n" + _block() + rest
            else:
                new = _block() + text
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text(new, encoding="utf-8")
        os.chmod(hook, hook.stat().st_mode | 0o111)
        _exclude_events(repo)
        cfg = Path(top) / "ops" / "config.json"  # opting in: the block acts only where this file exists
        if not cfg.exists():
            B._check_inside(cfg, Path(top) / "ops")
            B._atomic(cfg, b"{}\n", Path(top) / "ops")
        print(f"installed: {hook}")
        return 0
    if half:
        print(f"error: the sf ops autobundle markers in {hook} are incomplete; edit the file by hand", file=sys.stderr)
        return 1
    if has:
        a, b = text.index(BEGIN), text.index(END) + len(END)
        rest = text[:a] + text[b:].removeprefix("\n")
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
    i.add_argument("--langfuse-host", help="https URL of the Langfuse host, recorded in ops/config.json (no credentials)")
    i.add_argument("--langfuse-project", help="Langfuse project name, recorded in ops/config.json")
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
        return _init(Path(a.dir), a.langfuse_host, a.langfuse_project)
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
