"""``qa promote-notes``: turn the local QA attempt log (.sf/slices/<id>/) into the committed DIR/qa-notes.md.

One block per failure signature, no timestamps, so an unchanged log gives byte-identical output.
"""
import json
import os
import re
from pathlib import Path

from .feedback import check_text
from .store import check_signature

OUT = "qa-notes.md"


class NotesError(Exception):
    pass


def _walk_no_symlink(base: Path, target: Path, what: str) -> None:
    """Every path component from ``base`` down to ``target`` must be a real directory/file (no symlink)."""
    cur = base
    for part in target.relative_to(base).parts:
        cur = cur / part
        if cur.is_symlink():
            raise NotesError(f"{what} {cur} is a symlink; refusing to follow it")


def resolve_dir(root, slice_dir) -> Path:
    root_abs = Path(os.path.abspath(root))
    d = Path(slice_dir)
    if not d.is_absolute():
        cand = Path.cwd() / d
        d = cand if cand.exists() or not (root_abs / d).exists() else root_abs / d
    d = Path(os.path.abspath(d))
    try:
        d.relative_to(root_abs)
    except ValueError:
        raise NotesError(f"{slice_dir} is outside the root {root}") from None
    _walk_no_symlink(root_abs, d, "slice directory component")
    if root_abs.resolve() not in (d.resolve(), *d.resolve().parents):
        raise NotesError(f"{slice_dir} escapes the root {root}")
    return d


def _jsonl(p: Path) -> list:
    out = []
    for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if ln.strip():
            try:
                row = json.loads(ln)
            except ValueError:
                raise NotesError(f"{p.name} line {n} is not JSON") from None
            if not isinstance(row, dict):
                raise NotesError(f"{p.name} line {n} is not an object")
            out.append(row)
    return out


def _one(s) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()


def _section(text: str, head: str) -> str:
    m = re.search(rf"^## {head}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def build(root, slice_id: str) -> str:
    logdir = Path(root) / ".sf" / "slices" / slice_id
    if not (logdir / "attempts.jsonl").is_file():
        raise NotesError(f"no QA attempt log for slice {slice_id}: {logdir / 'attempts.jsonl'} not found under .sf")
    _walk_no_symlink(Path(os.path.abspath(root)), Path(os.path.abspath(logdir)), "QA log component")
    attempts = _jsonl(logdir / "attempts.jsonl")
    fails = _jsonl(logdir / "failures.jsonl") if (logdir / "failures.jsonl").is_file() else []
    try:
        proposals = json.loads((logdir / "state.json").read_text(encoding="utf-8")).get("proposals") or {}
    except (OSError, ValueError):
        proposals = {}
    sigs: dict = {}
    for row in attempts + fails:
        s = row.get("signature")
        if s:
            check_signature(s)
            sigs.setdefault(s, {"n": 0, "crit": set(), "obs": ""})
    for row in attempts:
        s = row.get("signature")
        if s:
            if row.get("outcome") == "fail":
                sigs[s]["n"] += 1
            for k in ("criterion", "case"):
                if row.get(k):
                    sigs[s]["crit"].add(_one(row[k]))
    for row in fails:  # latest observation wins
        if row.get("signature") and row.get("error_norm"):
            sigs[row["signature"]]["obs"] = _one(row["error_norm"])[:300]
    exp: dict = {}
    fbdir = logdir / "qa-feedback"
    files = sorted((p for p in fbdir.glob("*.md") if p.stem.isdigit()), key=lambda p: int(p.stem)) if fbdir.is_dir() else []
    for p in files:
        t = p.read_text(encoding="utf-8")
        m = re.search(r"\(signature `([A-Za-z0-9_-]+)`\)", t)
        if m and m.group(1) in sigs:
            s = m.group(1)
            exp[s] = _one(_section(t, "Expected"))[:300]
            sigs[s]["crit"].update(_one(c[2:]) for c in _section(t, "Criteria").splitlines() if c.startswith("- "))
    out = [f"# QA notes for slice {slice_id}\n",
           f"Repeated-failure notes promoted from `.sf/slices/{slice_id}/` by `sf qa promote-notes`. "
           "Each block is a failure signature; turn the ones that keep recurring into test cases.\n"]
    for s in sorted(sigs):
        info = sigs[s]
        prop = proposals.get(s)
        out.append(f"## Signature {s}\n"
                   f"- attempts {info['n']}\n"
                   f"- criteria: {', '.join(sorted(info['crit'])) or 'none recorded'}\n"
                   f"- observed: {info['obs'] or 'not recorded'}\n"
                   f"- expected: {exp.get(s) or 'not recorded (no qa feedback for this signature)'}\n"
                   f"- proposal: {_one(prop) if prop else 'none'}\n")
    if not sigs:
        out.append("No failure signatures recorded.\n")
    return "\n".join(out)


def promote(root, slice_dir, protect=(), allow_no_protect=False) -> Path:
    d = resolve_dir(root, slice_dir)
    text = build(root, d.name)
    check_text(text, root, protect, allow_no_protect)  # LeakError / NoProtectedPaths before anything is written
    target = d / OUT
    if target.is_symlink():
        raise NotesError(f"{target} is a symlink; refusing to write through it")
    data = text.encode("utf-8")
    if target.is_file() and target.read_bytes() == data:
        return target
    d.mkdir(parents=True, exist_ok=True)
    _walk_no_symlink(Path(os.path.abspath(root)), d, "slice directory component")
    tmp = d / f".{OUT}.tmp{os.getpid()}"
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target
