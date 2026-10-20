"""Stage events: one JSON line per event appended to ``<root>/ops/events.jsonl``.

``emit`` is telemetry. It never raises and never decides anything: a failure prints one line on stderr and
returns False. ``SF_EVENTS=off`` silences it entirely.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOTE_LIMIT = 2000
FIELD_LIMIT = 200  # stage, slice, verdict, source, role
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*)", re.S)


_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_USERINFO = re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@")


def _redact(text: str) -> str:
    from factory.hooks.ledger_audit import REDACTED, redact as base  # the redaction used by factory.hooks

    def redact(t: str) -> str:  # plus bearer tokens and scheme://user:password@host userinfo
        return _USERINFO.sub(REDACTED + "@", _BEARER.sub(lambda m: m.group(1) + REDACTED, base(t)))

    text = _PEM.sub(REDACTED, text)  # an unterminated block hides everything after its header
    spaced = redact(_CONTROL.sub(" ", text))
    joined = _CONTROL.sub("", text)  # a secret split by a newline, tab or NUL only matches once rejoined
    red = redact(joined)
    return red if red != joined else spaced


def _clean(value, limit: int) -> str:
    """Replace surrogates, redact secret-shaped values (also across control characters), then truncate."""
    return _redact(str(value).encode("utf-8", "replace").decode("utf-8", "replace"))[:limit]


def _head(root: Path) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = p.stdout.strip()
    return sha if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha) else "unknown"


def _target(root: Path) -> Path:
    """The events file; a symlink at ops/ or ops/events.jsonl is refused whatever its target."""
    if not root.is_dir():
        raise FileNotFoundError(f"repository root does not exist: {root}")
    ops = root / "ops"
    for p in (ops, ops / "events.jsonl"):
        if p.is_symlink():
            raise ValueError(f"{p} is a symlink")
    ops.mkdir(exist_ok=True)
    return ops / "events.jsonl"


def emit(root, stage: str, slice_id: str, verdict: str, note: str = "", source: str | None = "sf",
         role: str | None = None) -> bool:
    """Append one event; True when written. Never raises, never changes a caller's outcome."""
    if os.environ.get("SF_EVENTS", "").strip().lower() == "off":
        return False
    try:
        root = Path(root)
        event = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": _clean(stage, FIELD_LIMIT), "slice": _clean(slice_id, FIELD_LIMIT), "sha": _head(root),
            "verdict": _clean(verdict, FIELD_LIMIT), "note": _clean(note, NOTE_LIMIT)
        }
        if source is not None:  # None only for the legacy script, whose events never had a source key
            event["source"] = _clean(source, FIELD_LIMIT)
        if role is not None:
            event["role"] = _clean(role, FIELD_LIMIT)
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        path = _target(root)
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError(f"{path} is not a regular file")
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
