"""Experiment records: experiments/<id>/results.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
REQUIRED = ("question", "candidates", "metrics", "decision_rule_preregistered", "result", "as_of")


def check_resolved(d: Path) -> list[str]:
    """experiments/<id>/resolved.json: a choice settled by research, with its sources and date."""
    tag = d.name
    try:
        data = json.loads((d / "resolved.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{tag}: resolved.json is not valid JSON: {e}"]
    if not isinstance(data, dict):
        return [f"{tag}: resolved.json must be an object"]
    errs = [f"{tag}: resolved.json missing {k}" for k in ("question", "resolved_by")
            if not isinstance(data.get(k), str) or not data[k].strip()]
    src = data.get("sources")
    if not isinstance(src, list) or not any(isinstance(x, str) and x.strip() for x in src):
        errs.append(f"{tag}: resolved.json missing sources (at least one)")
    if not isinstance(data.get("as_of"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["as_of"]):
        errs.append(f"{tag}: resolved.json missing as_of (YYYY-MM-DD)")
    return errs


def check_dir(d: Path) -> list[str]:
    if (d / "resolved.json").is_file():
        return check_resolved(d) + (check_dir_results(d) if (d / "results.json").is_file() else [])
    return check_dir_results(d)


def check_dir_results(d: Path) -> list[str]:
    tag = d.name
    rp = d / "results.json"
    if not rp.is_file():
        return [f"{tag}: results.json not found"]
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{tag}: results.json is not valid JSON: {e}"]
    if not isinstance(data, dict):
        return [f"{tag}: results.json must be an object"]
    errs: list[str] = []
    for k in REQUIRED:
        if k not in data or data[k] in (None, "", [], {}):
            errs.append(f"{tag}: missing {k}")
    if isinstance(data.get("as_of"), str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["as_of"]):
        errs.append(f"{tag}: as_of must be YYYY-MM-DD")
    # candidates: each cited to a dated enumeration file in this directory
    names: list[str] = []
    cands = data.get("candidates")
    if isinstance(cands, list):
        for i, c in enumerate(cands):
            if not isinstance(c, dict) or not c.get("name") or not c.get("enumeration"):
                errs.append(f"{tag}: candidates[{i}] must be an object with name and enumeration (a bare candidate "
                            f"list with no enumeration file is rejected)")
                continue
            names.append(c["name"])
            en = str(c["enumeration"])
            if "/" in en or "\\" in en or en.startswith("."):
                errs.append(f"{tag}: candidate {c['name']} enumeration {en} must be a file in the same directory")
                continue
            ep = d / en
            if not ep.is_file():
                errs.append(f"{tag}: candidate {c['name']} cites enumeration file {en} which does not exist")
                continue
            text = ep.read_text(encoding="utf-8", errors="replace")
            if not DATE_RE.search(text):
                errs.append(f"{tag}: enumeration file {en} carries no date (YYYY-MM-DD in its text)")
            if c["name"].lower() not in text.lower():
                errs.append(f"{tag}: candidate {c['name']} does not appear in its enumeration file {en}")
        if len(names) < 2 and not errs:
            errs.append(f"{tag}: an experiment compares at least two candidates")
    elif "candidates" in data:
        errs.append(f"{tag}: candidates must be a list")
    mnames: list[str] = []
    ms = data.get("metrics")
    if isinstance(ms, list):
        for m in ms:
            n = m.get("name") if isinstance(m, dict) else None
            if n:
                mnames.append(n)
        if len(set(mnames)) < 2:
            errs.append(f"{tag}: need at least two metrics (multi-metric); got {len(set(mnames))}")
    rule = data.get("decision_rule_preregistered")
    if isinstance(rule, str) and rule.strip():
        one_line = "\n" not in rule.strip() and len(rule.strip()) < 120 and re.fullmatch(r"[\w./-]+\.\w{1,5}", rule.strip())
        if one_line and not (d / rule.strip()).is_file():
            errs.append(f"{tag}: decision_rule_preregistered path {rule.strip()} does not exist")
        elif not one_line and len(rule.strip()) < 20:
            errs.append(f"{tag}: decision_rule_preregistered text is too short to be a rule")
    res = data.get("result")
    if isinstance(res, dict):
        basis = res.get("basis") or []
        if len(set(basis)) < 2:
            errs.append(f"{tag}: result decided on a single-metric basis ({basis}); the winner must rest on at least two metrics")
        for b in basis:
            if mnames and b not in mnames:
                errs.append(f"{tag}: result.basis names {b}, which is not a declared metric")
        w = res.get("winner")
        if w is not None and names and w not in names:
            errs.append(f"{tag}: winner {w} is not a candidate")
        if w is None and res.get("status") != "no-winner":
            errs.append(f"{tag}: result has no winner and no explicit status 'no-winner'")
        scores = res.get("scores")
        if not isinstance(scores, dict):
            errs.append(f"{tag}: result.scores is required")
        else:
            for n in names:
                for m in mnames:
                    if not isinstance(scores.get(n), dict) or m not in scores[n]:
                        errs.append(f"{tag}: result.scores lacks {m} for candidate {n}")
    elif "result" in data:
        errs.append(f"{tag}: result must be an object")
    return errs


def check_root(root: Path, only: str | None = None) -> list[str]:
    root = Path(root)
    if not root.is_dir():
        return [f"{root} not found"]
    dirs = [root / only] if only else sorted(p for p in root.iterdir() if p.is_dir())
    errs: list[str] = []
    for d in dirs:
        errs += check_dir(d)
    return errs
