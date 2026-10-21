#!/usr/bin/env python3
"""Plan a sweep: which lenses apply to a brief, grouped for sweep agents, with each lens's required
statements (for omission claims) and the paths a sweeper must read. Deterministic, so two runs on
the same brief load the same lenses.

Usage: python3 tools/plan.py BRIEF [--all] [--json]
  --all   load every lens regardless of applies_when (use for integration evaluation)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, LENSES, ROOT, applies, lens_dirs, load_lens, load_yaml  # noqa: E402


def calibration() -> dict:
    p = ROOT / "runs" / "calibration.json"
    return json.loads(p.read_text()) if p.exists() else {}


def plan(brief: Path, load_all: bool = False) -> dict:
    text = brief.read_text(encoding="utf-8")
    groups = load_yaml(CONFIG / "groups.yaml")["groups"]
    models = load_yaml(CONFIG / "models.yaml")["roles"]
    cal = calibration()
    lens_group = {lid: g for g, spec in groups.items() for lid in spec["lenses"]}
    out_groups: dict[str, dict] = {}
    skipped = []
    for d in lens_dirs():
        lens = load_lens(d)
        m = lens["manifest"]
        ok, why = (True, "--all") if load_all else applies(m, text)
        if not ok:
            skipped.append(m["id"])
            continue
        g = lens_group.get(m["id"], "unassigned")
        grp = out_groups.setdefault(g, {
            "title": groups.get(g, {}).get("title", g),
            "model": groups.get(g, {}).get("model", models["sweeper"]),
            "lenses": [],
        })
        traps = (lens["traps"] or {}).get("traps", [])
        c = cal.get(m["id"], {})
        grp["lenses"].append({
            "id": m["id"],
            "version": m["version"],
            "why": why,
            "calibrated": c.get("version") == m["version"] and c.get("passed") is True,
            "read": [str((d / f).relative_to(ROOT)) for f in ("lens.md", "traps.yaml")],
            "required_statements": [f"{m['id']}.{r['id']}: {r['statement']}" for r in m.get("required_statements", [])],
            "traps": [{"id": t["id"], "status": t["status"], "kind": t["kind"]} for t in traps],
        })
    applied = [l for g in out_groups.values() for l in g["lenses"]]
    return {
        "brief": {"path": str(brief), "sha256": hashlib.sha256(text.encode()).hexdigest()},
        "groups": out_groups,
        "lenses_applied": len(applied),
        "lenses_skipped": skipped,
        "calibrated": bool(applied) and all(l["calibrated"] for l in applied),
        "models": models,
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("brief", type=Path)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = plan(a.brief, a.all)
    if a.json:
        print(json.dumps(p, indent=2))
        return 0
    print(f"brief {p['brief']['path']}  sha256 {p['brief']['sha256'][:12]}  calibrated: {p['calibrated']}")
    for g, spec in p["groups"].items():
        print(f"\n[{g}] {spec['title']}  (model {spec['model']})")
        for l in spec["lenses"]:
            n_ver = sum(t["status"] == "verified" for t in l["traps"])
            print(f"  {l['id']} {l['version']}  traps {len(l['traps'])} ({n_ver} verified)  {l['why']}")
    print(f"\nskipped: {', '.join(p['lenses_skipped']) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
