#!/usr/bin/env python3
"""Check the file-scope block of a PRD.

The PRD carries one fenced block labelled `yaml scope`. This script validates it against the
repository, prints the concrete files behind a unit's globs, and reports edits that fall outside a
unit's scope. It reports and never reverts: the scope is a soft sandbox.

    check_scope.py PRD.md [--repo DIR] [--strict]
    check_scope.py PRD.md --expand U1
    check_scope.py PRD.md --unit U1 --diff [BASE]

Glob syntax: `*` matches within one path segment, `**` matches across segments, `?` matches one
character, and a trailing `/` means everything below that directory. Character classes are not
supported.

Exit status: 0 when clean, 1 when there are errors (or warnings under --strict, or edits outside
scope under --diff), 2 when the scope block cannot be read.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

FENCE = re.compile(r"^```ya?ml[ \t]+scope[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)
TOO_BROAD = {"*", "**", "**/*", "./**", "./*"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache"}


class ScopeError(Exception):
    """The scope block is missing or unreadable."""


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern.endswith("/"):
        pattern += "**"
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def literal_prefix(pattern: str) -> str:
    if pattern.startswith("./"):
        pattern = pattern[2:]
    cut = len(pattern)
    for ch in "*?":
        idx = pattern.find(ch)
        if idx != -1:
            cut = min(cut, idx)
    return pattern[:cut]


def has_wildcard(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?") or pattern.endswith("/")


def list_files(repo: Path) -> list[str]:
    """Tracked and untracked-but-not-ignored files, relative to repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
        )
        names = {line for line in proc.stdout.splitlines() if line}
        return sorted(n for n in names if (repo / n).is_file())
    except (subprocess.CalledProcessError, FileNotFoundError):
        found: list[str] = []
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                found.append(os.path.relpath(os.path.join(root, name), repo).replace(os.sep, "/"))
        return sorted(found)


def load_scope(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        raw = text
    else:
        blocks = FENCE.findall(text)
        if not blocks:
            raise ScopeError(f"{path}: no fenced block labelled `yaml scope`")
        if len(blocks) > 1:
            raise ScopeError(f"{path}: {len(blocks)} `yaml scope` blocks, expected exactly one")
        raw = blocks[0]
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ScopeError(f"{path}: scope block is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ScopeError(f"{path}: scope block must be a mapping with a `units` list")
    return data


def _str_list(unit: dict[str, Any], key: str, errors: list[str], required: bool = False) -> list[str]:
    value = unit.get(key, [])
    uid = unit.get("id", "?")
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        errors.append(f"{uid}: `{key}` must be a list of non-empty strings")
        return []
    if required and not value:
        errors.append(f"{uid}: `{key}` must not be empty")
    return value


def validate(data: dict[str, Any], files: list[str], repo: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return ["`units` must be a non-empty list"], warnings

    parsed: dict[str, dict[str, Any]] = {}
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("id"), str) or not unit["id"]:
            errors.append("every unit needs a string `id`")
            continue
        uid = unit["id"]
        if uid in parsed:
            errors.append(f"{uid}: duplicate unit id")
            continue
        parsed[uid] = {
            "owns": _str_list(unit, "owns", errors, required=True),
            "new": _str_list(unit, "new", errors),
            "reads": _str_list(unit, "reads", errors),
            "depends_on": _str_list(unit, "depends_on", errors),
            "entry_points": unit.get("entry_points") or [],
            "confidence": unit.get("confidence", "high"),
        }

    file_set = set(files)
    all_new = {n for u in parsed.values() for n in u["new"]}
    universe = file_set | all_new
    owns_rx = {uid: [(p, glob_to_regex(p)) for p in u["owns"]] for uid, u in parsed.items()}

    owned: dict[str, set[str]] = {}
    for uid, u in parsed.items():
        for pat in u["owns"] + u["reads"]:
            if pat in TOO_BROAD:
                errors.append(f"{uid}: pattern '{pat}' is too broad")
        for path in u["new"]:
            if has_wildcard(path):
                errors.append(f"{uid}: new path '{path}' must be an explicit file path, not a glob")
            elif not any(rx.match(path) for _, rx in owns_rx[uid]):
                errors.append(f"{uid}: new path '{path}' is not covered by any `owns` pattern")
            if path in file_set:
                warnings.append(f"{uid}: new path '{path}' already exists")
        matched: set[str] = set(u["new"])
        for pat, rx in owns_rx[uid]:
            hits = {f for f in files if rx.match(f)}
            matched |= hits
            if not hits and not any(rx.match(n) for n in u["new"]):
                errors.append(f"{uid}: owns '{pat}' matches no files and no `new` path falls under it")
        owned[uid] = matched
        for pat in u["reads"]:
            rx = glob_to_regex(pat)
            if not any(rx.match(f) for f in universe):
                errors.append(f"{uid}: reads '{pat}' matches no files")
        for dep in u["depends_on"]:
            if dep not in parsed:
                errors.append(f"{uid}: depends_on '{dep}' is not a unit")
            elif dep == uid:
                errors.append(f"{uid}: depends_on itself")
        eps = u["entry_points"]
        if not isinstance(eps, list):
            errors.append(f"{uid}: `entry_points` must be a list")
            continue
        scope_rx = [rx for _, rx in owns_rx[uid]] + [glob_to_regex(p) for p in u["reads"]]
        for ep in eps:
            if not isinstance(ep, dict) or not isinstance(ep.get("path"), str):
                errors.append(f"{uid}: each entry point needs a `path`")
                continue
            ep_path = ep["path"]
            if ep_path not in universe:
                errors.append(f"{uid}: entry point '{ep_path}' does not exist")
                continue
            if not any(rx.match(ep_path) for rx in scope_rx):
                warnings.append(f"{uid}: entry point '{ep_path}' is outside this unit's owns and reads")
            symbol = ep.get("symbol")
            if symbol and ep_path in file_set:
                tail = str(symbol).split(".")[-1]
                text = (repo / ep_path).read_text(encoding="utf-8", errors="ignore")
                if tail not in text:
                    warnings.append(f"{uid}: symbol '{symbol}' not found in {ep_path} (stale?)")
        if u["confidence"] == "low":
            warnings.append(f"{uid}: confidence is low, so its first step should be a bounded exploration")

    # A cycle in depends_on means no valid order exists.
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            errors.append("depends_on cycle: " + " -> ".join(trail + [node]))
            return
        state[node] = 1
        for dep in parsed[node]["depends_on"]:
            if dep in parsed:
                visit(dep, trail + [node])
        state[node] = 2

    for uid in parsed:
        visit(uid, [])

    ids = list(parsed)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            both = sorted(owned[a] & owned[b])
            if both:
                shown = ", ".join(both[:5]) + (f" and {len(both) - 5} more" if len(both) > 5 else "")
                errors.append(f"{a} and {b} both own: {shown}")
            for src, dst in ((a, b), (b, a)):
                for path in parsed[src]["new"]:
                    if any(rx.match(path) for _, rx in owns_rx[dst]):
                        errors.append(f"{src}: new path '{path}' falls under {dst}'s owns")
            for pa in parsed[a]["owns"]:
                for pb in parsed[b]["owns"]:
                    wa, wb = has_wildcard(pa), has_wildcard(pb)
                    if wa and wb:
                        xa, xb = literal_prefix(pa), literal_prefix(pb)
                        if xa.startswith(xb) or xb.startswith(xa):
                            warnings.append(f"{a} '{pa}' and {b} '{pb}' may overlap on files that do not exist yet")
                    elif not wa and glob_to_regex(pb).match(pa.removeprefix("./")):
                        errors.append(f"{a} owns '{pa}', which falls under {b}'s '{pb}'")
                    elif not wb and glob_to_regex(pa).match(pb.removeprefix("./")):
                        errors.append(f"{b} owns '{pb}', which falls under {a}'s '{pa}'")
    # De-duplicate while keeping order.
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def expand(data: dict[str, Any], uid: str, files: list[str]) -> str:
    unit = next((u for u in data["units"] if u.get("id") == uid), None)
    if unit is None:
        raise ScopeError(f"no unit '{uid}'")
    lines = [f"unit {uid}: {unit.get('goal', '')}".rstrip()]
    for key in ("owns", "reads"):
        lines.append(f"{key}:")
        seen: set[str] = set()
        for pat in unit.get(key) or []:
            rx = glob_to_regex(pat)
            for f in files:
                if rx.match(f) and f not in seen:
                    seen.add(f)
                    lines.append(f"  {f}")
    lines.append("new:")
    for path in unit.get("new") or []:
        lines.append(f"  {path}")
    lines.append("entry points:")
    for ep in unit.get("entry_points") or []:
        why = f"  ({ep['why']})" if ep.get("why") else ""
        lines.append(f"  {ep['path']}  {ep.get('symbol', '')}{why}".rstrip())
    return "\n".join(lines)


def changed_files(repo: Path, base: str) -> list[str]:
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", base],
                          capture_output=True, text=True, check=True).stdout.splitlines()
    new = subprocess.run(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted({f for f in diff + new if f})


def out_of_scope(data: dict[str, Any], uid: str, changed: list[str]) -> list[tuple[str, str]]:
    units = {u["id"]: u for u in data["units"] if isinstance(u, dict) and "id" in u}
    if uid not in units:
        raise ScopeError(f"no unit '{uid}'")
    mine = [glob_to_regex(p) for p in units[uid].get("owns") or []]
    mine_new = set(units[uid].get("new") or [])
    result: list[tuple[str, str]] = []
    for f in changed:
        if f in mine_new or any(rx.match(f) for rx in mine):
            continue
        owner = next((oid for oid, u in units.items() if oid != uid
                      and any(glob_to_regex(p).match(f) for p in u.get("owns") or [])), None)
        result.append((f, f"owned by {owner}" if owner else "owned by no unit"))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("prd", type=Path, help="PRD markdown file, or a .yaml scope file")
    ap.add_argument("--repo", type=Path, default=Path("."), help="repository root (default: .)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--expand", metavar="UNIT", help="print the concrete files behind a unit's globs")
    ap.add_argument("--unit", metavar="UNIT", help="unit to check a diff against (with --diff)")
    ap.add_argument("--diff", nargs="?", const="HEAD", metavar="BASE",
                    help="report edits outside the unit's scope (default base: HEAD)")
    args = ap.parse_args(argv)

    try:
        data = load_scope(args.prd)
        repo = args.repo.resolve()
        files = list_files(repo)
        if args.expand:
            print(expand(data, args.expand, files))
            return 0
        if args.diff is not None:
            if not args.unit:
                raise ScopeError("--diff needs --unit")
            stray = out_of_scope(data, args.unit, changed_files(repo, args.diff))
            for path, why in stray:
                print(f"OUT OF SCOPE  {path}  ({why})")
            print(f"{args.unit}: {len(stray)} edit(s) outside scope" if stray
                  else f"{args.unit}: all edits inside scope")
            return 1 if stray else 0
    except ScopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"error: git failed: {exc.stderr.strip() if exc.stderr else exc}", file=sys.stderr)
        return 2

    errors, warnings = validate(data, files, repo)
    count = len(data["units"]) if isinstance(data.get("units"), list) else 0
    print(f"scope: {count} unit(s), {len(files)} file(s) in repo")
    for msg in errors:
        print(f"ERROR  {msg}")
    for msg in warnings:
        print(f"WARN   {msg}")
    failed = bool(errors) or (args.strict and bool(warnings))
    print("FAILED" if failed else "OK", f"({len(errors)} error(s), {len(warnings)} warning(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
