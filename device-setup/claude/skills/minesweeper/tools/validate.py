#!/usr/bin/env python3
"""Validate run outputs against the engine schemas and the policy, and compute gates.

  python3 tools/validate.py claims  RUN_DIR/claims.json
  python3 tools/validate.py register RUN_DIR/register.json [--write-gates]

Beyond the schema, a register must satisfy the policy rules a model could fudge:
  - a confirmed finding cites at least one primary quote, note, report, experiment or check;
  - a finding matched to an unverified trap can be confirmed only with its own primary evidence;
  - severity.tier equals the tier of the first question answered yes, in policy order;
  - a dismissal that says "out of scope" on a never-out-of-scope topic must carry a consequence;
  - every quarantine entry points at existing findings.
--write-gates recomputes register.gates (critical -> blocking, high -> needs_disposition).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, load_yaml, validator  # noqa: E402

TIER_ORDER = ["critical", "high", "medium", "low"]


def expected_tier(answers: list[dict], questions: list[dict]) -> str | None:
    by_q = {a["q"]: a["a"] for a in answers}
    by_id = {a.get("id"): a["a"] for a in answers if a.get("id")}
    for q in questions:
        ans = by_id.get(q["id"], by_q.get(q["q"]))
        if ans is None:
            return None  # unanswered question before the first yes: cannot reproduce the tier
        if ans:
            return q["tier"]
    return "low"


def check_register(reg: dict) -> list[str]:
    policy = load_yaml(CONFIG / "policy.yaml")
    qs = policy["severity_questions"]
    errs = []
    ids = {f["id"] for f in reg.get("findings", [])}
    for f in reg.get("findings", []):
        fid = f["id"]
        if f["status"] == "confirmed":
            strong = [e for e in f.get("evidence", []) if e["kind"] != "quote" or e.get("tier", "primary") == "primary"]
            if not strong:
                errs.append(f"{fid}: confirmed with no primary evidence")
            if f.get("trap_status") == "unverified" and not any(e["kind"] in ("quote", "check", "experiment", "note", "report") for e in f.get("evidence", [])):
                errs.append(f"{fid}: unverified trap confirmed without its own evidence")
        sev = f.get("severity")
        if sev:
            want = expected_tier(sev.get("answers", []), qs)
            if want is None:
                errs.append(f"{fid}: severity answers skip a policy question before the first yes")
            elif want != sev["tier"]:
                errs.append(f"{fid}: tier {sev['tier']} but policy questions give {want}")
        if f["status"] == "dismissed" and re.search(r"out of scope", f.get("dismissal_reason", ""), re.I):
            if not f.get("out_of_scope_consequence"):
                errs.append(f"{fid}: dismissed as out of scope without a written consequence")
    for q in reg.get("quarantine", []):
        for fid in q["finding_ids"]:
            if fid not in ids:
                errs.append(f"quarantine {q['locator']}: unknown finding {fid}")
    return errs


def gates(reg: dict) -> dict:
    live = [f for f in reg.get("findings", []) if f["status"] in ("confirmed", "plausible")]
    return {
        "blocking": [f["id"] for f in live if (f.get("severity") or {}).get("tier") == "critical"],
        "needs_disposition": [f["id"] for f in live if (f.get("severity") or {}).get("tier") == "high" and not f.get("disposition")],
    }


def main(argv):
    if len(argv) < 2 or argv[0] not in ("claims", "register"):
        print(__doc__, file=sys.stderr)
        return 2
    kind, path = argv[0], Path(argv[1])
    doc = json.loads(path.read_text(encoding="utf-8"))
    v = validator("claims.v1.json" if kind == "claims" else "register.v1.json")
    errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(doc)]
    if kind == "register" and not errs:
        errs += check_register(doc)
        if "--write-gates" in argv:
            doc["gates"] = gates(doc)
            path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    for e in errs:
        print(f"ERROR {e}")
    print(f"{kind}: {path} {'valid' if not errs else f'{len(errs)} errors'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
