from __future__ import annotations

import argparse
from pathlib import Path

from . import bundle as B
from . import runtime as R


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
