"""Human-stop ledger: ``<root>/.sf/stops/<name>.json`` plus an append-only, hash-chained ``log.jsonl``.

The log is the authority. An open stop is a ``request`` entry with no later ``release``. Each open
stop must have its file, byte-identical to the hash the log recorded, and no other stop file may
exist; any deviation (edited, deleted, forged, truncated) raises :class:`StopLedgerError` so callers
fail closed. Limit: a hash chain proves internal consistency, not authorship; wiping the whole
``.sf/stops`` directory leaves nothing to compare against.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SCOPE_RE = re.compile(r"^(run|slice:[A-Za-z0-9][A-Za-z0-9._-]{0,127})$")


class StopLedgerError(Exception):
    """The stop ledger failed verification (tampered or malformed)."""


class StopUsageError(ValueError):
    """Bad name/scope, duplicate request or unknown stop."""


class ReleaseRefused(Exception):
    """The releasing actor is not a human."""


def stops_dir(root) -> Path:
    return Path(root) / ".sf" / "stops"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _check_actor(by: str) -> None:
    kind, _, ref = (by or "").partition(":")
    if kind in ("agent", "subagent", "codex"):
        raise ReleaseRefused(f"actor kind {kind!r} may not release a human stop; "
                             "it needs --by human:<ref> from the owner (codex: is not enough here)")
    if kind != "human" or not ref.strip():
        raise ReleaseRefused(f"--by {by!r} refused: a release needs --by human:<ref>")


def _read_log(d: Path) -> list[dict]:
    log = d / "log.jsonl"
    if not log.exists():
        return []
    entries, prev = [], GENESIS
    for n, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        try:
            e = json.loads(line)
        except ValueError:
            raise StopLedgerError(f"log line {n} is not JSON") from None
        if not isinstance(e, dict) or e.get("seq") != n or e.get("prev") != prev \
                or e.get("hash") != _digest(e):
            raise StopLedgerError(f"log line {n} breaks the hash chain")
        prev = e["hash"]
        entries.append(e)
    return entries


def _open_from(entries: list[dict]) -> dict[str, dict]:
    open_: dict[str, dict] = {}
    for e in entries:
        if e.get("event") == "request" and e.get("name") not in open_:
            open_[e["name"]] = e
        elif e.get("event") == "release" and e.get("name") in open_:
            try:
                _check_actor(e.get("by", ""))
            except ReleaseRefused as exc:
                raise StopLedgerError(f"log line {e['seq']}: release by non-human: {exc}") from None
            del open_[e["name"]]
        else:
            raise StopLedgerError(f"log line {e.get('seq')}: unexpected {e.get('event')!r} for {e.get('name')!r}")
    return open_


def _verified_open(root) -> dict[str, dict]:
    d = stops_dir(root)
    open_ = _open_from(_read_log(d))
    on_disk = {p.stem for p in d.glob("*.json")} if d.is_dir() else set()
    if on_disk != set(open_):
        raise StopLedgerError(f"stop files {sorted(on_disk)} do not match the log's open stops {sorted(open_)}")
    for name, e in open_.items():
        if hashlib.sha256((d / f"{name}.json").read_bytes()).hexdigest() != e["file_sha256"]:
            raise StopLedgerError(f"stop file {name}.json changed after it was logged")
    return open_


def applies(stop: dict, scope: str | None) -> bool:
    return scope is None or stop["scope"] == "run" or stop["scope"] == scope


def blocking(root, scope: str | None = None) -> list[dict]:
    """Open stops that apply to ``scope`` (None = all). Raises :class:`StopLedgerError`."""
    return [{k: e[k] for k in ("name", "scope", "reason", "requested_at", "requested_by")}
            for e in _verified_open(root).values()
            if applies({"scope": e["scope"]}, scope)]


def _append(d: Path, entry: dict) -> None:
    entries = _read_log(d)
    entry = {"seq": len(entries) + 1, "prev": entries[-1]["hash"] if entries else GENESIS, **entry}
    entry["hash"] = _digest(entry)
    with (d / "log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


class _Lock:
    def __init__(self, d: Path):
        d.mkdir(parents=True, exist_ok=True)
        self.f = open(d / ".lock", "w")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)

    def __exit__(self, *a):
        self.f.close()


def request(root, name: str, reason: str, scope: str = "run", by: str = "unspecified") -> dict:
    if not NAME_RE.match(name or ""):
        raise StopUsageError(f"bad stop name {name!r}")
    if not SCOPE_RE.match(scope or ""):
        raise StopUsageError(f"bad scope {scope!r}; use run or slice:<id>")
    if not (reason or "").strip():
        raise StopUsageError("a reason is required")
    d = stops_dir(root)
    with _Lock(d):
        open_ = _verified_open(root)
        if name in open_:
            raise StopUsageError(f"stop {name!r} is already open")
        rec = {"name": name, "scope": scope, "reason": reason, "requested_at": _now(), "requested_by": by}
        data = (json.dumps(rec, indent=2, sort_keys=True) + "\n").encode()
        (d / f"{name}.json").write_bytes(data)
        _append(d, {"event": "request", **rec, "file_sha256": hashlib.sha256(data).hexdigest()})
    return rec


def release(root, name: str, by: str) -> None:
    _check_actor(by)
    d = stops_dir(root)
    with _Lock(d):
        if name not in _verified_open(root):
            raise StopUsageError(f"no open stop named {name!r}")
        _append(d, {"event": "release", "name": name, "by": by, "at": _now()})
        (d / f"{name}.json").unlink()


def find_root(start) -> Path | None:
    """Nearest ancestor of ``start`` (inclusive) holding ``.sf/stops``, else None."""
    p = Path(start).resolve()
    for c in (p, *p.parents):
        if stops_dir(c).is_dir():
            return c
    return None
