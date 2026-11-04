#!/usr/bin/env python3
"""Structural lint for the minesweeper skill. Exit 0 clean, 1 on any error.

Fails when: a manifest, catalogue, source list or case is invalid against its schema; a verified
trap cites a non-primary source or one without a quote; a check named by a trap does not exist; a
trap has no source or no planted case; a source has no adapter; a lens has no clean twin; groups.yaml
does not cover every lens exactly once; ids collide; or content names a denylisted project.
Warnings (unverified seeds, missing omission cases) never fail the run.

Usage: python3 tools/lint.py [--quiet]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ADAPTERS, CONFIG, LENSES, ROOT, lens_dirs, load_lens, load_yaml, validator  # noqa: E402
from checks import CHECKS  # noqa: E402

REQUIRED_FILES = ["lens.md", "traps.yaml", "sources.yaml", "CHANGELOG.md"]


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def schema_errors(v, doc, where, rep):
    for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "<root>"
        rep.err(f"{where}: {loc}: {e.message}")


def denylist() -> list[re.Pattern]:
    pats = []
    for line in (CONFIG / "denylist.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(re.compile(rf"\b{re.escape(line)}\b", re.IGNORECASE))
    return pats


def lint(rep: Report) -> dict:
    v_lens, v_traps = validator("lens.v1.json"), validator("traps.v1.json")
    v_sources, v_case = validator("sources.v1.json"), validator("case.v1.json")
    adapters = {p.stem for p in ADAPTERS.glob("*.py") if not p.stem.startswith("_")}
    deny = denylist()
    stats = {"lenses": 0, "traps": 0, "verified": 0, "unverified": 0, "cases": 0, "sources": 0}
    seen_trap_ids: dict[str, str] = {}
    lens_ids: list[str] = []

    for d in lens_dirs():
        name = d.name
        missing = [f for f in REQUIRED_FILES if not (d / f).exists()]
        if missing:
            rep.err(f"{name}: missing {', '.join(missing)}")
            continue
        if not (d / "cases").is_dir():
            rep.err(f"{name}: missing cases/")
            continue
        try:
            lens = load_lens(d)
        except Exception as exc:  # malformed YAML or front matter is a lint error, not a crash
            rep.err(f"{name}: cannot load: {exc}")
            continue
        stats["lenses"] += 1
        lens_ids.append(name)
        m, traps_doc, sources_doc = lens["manifest"], lens["traps"], lens["sources"]
        schema_errors(v_lens, m, f"{name}/lens.md", rep)
        schema_errors(v_traps, traps_doc, f"{name}/traps.yaml", rep)
        schema_errors(v_sources, sources_doc, f"{name}/sources.yaml", rep)
        if m.get("id") != name:
            rep.err(f"{name}/lens.md: id {m.get('id')!r} does not match folder")
        for a in m.get("adapters", []):
            if a not in adapters:
                rep.err(f"{name}/lens.md: adapter {a!r} not in sources/adapters/")

        sources = {s["id"]: s for s in (sources_doc or {}).get("sources", []) if isinstance(s, dict) and "id" in s}
        stats["sources"] += len(sources)
        for s in sources.values():
            if s.get("adapter") not in adapters:
                rep.err(f"{name}/sources.yaml: source {s['id']} uses unknown adapter {s.get('adapter')!r}")

        statement_ids = {f"{name}.{r['id']}" for r in m.get("required_statements", []) if isinstance(r, dict) and "id" in r}
        traps = [t for t in (traps_doc or {}).get("traps", []) if isinstance(t, dict)]
        trap_ids = set()
        for t in traps:
            tid = t.get("id", "?")
            stats["traps"] += 1
            if not tid.startswith(name + "."):
                rep.err(f"{name}: trap {tid} must be prefixed '{name}.'")
            for key in [tid, *t.get("aliases", [])]:
                if key in seen_trap_ids:
                    rep.err(f"{name}: trap id or alias {key} duplicates one in {seen_trap_ids[key]}")
                seen_trap_ids[key] = name
            trap_ids.add(tid)
            if not t.get("sources"):
                rep.err(f"{name}: trap {tid} has no source")
            for sid in t.get("sources", []):
                if sid not in sources:
                    rep.err(f"{name}: trap {tid} cites unknown source {sid}")
            for c in t.get("checks", []):
                if c not in CHECKS:
                    rep.err(f"{name}: trap {tid} names unknown check {c}")
            if t.get("status") == "verified":
                stats["verified"] += 1
                if not t.get("verified_on"):
                    rep.err(f"{name}: verified trap {tid} has no verified_on date")
                for sid in t.get("sources", []):
                    s = sources.get(sid)
                    if not s:
                        continue
                    if s.get("tier") != "primary":
                        rep.err(f"{name}: verified trap {tid} cites non-primary source {sid}")
                    if not any(tid in q.get("supports", [tid]) for q in s.get("quotes", [])):
                        rep.err(f"{name}: verified trap {tid} cites {sid} with no quote supporting it")
            else:
                stats["unverified"] += 1

        planted_cover, omission_cover, clean = set(), set(), set()
        cases = lens["cases"]
        for cid, c in cases.items():
            stats["cases"] += 1
            schema_errors(v_case, c, f"{name}/cases/{cid}.yaml", rep)
            if not isinstance(c, dict):
                continue
            if c.get("id") != cid:
                rep.err(f"{name}/cases/{cid}.yaml: id {c.get('id')!r} does not match file name")
            kind, exp = c.get("kind"), c.get("expect", {}) or {}
            if kind == "clean":
                clean.add(cid)
                if not exp.get("none_from_lens"):
                    rep.err(f"{name}/cases/{cid}: clean case must set expect.none_from_lens: true")
            if kind in ("planted", "omission"):
                twin = c.get("twin")
                if not twin or twin not in cases:
                    rep.err(f"{name}/cases/{cid}: {kind} case needs a twin that exists in this lens")
                elif cases[twin].get("kind") != "clean":
                    rep.err(f"{name}/cases/{cid}: twin {twin} is not a clean case")
            for tid in exp.get("traps", []):
                if tid not in trap_ids:
                    rep.err(f"{name}/cases/{cid}: expects {tid}, which is not a trap of this lens")
                planted_cover.add(tid)
            for oid in exp.get("omissions", []):
                if oid not in statement_ids:
                    rep.err(f"{name}/cases/{cid}: expects unknown required statement {oid}")
                omission_cover.add(oid)
        if not clean:
            rep.err(f"{name}: no clean twin case")
        for tid in sorted(trap_ids - planted_cover):
            rep.err(f"{name}: trap {tid} has no planted case")
        for oid in sorted(statement_ids - omission_cover):
            rep.warn(f"{name}: required statement {oid} has no omission case")
        unv = [t["id"] for t in traps if t.get("status") != "verified" and "id" in t]
        if unv:
            rep.warn(f"{name}: {len(unv)} unverified trap(s); they can raise suspects but never confirm")

        for p in [d / "lens.md", d / "traps.yaml", d / "sources.yaml", *sorted((d / "cases").glob("*.yaml"))]:
            text = p.read_text(encoding="utf-8")
            for pat in deny:
                if pat.search(text):
                    rep.err(f"{p.relative_to(ROOT)}: names a denylisted project ({pat.pattern})")

    # groups.yaml covers every lens exactly once
    groups = load_yaml(CONFIG / "groups.yaml")["groups"]
    placed: dict[str, str] = {}
    for g, spec in groups.items():
        for lid in spec.get("lenses", []):
            if lid in placed:
                rep.err(f"groups.yaml: lens {lid} in both {placed[lid]} and {g}")
            placed[lid] = g
            if lid not in lens_ids:
                rep.err(f"groups.yaml: group {g} names missing lens {lid}")
    for lid in lens_ids:
        if lid not in placed:
            rep.err(f"groups.yaml: lens {lid} is in no group")

    # integration cases
    integ = ROOT / "integration"
    for p in sorted(integ.glob("*.yaml")):
        c = load_yaml(p)
        stats["cases"] += 1
        schema_errors(v_case, c, f"integration/{p.name}", rep)
        for tid in (c or {}).get("expect", {}).get("traps", []):
            if tid not in seen_trap_ids:
                rep.err(f"integration/{p.name}: expects unknown trap {tid}")
    return stats


def main(argv: list[str]) -> int:
    rep = Report()
    stats = lint(rep)
    quiet = "--quiet" in argv
    if not quiet:
        for w in rep.warnings:
            print(f"warn  {w}")
    for e in rep.errors:
        print(f"ERROR {e}")
    print(
        f"lint: {stats['lenses']} lenses, {stats['traps']} traps ({stats['verified']} verified, "
        f"{stats['unverified']} unverified), {stats['sources']} sources, {stats['cases']} cases; "
        f"{len(rep.errors)} errors, {len(rep.warnings)} warnings"
    )
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
