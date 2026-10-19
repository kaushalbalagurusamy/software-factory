"""python -m factory.hitl: human stops. Exit codes: 0 ok / no applicable open stop, 1 error,
2 usage error, 3 an open stop applies (status), 4 ledger tampered (status fails closed),
5 release refused (not an interactive terminal, or actor is not human:<ref>)."""
from __future__ import annotations

import argparse
import sys

from . import store

OK, ERR, USAGE, OPEN, TAMPER, REFUSED = 0, 1, 2, 3, 4, 5


def _status(a) -> int:
    try:
        stops = store.blocking(a.root, a.scope)
    except store.StopLedgerError as e:
        print(f"TAMPERED stop ledger (failing closed): {e}", file=sys.stderr)
        return TAMPER
    for s in stops:
        print(f"OPEN {'(legacy .sf/stops, read-only) ' if s['legacy'] else ''}{s['name']} [{s['scope']}] {s['reason']} (by {s['requested_by']} at {s['requested_at']})")
    if not stops:
        print("no open stops")
    return OPEN if stops else OK


def _request(a) -> int:
    r = store.request(a.root, a.name, a.reason, a.scope, a.by)
    print(f"stop {r['name']} requested [{r['scope']}]")
    return OK


def _release(a) -> int:
    store.release(a.root, a.name, a.by)
    print(f"stop {a.name} released by {a.by}")
    return OK


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m factory.hitl", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("request"); c.set_defaults(f=_request)
    c.add_argument("--name", required=True); c.add_argument("--reason", required=True)
    c.add_argument("--scope", default="run"); c.add_argument("--by", default="unspecified")
    c = sub.add_parser("status"); c.set_defaults(f=_status); c.add_argument("--scope")
    c = sub.add_parser("release"); c.set_defaults(f=_release)
    c.add_argument("--name", required=True); c.add_argument("--by", required=True)
    for c in sub.choices.values():
        c.add_argument("--root", required=True)
    return ap


def main(argv=None) -> int:
    try:
        a = build().parse_args(argv)
    except SystemExit as e:
        return USAGE if e.code else OK
    try:
        return a.f(a)
    except store.StopUsageError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return USAGE
    except store.ReleaseRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return REFUSED
    except store.StopLedgerError as e:
        print(f"TAMPERED stop ledger: {e}", file=sys.stderr)
        return TAMPER


if __name__ == "__main__":
    sys.exit(main())
