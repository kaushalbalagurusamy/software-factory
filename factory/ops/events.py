"""Stage events: one JSON line per event appended to ``<root>/ops/events.jsonl``.

``emit`` is telemetry. It never raises and never decides anything: a failure prints one line on stderr and
returns False. ``SF_EVENTS=off`` silences it entirely.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOTE_LIMIT = 2000
FIELD_LIMIT = 200  # stage, slice, verdict, source, role
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _clean(value, limit: int) -> str:
    """Redact secret-shaped values, replace surrogates and control characters, then truncate."""
    from factory.hooks.ledger_audit import redact  # the redaction used by factory.hooks

    text = str(value).encode("utf-8", "replace").decode("utf-8", "replace")
    return _CONTROL.sub(" ", redact(text))[:limit]


def _head(root: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = p.stdout.strip()
    return sha if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha) else "unknown"


def _target(root: Path) -> Path:
    """The events file, refusing any symlink that leads outside root."""
    real_root = Path(os.path.realpath(root))
    ops = root / "ops"
    for p in (ops, ops / "events.jsonl"):
        if p.is_symlink():
            r = Path(os.path.realpath(p))
            if r != real_root and real_root not in r.parents:
                raise ValueError(f"{p} is a symlink that resolves outside the repository")
    ops.mkdir(parents=True, exist_ok=True)
    return ops / "events.jsonl"


def emit(root, stage: str, slice_id: str, verdict: str, note: str = "", source: str = "sf",
         role: str | None = None) -> bool:
    """Append one event; True when written. Never raises, never changes a caller's outcome."""
    if os.environ.get("SF_EVENTS", "").strip().lower() == "off":
        return False
    try:
        root = Path(root)
        event = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": _clean(stage, FIELD_LIMIT), "slice": _clean(slice_id, FIELD_LIMIT), "sha": _head(root),
            "verdict": _clean(verdict, FIELD_LIMIT), "note": _clean(note, NOTE_LIMIT), "source": _clean(source, FIELD_LIMIT),
        }
        if role is not None:
            event["role"] = _clean(role, FIELD_LIMIT)
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        path = _target(root)
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)  # the newline repair reads then writes; closing the fd unlocks
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                line = b"\n" + line  # a hand-edited file without a final newline must not merge two events
            if os.write(fd, line) != len(line):
                raise OSError("short write")
        finally:
            os.close(fd)
        return True
    except Exception as e:  # noqa: BLE001 - telemetry must not change a command's outcome
        reason = " ".join(f"{type(e).__name__}: {e}".split())[:200]
        print(f"event not recorded: {reason}", file=sys.stderr)
        return False
