#!/usr/bin/env python3
"""Render register.json as register.md for people. The JSON stays the record; this is a view.

Usage: python3 tools/render.py RUN_DIR/register.json [> RUN_DIR/register.md]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TIERS = ["critical", "high", "medium", "low"]


def cell(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def render(reg: dict) -> str:
    run, conv = reg["run"], reg["convergence"]
    out = [
        "# Minesweeper trap register",
        "",
        f"- Brief: `{reg['brief']['path']}` (sha256 `{reg['brief']['sha256'][:12]}`)",
        f"- Run: {run['date']}, mode {run['mode']}, skill {run.get('skill_version', '?')}",
        f"- Calibrated: **{'yes' if run['calibrated'] else 'NO: uncalibrated lenses, treat findings as leads'}**",
        f"- Lenses: " + ", ".join(f"{l['id']} {l['version']}{'' if l['calibrated'] else ' (uncalibrated)'}" for l in run["lenses"]),
        f"- Loop: {conv['passes']} pass(es), stop: {conv['stop_reason']}; open: {', '.join(conv.get('open', [])) or 'none'}",
        "",
    ]
    g = reg.get("gates") or {}
    if g.get("blocking") or g.get("needs_disposition"):
        out += ["## Gates", ""]
        if g.get("blocking"):
            out.append(f"- **Blocking until owner sign-off (Critical):** {', '.join(g['blocking'])}")
        if g.get("needs_disposition"):
            out.append(f"- **High, needs a recorded disposition:** {', '.join(g['needs_disposition'])}")
        out.append("")
    live = [f for f in reg["findings"] if f["status"] in ("confirmed", "plausible")]
    live.sort(key=lambda f: (TIERS.index((f.get("severity") or {}).get("tier", "low")), f["id"]))
    out += ["## Findings", "", "| Id | Tier | Status | Lens / trap | Disposition | Underlying problem |", "|---|---|---|---|---|---|"]
    for f in live:
        out.append(f"| {f['id']} | {(f.get('severity') or {}).get('tier', '-')} | {f['status']} | {f['lens']} / {f.get('trap_id') or 'novel'} | {f.get('disposition', '-')} | {cell(f.get('underlying_problem') or f.get('would_settle'))} |")
    out.append("")
    for f in live:
        out += [f"### {f['id']}: {f.get('trap_id') or 'novel finding'}", ""]
        out.append(f"- Claims: {', '.join(f['claim_ids'])}; route: {f['route']} ({cell(f.get('route_reason'))})")
        for e in f.get("evidence", []):
            q = f" \"{cell(e['quote'])}\"" if e.get("quote") else ""
            out.append(f"- Evidence ({e['kind']}, {e.get('tier', '-')}, {e['date']}): {e['ref']} {e.get('locator', '')}{q}")
        if f.get("severity"):
            yes = [a for a in f["severity"]["answers"] if a["a"]]
            out.append(f"- Severity {f['severity']['tier']}: first yes = {cell(yes[0]['q']) if yes else 'none'}")
        if f.get("skeptic"):
            out.append(f"- Skeptic: {f['skeptic']['verdict']}: {cell(f['skeptic']['reason'])}")
        if f.get("owner_question"):
            out.append(f"- **Owner question:** {cell(f['owner_question'])}")
        if f.get("spec_section"):
            out.append(f"- Spec section that must answer it: `{f['spec_section']}`")
        out.append("")
    out += ["## Poisoned-instruction autopsy", ""]
    if reg["quarantine"]:
        out += ["| Brief locator | Quarantined text | Findings | Reason | Replaced by |", "|---|---|---|---|---|"]
        for q in reg["quarantine"]:
            out.append(f"| {cell(q['locator'])} | {cell(q['text'])} | {', '.join(q['finding_ids'])} | {cell(q['reason'])} | {cell(q.get('replacement'))} |")
    else:
        out.append("Nothing quarantined.")
    dismissed = [f for f in reg["findings"] if f["status"] == "dismissed"]
    if dismissed:
        out += ["", "## Dismissed", ""]
        out += [f"- {f['id']} ({f['lens']} / {f.get('trap_id') or 'novel'}): {cell(f.get('dismissal_reason'))}" for f in dismissed]
    out += ["", "_Not legal advice. The skill flags and cites; the owner decides._", ""]
    return "\n".join(out)


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    print(render(json.loads(Path(argv[0]).read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
