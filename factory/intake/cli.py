"""python -m factory.intake <check|record-sweep|signoff|gate|seeds check|experiments check>.

Exit codes: 0 ok, 1 check failure, 2 usage error, 3 gate not met.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ledger, sweep

OK, FAIL, USAGE, GATE = 0, 1, 2, 3
DEFAULT_LEDGER = "docs/requirements/ledger.tsv"


def _say(lines, stream):
    for ln in lines:
        print(ln, file=stream)


def build() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="factory.intake")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, source_required=False):
        sp.add_argument("--source", type=Path, required=source_required)
        sp.add_argument("--ledger", type=Path, default=Path(DEFAULT_LEDGER))
        sp.add_argument("--repo-root", type=Path, default=Path("."))

    c = sub.add_parser("check")
    common(c, True)
    r = sub.add_parser("record-sweep")
    common(r)
    r.add_argument("--register", type=Path, required=True)
    r.add_argument("--claims", type=Path)
    s = sub.add_parser("signoff")
    common(s)
    s.add_argument("--finding", required=True)
    s.add_argument("--by", required=True)
    g = sub.add_parser("gate")
    common(g)
    g.add_argument("--slice", type=Path, dest="slice_dir")
    g.add_argument("--since")
    sd = sub.add_parser("seeds").add_subparsers(dest="sub", required=True).add_parser("check")
    sd.add_argument("--file", type=Path, default=Path("research/seeds.tsv"))
    sd.add_argument("--lenses", type=Path)
    sd.add_argument("--repo-root", type=Path, default=Path("."))
    ex = sub.add_parser("experiments").add_subparsers(dest="sub", required=True).add_parser("check")
    ex.add_argument("id", nargs="?")
    ex.add_argument("--root", type=Path, default=Path("experiments"))
    return p


def main(argv=None) -> int:
    try:
        a = build().parse_args(argv)
    except SystemExit as e:
        return USAGE if e.code not in (0, None) else OK
    try:
        if a.cmd == "check":
            errs = ledger.check(a.source, a.ledger, a.repo_root)
            _say(errs or [f"ok: {a.ledger} covers every non-blank line of {a.source}"], sys.stderr if errs else sys.stdout)
            return FAIL if errs else OK
        if a.cmd == "record-sweep":
            _say(sweep.record_sweep(a.register, a.ledger, a.source, a.claims), sys.stdout)
            return OK
        if a.cmd == "signoff":
            _say(sweep.signoff(a.ledger, a.source, a.finding, a.by), sys.stdout)
            return OK
        if a.cmd == "gate":
            errs = sweep.gate(a.ledger, a.source, a.slice_dir, a.since, a.repo_root)
            _say(errs or ["gate met"], sys.stderr if errs else sys.stdout)
            return GATE if errs else OK
        if a.cmd == "seeds":
            from . import seeds
            try:
                lenses, used = seeds.load_lenses(a.lenses)
            except FileNotFoundError as e:
                print(e, file=sys.stderr)
                return USAGE
            errs = seeds.check(a.file, lenses, a.repo_root)
            _say(errs or [f"ok: {a.file} (lens list {used})"], sys.stderr if errs else sys.stdout)
            return FAIL if errs else OK
        if a.cmd == "experiments":
            from . import experiments
            errs = experiments.check_root(a.root, a.id)
            _say(errs or [f"ok: {a.root}"], sys.stderr if errs else sys.stdout)
            return FAIL if errs else OK
    except sweep.IntakeError as e:
        _say(e.msgs, sys.stderr)
        return e.code
    return USAGE


if __name__ == "__main__":
    sys.exit(main())
