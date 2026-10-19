"""CLI: python -m factory.verify {check-contracts|verify|report}."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from . import gate
from .consistency import compare_contracts, review_contract
from .contracts import ContractError, check_ids, load_contracts, load_retired
from .regress import write_regressions


def _load(paths):
    try:
        return load_contracts(paths)
    except (ContractError, OSError) as e:
        print(f"contract error: {e}", file=sys.stderr)
        print(f"contract error: {e}")
        return None


def _print_findings(reports) -> int:
    code = gate.EXIT_OK
    for r in reports:
        for f in r.findings:
            print(f"[{f.severity}] {r.contract_id} {f.code}" + (f" ({f.obligation})" if f.obligation else "") + f": {f.message}")
            if f.detail:
                print(f"        detail: {json.dumps(f.detail, default=str)}")
        if not r.ok:
            code = gate.EXIT_CONTRACT_REVIEW
    return code


def cmd_check_contracts(a) -> int:
    contracts = _load(a.paths)
    if contracts is None:
        return gate.EXIT_USAGE
    retired = load_retired(a.retired) if a.retired else []
    code = gate.EXIT_OK
    for p in check_ids(contracts, retired):
        print(f"[error] {p}")
        code = gate.EXIT_CONTRACT_REVIEW
    try:
        reports = [review_contract(c) for c in contracts]
        if a.against:
            old = _load(a.against)
            if old is None:
                return gate.EXIT_USAGE
            olds = {c.contract_id: c for c in old}
            for c in contracts:
                if c.contract_id in olds:
                    reports.append(compare_contracts(olds[c.contract_id], c))
                else:
                    print(f"[info] {c.contract_id} is new (no old version to compare)")
    except Exception as e:  # noqa: BLE001
        from .solve import SolverUnavailable
        if isinstance(e, SolverUnavailable):
            print(f"[error] Z3_MISSING: {e}")
            return gate.EXIT_Z3_MISSING
        print(f"[error] CRASH: {type(e).__name__}: {e}")
        return gate.EXIT_CRASH
    code = max(code, _print_findings(reports)) if code == gate.EXIT_OK else code
    print("check-contracts:", "OK" if code == gate.EXIT_OK else f"FAILED (exit {code})")
    return code


def _render(d: dict) -> str:
    lines = [f"gate: {'PASSED' if d['passed'] else 'FAILED'} (exit {d['exit_code']})",
             f"tools: python {d['tool_versions'].get('python')}, z3 {d['tool_versions'].get('z3')}"]
    for c in d["contracts"]:
        lines.append(f"- {c['contract_id']} {c['symbol']} [{c.get('semantics')}]" + (" (cache hit)" if c.get("cache_hit") else ""))
        for o in c.get("obligations", []):
            lines.append(f"    {o['verdict'] + (' (cached)' if o.get('cached') else ''):<14} {o['id']}: {o['text']}" + (f"  -> route {o['route']['method']}" if o.get("route") else ""))
    for r in d["reasons"]:
        lines.append(f"! {r['code']}: {r['message']}")
    return "\n".join(lines)


def cmd_verify(a) -> int:
    contracts = _load(a.paths)
    if contracts is None:
        return gate.EXIT_USAGE
    retired = load_retired(a.retired) if a.retired else []
    sources = {}
    for s in a.source or []:
        sym, _, path = s.partition("=")
        sources[sym] = Path(path)
    rep = gate.run_gate(contracts, roots=a.root or [], source_files=sources, timeout_ms=a.timeout_ms,
                        cache_path=None if a.no_cache else a.cache, retired_ids=retired)
    d = rep.as_dict()
    if a.report:
        Path(a.report).write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    if a.regress_dir:
        for p in write_regressions(rep, a.regress_dir):
            print(f"wrote regression {p}")
    print(_render(d))
    return rep.exit_code


def cmd_report(a) -> int:
    try:
        d = json.loads(Path(a.path).read_text(encoding="utf-8"))
        print(_render(d))
        return int(d["exit_code"])
    except (OSError, ValueError, KeyError) as e:
        print(f"cannot read report: {e}")
        return gate.EXIT_USAGE


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m factory.verify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check-contracts", help="review contracts before code (and compare with an old version)")
    c.add_argument("paths", nargs="+")
    c.add_argument("--against", nargs="+", help="old contract files/dirs to compare by contract_id")
    c.add_argument("--retired", help="RETIRED.yaml listing contract ids that must never be reused")
    c.set_defaults(fn=cmd_check_contracts)
    v = sub.add_parser("verify", help="verify contracts against implementations (the gate)")
    v.add_argument("paths", nargs="+")
    v.add_argument("--root", action="append", help="directory searched for the contract's module (repeatable)")
    v.add_argument("--source", action="append", help="SYMBOL=FILE override of the implementation file")
    v.add_argument("--timeout-ms", type=int, default=5000)
    v.add_argument("--cache", help="JSON proof cache file (local speed only: a hand-written file can forge a pass)")
    v.add_argument("--no-cache", action="store_true", help="never read or write a cache; the CI/release default")
    v.add_argument("--report", help="write the JSON report here")
    v.add_argument("--regress-dir", help="write pytest regressions for counterexamples here")
    v.add_argument("--retired")
    v.set_defaults(fn=cmd_verify)
    r = sub.add_parser("report", help="print a saved JSON report; exit code = recorded gate code")
    r.add_argument("path")
    r.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
