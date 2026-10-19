"""Validate a minesweeper register against vendored copies of register.v1.json and finding.v1.json.

The schemas in ./schemas are copies of ~/.claude/skills/minesweeper/engine/schemas (read 2026-10-19; see
docs/intake-format.md). This is a small validator for exactly the keywords those files use. It does not
import minesweeper code and does not re-derive severity tiers from answers (minesweeper's own validate.py does).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "null": type(None)}


def _is(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def _validate(v, s: dict, path: str, errs: list[str]) -> None:
    if "$ref" in s:
        s = _load(s["$ref"])
    if "const" in s and v != s["const"]:
        errs.append(f"{path}: must be {s['const']!r}")
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{path}: {v!r} not one of {s['enum']}")
    if "type" in s:
        ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(_is(v, t) for t in ts):
            errs.append(f"{path}: expected {'/'.join(ts)}, got {type(v).__name__}")
            return
    if isinstance(v, str):
        if "pattern" in s and not re.search(s["pattern"], v):
            errs.append(f"{path}: {v!r} does not match pattern {s['pattern']}")
        if "minLength" in s and len(v) < s["minLength"]:
            errs.append(f"{path}: shorter than {s['minLength']}")
        if s.get("format") == "date" and not DATE_RE.match(v):
            errs.append(f"{path}: {v!r} is not a date (YYYY-MM-DD)")
    if isinstance(v, int) and not isinstance(v, bool) and "minimum" in s and v < s["minimum"]:
        errs.append(f"{path}: below minimum {s['minimum']}")
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                errs.append(f"{path}: missing required {k}")
        props = s.get("properties", {})
        if s.get("additionalProperties") is False:
            for k in v:
                if k not in props:
                    errs.append(f"{path}: unexpected property {k}")
        for k, sub in props.items():
            if k in v:
                _validate(v[k], sub, f"{path}.{k}", errs)
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            errs.append(f"{path}: needs at least {s['minItems']} item(s)")
        if "items" in s:
            for i, x in enumerate(v):
                _validate(x, s["items"], f"{path}[{i}]", errs)
    for rule in s.get("allOf", []):
        cond = rule["if"]
        probe: list[str] = []
        _validate(v, {"type": "object", **cond}, path, probe)
        if not probe:  # the `if` holds
            t = dict(rule["then"])
            _validate(v, {"type": "object", **t}, path, errs)


def validate_register(data) -> list[str]:
    errs: list[str] = []
    _validate(data, _load("register.v1.json"), "register", errs)
    if isinstance(data, dict):
        ids = [f.get("id") for f in data.get("findings", []) if isinstance(f, dict)]
        for i in {x for x in ids if ids.count(x) > 1}:
            errs.append(f"register.findings: duplicate id {i}")
    return errs
