"""Sweep records (docs/requirements/sweeps/<source-sha>.json), applying them to the ledger, and the gate."""
from __future__ import annotations

import copy
import difflib
import json
import re
import subprocess
from pathlib import Path

import yaml

from . import ledger as L
from .register import validate_register

RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, None: 4}
BY_RE = re.compile(r"^(human|codex):\S+")
NUM_RE = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?")


class IntakeError(Exception):
    def __init__(self, msgs, code=1):
        self.msgs = [msgs] if isinstance(msgs, str) else list(msgs)
        self.code = code


def sweeps_dir(ledger: Path) -> Path:
    return Path(ledger).parent / "sweeps"


def record_path(ledger: Path, src_sha: str) -> Path:
    return sweeps_dir(ledger) / f"{src_sha}.json"


def lines_in(locator: str) -> set[int]:
    out: set[int] = set()
    for a, b in NUM_RE.findall(locator or ""):
        lo, hi = int(a), int(b or a)
        out.update(range(lo, max(lo, hi) + 1))
    return out


def resolve_source(source: Path | None, ledger: Path, register: dict | None = None) -> Path:
    if source:
        return Path(source)
    cands: list[str] = []
    if ledger.is_file():
        _, rows = L.read(ledger)
        for r in rows:
            m = L.REF_RE.match(r.get("source_ref", ""))
            if m:
                cands.append(m.group("file"))
                break
    if register:
        cands.append(register.get("brief", {}).get("path", ""))
    for c in filter(None, cands):
        for base in (Path("."), ledger.parent, *ledger.parent.parents):
            if (base / c).is_file():
                return base / c
    raise IntakeError("cannot locate the source file; pass --source", 2)


# ---------------------------------------------------------------- record building
def build_record(register: dict, claims: dict | None, src_sha: str, reg_sha: str) -> dict:
    claim_by = {c["id"]: c for c in (claims or {}).get("claims", [])}
    omissions = []
    claim_lines: set[int] = set()
    omission_of: dict[str, str] = {}
    for c in claim_by.values():
        if c["kind"] == "omission":
            req = f"BP-{c['id']}"
            omission_of[c["id"]] = req
            omissions.append({"req_id": req, "claim_id": c["id"], "lens": c["locator"].split(".", 1)[0],
                              "text": c["text"], "text_sha": L.line_sha(c["text"]), "locator": c["locator"]})
        else:
            claim_lines |= lines_in(c["locator"])
    quar: dict[str, set[int]] = {}
    for q in register["quarantine"]:
        ls = lines_in(q["locator"])
        claim_lines |= ls
        for fid in q["finding_ids"]:
            quar.setdefault(fid, set()).update(ls)
    findings = []
    for f in register["findings"]:
        ls: set[int] = set(quar.get(f["id"], set()))
        reqs = []
        for cid in f["claim_ids"]:
            c = claim_by.get(cid)
            if c and c["kind"] != "omission":
                ls |= lines_in(c["locator"])
            if cid in omission_of:
                reqs.append(omission_of[cid])
        findings.append({"id": f["id"], "lens": f["lens"], "status": f["status"],
                         "tier": (f.get("severity") or {}).get("tier"), "disposition": f.get("disposition"),
                         "lines": sorted(ls), "omission_reqs": sorted(reqs), "quarantined": f["id"] in quar,
                         "owner_question": f.get("owner_question")})
    conv = register["convergence"]
    return {"schema_version": 1, "source_sha256": src_sha, "register_sha256": reg_sha,
            "register_path": None, "date": register["run"]["date"], "mode": register["run"]["mode"],
            "calibrated": register["run"]["calibrated"],
            "lenses": [x["id"] for x in register["run"]["lenses"]],
            "converged": conv["converged"], "stop_reason": conv["stop_reason"],
            "claim_lines": sorted(claim_lines), "omissions": omissions, "findings": findings, "signoffs": []}


def _open_findings(rec: dict) -> list[dict]:
    return [f for f in rec["findings"] if f["status"] != "dismissed"]


def signed(rec: dict) -> set[str]:
    return {s["finding"] for s in rec.get("signoffs", [])}


def open_critical_ids(rec: dict) -> set[str]:
    return {f["id"] for f in _open_findings(rec) if f["tier"] == "critical" and f["id"] not in signed(rec)}


# ---------------------------------------------------------------- applying a record to the ledger
def apply_record(rows: list[dict], rec: dict, source: Path) -> list[dict]:
    rows = copy.deepcopy(rows)
    have = {r["req_id"] for r in rows}
    for o in rec["omissions"]:
        if o["req_id"] not in have:
            rows.append({"req_id": o["req_id"], "source_ref": f"omission:{o['locator']}", "text_sha": o["text_sha"],
                         "category": f"best-practice:{o['lens']}", "trust": "trusted", "finding_ids": "",
                         "disposition": "", "status": "unserved", "slice_ids": "",
                         "artifact_or_waits_on": ""})
    sg = signed(rec)
    for r in rows:
        n = L.line_of(r, source)
        is_om = r.get("source_ref", "").startswith("omission:")
        if n is None and not is_om:
            continue
        rel = [f for f in _open_findings(rec) if (n is not None and n in f["lines"]) or r["req_id"] in f["omission_reqs"]]
        rel.sort(key=lambda f: (RANK[f["tier"]], f["id"]))
        r["finding_ids"] = ";".join(sorted(f["id"] for f in rel))
        rej = [f for f in rel if f["disposition"] == "decline" or f["quarantined"]]
        cond = [f for f in rel if f["tier"] in ("critical", "high")]
        if rej:
            r["trust"], pick = f"rejected({rej[0]['id']})", rej[0]
        elif cond:
            r["trust"], pick = f"conditioned({cond[0]['id']})", cond[0]
        else:
            r["trust"], pick = "trusted", None
        r["disposition"] = (pick or {}).get("disposition") or ""
        oc = [f["id"] for f in rel if f["tier"] == "critical" and f["id"] not in sg]
        st = L.base_status(r["status"])
        waits = r.get("artifact_or_waits_on", "")
        if oc:
            r["status"] = "blocked; open critical " + ",".join(oc)
            r["artifact_or_waits_on"] = "owner sign-off " + ",".join(oc)
        else:
            if waits.startswith("owner sign-off"):
                r["artifact_or_waits_on"] = ""
                if st == "blocked":
                    st = "unserved"
            r["status"] = st
    return rows


# ---------------------------------------------------------------- record-sweep
def record_sweep(register_path: Path, ledger: Path, source: Path | None, claims_path: Path | None) -> list[str]:
    try:
        reg = json.loads(Path(register_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise IntakeError(f"register: cannot read {register_path}: {e}", 2)
    errs = validate_register(reg)
    if errs:
        raise IntakeError(["register invalid against register.v1/finding.v1:"] + errs)
    src = resolve_source(source, ledger, reg)
    src_sha = L.file_sha(src)
    if reg["brief"]["sha256"] != src_sha:
        raise IntakeError(f"register brief.sha256 {reg['brief']['sha256'][:12]} is not the sha256 of {src} "
                          f"({src_sha[:12]}): the sweep ran on different text")
    if reg["run"]["mode"] == "eval":
        raise IntakeError("register mode 'eval' is retrieval-only calibration, not a sweep of this brief")
    cp = claims_path
    if cp is None and reg["run"].get("claims_path"):
        guess = Path(register_path).parent / reg["run"]["claims_path"]
        cp = guess if guess.is_file() else None
    claims = None
    if cp:
        try:
            claims = json.loads(Path(cp).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise IntakeError(f"claims: cannot read {cp}: {e}", 2)
        if claims.get("brief", {}).get("sha256") != src_sha:
            raise IntakeError("claims brief.sha256 does not match the source")
    rec = build_record(reg, claims, src_sha, L.file_sha(Path(register_path)))
    rec["register_path"] = str(register_path)
    rp = record_path(ledger, src_sha)
    if rp.is_file():
        rec["signoffs"] = json.loads(rp.read_text())["signoffs"]
    header, rows = L.read(ledger)
    if not all(c in header for c in L.COLUMNS):
        raise IntakeError("ledger lacks the full column set; extract it with the full header first")
    new_rows = apply_record(rows, rec, src)
    errs = L.check(src, ledger, Path("."))  # source state before writing: refuse to sweep a drifted ledger
    if errs:
        raise IntakeError(["ledger does not check against the source before the sweep is applied:"] + errs)
    post = _check_rows(src, new_rows)
    if post:
        raise IntakeError(["ledger would be invalid after applying the sweep:"] + post)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    L.write(ledger, new_rows)
    return [f"recorded {rp}", f"updated {ledger} ({len(new_rows)} rows)"]


def _check_rows(src: Path, rows: list[dict]) -> list[str]:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "l.tsv"
        L.write(p, rows)
        return L.check(src, p, Path("."))


# ---------------------------------------------------------------- signoff
def signoff(ledger: Path, source: Path | None, finding: str, by: str) -> list[str]:
    if not BY_RE.match(by):
        raise IntakeError("--by must be human:REF or codex:REF", 2)
    src = resolve_source(source, ledger)
    rp = record_path(ledger, L.file_sha(src))
    if not rp.is_file():
        raise IntakeError(f"no sweep record {rp.name}; run record-sweep first", 2)
    rec = json.loads(rp.read_text())
    crit = {f["id"] for f in _open_findings(rec) if f["tier"] == "critical"}
    if finding not in crit:
        raise IntakeError(f"{finding} is not a non-dismissed Critical finding in the sweep record", 2)
    if finding not in signed(rec):
        rec["signoffs"].append({"finding": finding, "by": by})
    _, rows = L.read(ledger)
    new_rows = apply_record(rows, rec, src)
    rp.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    L.write(ledger, new_rows)
    return [f"signed off {finding} by {by}"]


# ---------------------------------------------------------------- gate
def _slice_ids(slice_dir: Path) -> list[str]:
    p = Path(slice_dir) / "proposal.md"
    if not p.is_file():
        raise IntakeError(f"slice: {p} not found", 2)
    parts = p.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise IntakeError(f"slice: {p} has no frontmatter", 2)
    ids = (yaml.safe_load(parts[1]) or {}).get("source_requirement_ids") or []
    return [str(i) for i in ids]


def _git_show(source: Path, since: str) -> str:
    src = Path(source).resolve()
    p = subprocess.run(["git", "-C", str(src.parent), "show", f"{since}:./{src.name}"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise IntakeError(f"--since {since}: cannot read {src.name} at that revision: {p.stderr.strip()}", 2)
    return p.stdout


def gate(ledger: Path, source: Path | None, slice_dir: Path | None = None, since: str | None = None,
         repo_root: Path | None = None) -> list[str]:
    src = resolve_source(source, ledger)
    src_sha = L.file_sha(src)
    errs: list[str] = []
    old_text = _git_show(src, since) if since else None
    changed: list[int] = []
    changed_note = ""
    if old_text is not None:
        import hashlib
        if hashlib.sha256(old_text.encode()).hexdigest() != src_sha:
            old = [x.strip() for x in old_text.split("\n")]
            new = [x.strip() for x in L.source_lines(src)]
            for tag, _, _, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
                if tag in ("replace", "insert"):
                    changed += [j + 1 for j in range(j1, j2) if new[j]]
            changed_note = (f"source changed since {since} (lines {', '.join(map(str, changed)) or 'removed'}); "
                            f"a new sweep record for sha {src_sha[:12]} is required")
    rp = record_path(ledger, src_sha)
    if not rp.is_file():
        if changed_note:
            errs.append(changed_note)
        errs.append(f"no sweep record for source sha {src_sha} (expected {rp}); the minesweeper sweep did not "
                    f"run or was not recorded with record-sweep")
        return errs
    rec = json.loads(rp.read_text())
    errs += L.check(src, ledger, repo_root, open_critical=open_critical_ids(rec))
    if not rec["converged"]:
        errs.append(f"sweep did not converge (stop_reason {rec['stop_reason']}); finish or accept it explicitly")
    for f in _open_findings(rec):
        if f["tier"] is None:
            errs.append(f"{f['id']}: unrated {f['status']} finding; assign a severity or dismiss it")
        elif f["tier"] in ("critical", "high") and not f["disposition"]:
            errs.append(f"{f['id']}: {f['tier'].capitalize()} finding has no recorded disposition")
        if f["tier"] in ("critical", "high") and not f["lines"] and not f["omission_reqs"]:
            errs.append(f"{f['id']}: {f['tier']} finding maps to no ledger row (pass --claims so claim lines are known)")
    header, rows = L.read(ledger)
    if all(c in header for c in L.COLUMNS):
        want = {r["req_id"]: r for r in apply_record(rows, rec, src)}
        for r in rows:
            w = want[r["req_id"]]
            if r["trust"] != w["trust"] or r["finding_ids"] != w["finding_ids"]:
                errs.append(f"{r['req_id']}: ledger says trust {r['trust']!r} findings {r['finding_ids']!r} but the "
                            f"sweep record implies {w['trust']!r} / {w['finding_ids']!r}")
        for rid in set(want) - {r["req_id"] for r in rows}:
            errs.append(f"{rid}: omitted best-practice row from the sweep record is missing from the ledger")
    if since and changed:
        miss = [n for n in changed if n not in set(rec["claim_lines"])]
        for n in miss:
            errs.append(f"changed line {n} is not covered by any claim in the new sweep record "
                        f"(re-run the delta sweep with its claims.json)")
    if slice_dir is not None:
        by = {r["req_id"]: r for r in rows}
        oc = open_critical_ids(rec)
        for i in _slice_ids(slice_dir):
            r = by.get(i)
            if r is None:
                errs.append(f"slice: source requirement {i} is not in the ledger")
                continue
            hit = oc & {x for x in r["finding_ids"].split(";") if x}
            if hit or L.OPEN_CRITICAL_RE.search(r["status"]):
                errs.append(f"slice: {i} is {r['trust']} on open Critical {', '.join(sorted(hit)) or r['status']}; "
                            f"blocked until owner sign-off")
    return errs
