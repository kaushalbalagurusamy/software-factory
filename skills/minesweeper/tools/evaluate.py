#!/usr/bin/env python3
"""Run and score evaluation cases.

  python3 tools/evaluate.py list [--lens ID]
  python3 tools/evaluate.py run   --label NAME [--lens ID | --case ID ...] [--model sonnet] [-j 2]
  python3 tools/evaluate.py score RUN_DIR [RUN_DIR ...] [--record]

`run` sweeps each case brief in eval mode through headless Claude Code (`claude -p`, the Claude Max
subscription; no other API) and writes runs/<date>-<label>/<case-id>/{claims.json, register.json,
meta.json}. Eval mode is one pass, retrieval and checks only, no research hand-offs, so results
measure the sweep, not the web.

`score` reads one or more run directories and prints per-lens metrics:
  recall            planted traps found (any non-dismissed finding on the trap or an alias)
  false_alarm_rate  clean twins where the lens under test raised a non-dismissed finding
  omission_recall   omission cases whose required statement became a live finding
  citation_rate     confirmed findings with at least one evidence item
  severity_agree    with several run dirs: share of (case, trap) whose tier matched in every run
  tokens, minutes   per case, from meta.json
--record writes runs/calibration.json: a lens is calibrated at its version when it meets the
policy.yaml thresholds. Failed runs stay in runs/; reruns are new directories.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, ROOT, lens_dirs, load_lens, load_yaml  # noqa: E402

RUNS = ROOT / "runs"


def all_cases(lens: str | None = None) -> list[dict]:
    out = []
    for d in lens_dirs():
        if lens and d.name != lens:
            continue
        L = load_lens(d)
        for cid, c in L["cases"].items():
            out.append({**c, "_lens": d.name, "_version": L["manifest"]["version"], "_path": str(d / "cases" / f"{cid}.yaml")})
    if not lens:
        for p in sorted((ROOT / "integration").glob("*.yaml")):
            c = load_yaml(p)
            out.append({**c, "_lens": None, "_version": None, "_path": str(p)})
    return out


def alias_map() -> dict:
    m = {}
    for d in lens_dirs():
        for t in (load_lens(d)["traps"] or {}).get("traps", []):
            m[t["id"]] = t["id"]
            for a in t.get("aliases", []):
                m[a] = t["id"]
    return m


PROMPT = """Use the minesweeper skill (~/.claude/skills/minesweeper/SKILL.md) in EVAL mode on the brief at {brief}.
Eval mode: a single pass; retrieval from the local cache (tools/search.py) and tools/checks only; no
grounded-research, deep-research, experiment-designer or web fetches; do not ask questions.
Write claims.json and register.json to {out}, valid against engine/schemas, with register.run.mode "eval"
and convergence.stop_reason "eval-single-pass". Validate both with tools/validate.py before finishing.
{scope}Do not read any file under lenses/*/cases/ or integration/: they hold the expected answers."""


def run_case(case: dict, out_root: Path, model: str, timeout: int) -> dict:
    out = out_root / case["id"]
    out.mkdir(parents=True, exist_ok=True)
    brief = out / "brief.md"
    brief.write_text(case["brief"], encoding="utf-8")
    scope = f"Lens under test: {case['_lens']} (still apply every lens plan.py selects).\n" if case["_lens"] else ""
    prompt = PROMPT.format(brief=brief, out=out, scope=scope)
    t0 = time.time()
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json", "--permission-mode", "bypassPermissions"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        res = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"raw": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
        rc = p.returncode
    except subprocess.TimeoutExpired:
        res, rc = {"error": f"timeout after {timeout}s"}, -1
    usage = res.get("usage") or {}
    meta = {
        "case": case["id"], "lens": case["_lens"], "lens_version": case["_version"], "model": model,
        "returncode": rc, "minutes": round((time.time() - t0) / 60, 2),
        "tokens": sum(v for k, v in usage.items() if k.endswith("tokens") and isinstance(v, int)) or None,
        "cost_usd_reported": res.get("total_cost_usd"), "error": res.get("error") or (res.get("is_error") and res.get("result")),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def score_dir(run_dir: Path, cases: dict, aliases: dict) -> dict:
    per = {}
    for cdir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        case = cases.get(cdir.name)
        if not case:
            continue
        lens = case["_lens"] or "integration"
        s = per.setdefault(lens, {"planted": 0, "hit": 0, "clean": 0, "alarm": 0, "omit": 0, "omit_hit": 0, "confirmed": 0, "cited": 0, "missing": 0, "tokens": [], "minutes": [], "tiers": {}})
        reg_p, claims_p = cdir / "register.json", cdir / "claims.json"
        meta = json.loads((cdir / "meta.json").read_text()) if (cdir / "meta.json").exists() else {}
        if meta.get("tokens"):
            s["tokens"].append(meta["tokens"])
        if meta.get("minutes") is not None:
            s["minutes"].append(meta["minutes"])
        exp = case.get("expect", {})
        if not reg_p.exists():
            s["missing"] += 1  # a crashed run counts as a miss, never as a pass
            s["planted"] += len(exp.get("traps", []))
            s["omit"] += len(exp.get("omissions", []))
            is_clean = case["kind"] == "clean" or (case["kind"] == "integration" and exp.get("none_from_lens"))
            s["clean"] += 1 if is_clean else 0
            s["alarm"] += 1 if is_clean else 0
            continue
        reg = json.loads(reg_p.read_text())
        claims = {c["id"]: c for c in json.loads(claims_p.read_text()).get("claims", [])} if claims_p.exists() else {}
        live = [f for f in reg.get("findings", []) if f.get("status") != "dismissed"]
        found = {aliases.get(f.get("trap_id"), f.get("trap_id")): f for f in live}
        for tid in exp.get("traps", []):
            s["planted"] += 1
            f = found.get(aliases.get(tid, tid))
            if f:
                s["hit"] += 1
                s["tiers"][(cdir.name, tid)] = (f.get("severity") or {}).get("tier")
        if case["kind"] == "clean":
            s["clean"] += 1
            if any(f.get("lens") == case["_lens"] for f in live):
                s["alarm"] += 1
        elif case["kind"] == "integration" and exp.get("none_from_lens"):
            # A clean multi-lens brief: any surviving finding above low is a false alarm.
            s["clean"] += 1
            if any((f.get("severity") or {}).get("tier") not in ("low", None) for f in live):
                s["alarm"] += 1
        for oid in exp.get("omissions", []):
            s["omit"] += 1
            if any(claims.get(cid, {}).get("kind") == "omission" and claims[cid].get("locator") == oid for f in live for cid in f.get("claim_ids", [])):
                s["omit_hit"] += 1
        for f in reg.get("findings", []):
            if f.get("status") == "confirmed":
                s["confirmed"] += 1
                s["cited"] += 1 if f.get("evidence") else 0
    return per


def ratio(a, b):
    return round(a / b, 3) if b else None


def score(run_dirs: list[Path], record: bool) -> int:
    cases = {c["id"]: c for c in all_cases()}
    aliases = alias_map()
    runs = [score_dir(d, cases, aliases) for d in run_dirs]
    policy = load_yaml(CONFIG / "policy.yaml")["calibration"]
    versions = {d.name: load_lens(d)["manifest"]["version"] for d in lens_dirs()}
    cal_p = RUNS / "calibration.json"
    cal = json.loads(cal_p.read_text()) if cal_p.exists() else {}
    report = {}
    for lens in sorted({l for r in runs for l in r}):
        s = runs[0].get(lens) or {}
        m = {
            "recall": ratio(s.get("hit", 0), s.get("planted", 0)),
            "false_alarm_rate": ratio(s.get("alarm", 0), s.get("clean", 0)),
            "omission_recall": ratio(s.get("omit_hit", 0), s.get("omit", 0)),
            "citation_rate": ratio(s.get("cited", 0), s.get("confirmed", 0)),
            "crashed_cases": s.get("missing", 0),
            "tokens_mean": round(sum(s["tokens"]) / len(s["tokens"])) if s.get("tokens") else None,
            "minutes_mean": round(sum(s["minutes"]) / len(s["minutes"]), 2) if s.get("minutes") else None,
        }
        if len(runs) > 1:
            keys = set.intersection(*[set((r.get(lens) or {}).get("tiers", {})) for r in runs])
            agree = sum(len({r[lens]["tiers"][k] for r in runs}) == 1 for k in keys)
            m["severity_agree"] = ratio(agree, len(keys))
        passed = (
            m["recall"] is not None and m["recall"] >= policy["min_recall"]
            and (m["false_alarm_rate"] is None or m["false_alarm_rate"] <= policy["max_false_alarm_rate"])
            and (m["omission_recall"] is None or m["omission_recall"] >= policy["min_omission_recall"])
            and (m["citation_rate"] is None or m["citation_rate"] >= policy["min_citation_rate"])
            and m["crashed_cases"] == 0
        )
        m["passed"] = passed
        report[lens] = m
        if record and lens in versions:
            cal[lens] = {"version": versions[lens], "passed": passed, "date": date.today().isoformat(), "runs": [str(d.relative_to(ROOT)) for d in run_dirs], "metrics": m}
    for lens, m in report.items():
        print(f"{lens:24} " + "  ".join(f"{k}={v}" for k, v in m.items()))
    out = run_dirs[0] / "score.json"
    out.write_text(json.dumps(report, indent=2))
    if record:
        cal_p.write_text(json.dumps(cal, indent=2))
        print(f"recorded calibration for {sum(1 for l in report if l in versions)} lens(es) in {cal_p.relative_to(ROOT)}")
    return 0 if all(m["passed"] for m in report.values()) else 1


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list")
    l.add_argument("--lens")
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--lens")
    r.add_argument("--case", action="append")
    r.add_argument("--model", default=load_yaml(CONFIG / "models.yaml")["roles"]["sweeper"])
    r.add_argument("-j", type=int, default=2)
    r.add_argument("--timeout", type=int, default=1500)
    s = sub.add_parser("score")
    s.add_argument("run_dirs", nargs="+", type=Path)
    s.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for c in all_cases(a.lens):
            print(f"{c['id']:40} {c['kind']:11} {c['_lens'] or 'integration'}")
        return 0
    if a.cmd == "run":
        cases = [c for c in all_cases(a.lens) if not a.case or c["id"] in a.case]
        if not cases:
            print("no cases selected", file=sys.stderr)
            return 2
        out_root = RUNS / f"{date.today().isoformat()}-{a.label}"
        if out_root.exists():
            print(f"{out_root} exists: reruns get a new label so failed runs stay in the history", file=sys.stderr)
            return 2
        out_root.mkdir(parents=True)
        with ThreadPoolExecutor(max_workers=a.j) as ex:
            for meta in ex.map(lambda c: run_case(c, out_root, a.model, a.timeout), cases):
                print(f"{meta['case']:40} rc={meta['returncode']} {meta['minutes']} min")
        print(f"run dir: {out_root}")
        return 0
    return score(a.run_dirs, a.record)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
