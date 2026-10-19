"""Leak check: feedback to the blind implementer must not carry protected test material.

Rejects text containing (after whitespace normalisation) a verbatim line of at least
MIN_LINE characters, any WINDOW-character window, or the path of any file under the protected
paths. Findings never include the protected text itself.
"""
import re
from dataclasses import dataclass
from pathlib import Path

WINDOW = 40
MIN_LINE = 16
MAX_BYTES = 5_000_000
_GLOB = re.compile(r"[*?\[]")


class LeakError(Exception):
    pass


@dataclass(frozen=True)
class Leak:
    path: str
    line: int
    kind: str  # line | window | path


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def expand(protected, root=None) -> list:
    """Files under the given paths (files, directories, or globs relative to root)."""
    files = []
    for p in protected:
        s = str(p)
        if _GLOB.search(s):
            base = Path(root or ".")
            hits = base.glob(s)
        else:
            q = Path(s)
            if not q.is_absolute() and root is not None:
                q = Path(root) / q
            hits = [q]
        for h in hits:
            if h.is_dir():
                files.extend(x for x in sorted(h.rglob("*")) if x.is_file())
            elif h.is_file():
                files.append(h)
    seen, out = set(), []
    for f in files:
        k = f.resolve()
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _read(f: Path):
    try:
        if f.stat().st_size > MAX_BYTES:
            return None
        return f.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def leak_check(text: str, protected_paths, root=None) -> list:
    flat = _norm(text)
    text_lines = {_norm(l) for l in text.splitlines()}
    hashes = {hash(flat[i:i + WINDOW]) for i in range(max(0, len(flat) - WINDOW + 1))}
    found = []
    base = Path(root).resolve() if root is not None else None
    for f in expand(protected_paths, root):
        body = _read(f)
        if body is None:
            continue
        shown = str(f)
        parts = f.resolve().parts
        rels = {shown} | {"/".join(parts[-k:]) for k in (2, 3) if len(parts) >= k}
        if base is not None:
            try:
                rels.add(str(f.resolve().relative_to(base)))
            except ValueError:
                pass
        if any(r in text for r in rels):
            found.append(Leak(shown, 0, "path"))
        hit = None
        for n, line in enumerate(body.splitlines(), 1):
            nl = _norm(line)
            if len(nl) >= MIN_LINE and nl in text_lines:
                hit = Leak(shown, n, "line")
                break
        if hit:
            found.append(hit)
            continue
        for n, line in enumerate(body.splitlines(), 1):
            nl = _norm(line)
            if len(nl) >= WINDOW and any(hash(nl[i:i + WINDOW]) in hashes
                                         for i in range(len(nl) - WINDOW + 1)):
                found.append(Leak(shown, n, "window"))
                break
        else:
            # windows that span lines in the protected file
            fb = _norm(body)
            if len(fb) >= WINDOW and any(hash(fb[i:i + WINDOW]) in hashes
                                         for i in range(len(fb) - WINDOW + 1)):
                found.append(Leak(shown, 0, "window"))
    return found


def assert_no_leak(text: str, protected_paths, root=None) -> None:
    found = leak_check(text, protected_paths, root)
    if found:
        where = "; ".join(f"{l.path}" + (f":{l.line}" if l.line else "") + f" ({l.kind})" for l in found)
        raise LeakError(f"feedback matches protected material, refusing to write: {where}")
