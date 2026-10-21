"""Human-stop ledger: ``<root>/.factory/stops/<name>.json`` plus an append-only, hash-chained ``log.jsonl``.

The log is the authority. An open stop is a ``request`` entry with no later ``release``. Each open
stop must have its file, byte-identical to the hash the log recorded, and no other stop file may
exist; any deviation (edited, deleted, forged, truncated) raises :class:`StopLedgerError` so callers
fail closed. Limit: a hash chain proves internal consistency, not authorship; wiping the whole
``.factory/stops`` directory leaves nothing to compare against. The store lives under ``.factory/`` so the
control-folder protection (the implement role cannot write ``.factory/**``) covers it. Entries in the
legacy ``<root>/.sf/stops`` are read (verified the same way) and reported, never written.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sys
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
    return Path(root) / ".factory" / "stops"


def legacy_dir(root) -> Path:
    return Path(root) / ".sf" / "stops"


def interactive_terminal() -> bool:
    """True when stdin and stdout are TTYs. Friction, not proof: an agent can allocate a pty."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (ValueError, AttributeError):
        return False


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
    released: set[str] = set()
    for e in entries:
        if e.get("event") == "request" and e.get("name") not in open_:
            open_[e["name"]] = e
        elif e.get("event") == "release" and e.get("name") in open_:
            try:
                _check_actor(e.get("by", ""))
            except ReleaseRefused as exc:
                raise StopLedgerError(f"log line {e['seq']}: release by non-human: {exc}") from None
            del open_[e["name"]]
            released.add(e["name"])
        elif e.get("event") == "supersede" and e.get("name") in open_ and e.get("by_stop") in released:
            try:
                _check_actor(e.get("by", ""))
            except ReleaseRefused as exc:
                raise StopLedgerError(f"log line {e['seq']}: supersede by non-human: {exc}") from None
            del open_[e["name"]]
        else:
            raise StopLedgerError(f"log line {e.get('seq')}: unexpected {e.get('event')!r} for {e.get('name')!r}")
    return open_


def _verified_open(root) -> dict[str, dict]:
    return _verified_dir(stops_dir(root))


def _verified_dir(d: Path) -> dict[str, dict]:
    if os.path.lexists(d) and not d.is_dir():
        raise StopLedgerError(f"{d} exists but is not a directory")
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
    keys = ("name", "scope", "reason", "requested_at", "requested_by")
    try:
        found = [{**{k: e[k] for k in keys}, "legacy": False} for e in _verified_open(root).values()]
        found += [{**{k: e[k] for k in keys}, "legacy": True} for e in _verified_dir(legacy_dir(root)).values()]
    except (OSError, UnicodeDecodeError, KeyError) as e:
        raise StopLedgerError(f"stop ledger unreadable: {type(e).__name__}: {e}") from None
    return [f for f in found if applies(f, scope)]


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
        if name in open_ or name in _verified_dir(legacy_dir(root)):
            raise StopUsageError(f"stop {name!r} is already open")
        rec = {"name": name, "scope": scope, "reason": reason, "requested_at": _now(), "requested_by": by}
        data = (json.dumps(rec, indent=2, sort_keys=True) + "\n").encode()
        (d / f"{name}.json").write_bytes(data)
        _append(d, {"event": "request", **rec, "file_sha256": hashlib.sha256(data).hexdigest()})
    return rec


def release(root, name: str, by: str, tty_probe=None) -> None:
    if not (tty_probe or interactive_terminal)():
        raise ReleaseRefused("a human stop is released by a person at a terminal "
                             "(stdin and stdout must be interactive TTYs; there is no bypass flag)")
    _check_actor(by)
    d = stops_dir(root)
    if name in _verified_dir(legacy_dir(root)):
        raise StopUsageError(f"stop {name!r} is a legacy entry in {legacy_dir(root)}, which is read-only here; "
                             "a person must delete that directory by hand after reviewing it")
    with _Lock(d):
        if name not in _verified_open(root):
            raise StopUsageError(f"no open stop named {name!r}")
        _append(d, {"event": "release", "name": name, "by": by, "at": _now()})
        (d / f"{name}.json").unlink()


def supersede(root, name: str, by_stop: str, by: str, note: str = "", tty_probe=None) -> None:
    """Retire open stop ``name`` because a later stop ``by_stop`` over the same ground was already
    released. Same gate as :func:`release` (human, interactive terminal); appends a chained record."""
    if not (tty_probe or interactive_terminal)():
        raise ReleaseRefused("a human stop is superseded by a person at a terminal "
                             "(stdin and stdout must be interactive TTYs; there is no bypass flag)")
    _check_actor(by)
    d = stops_dir(root)
    with _Lock(d):
        if name not in _verified_open(root):
            raise StopUsageError(f"no open stop named {name!r}")
        if not any(e.get("event") == "release" and e.get("name") == by_stop for e in _read_log(d)):
            raise StopUsageError(f"{by_stop!r} has not been released; supersede needs a released stop")
        _append(d, {"event": "supersede", "name": name, "by_stop": by_stop, "by": by, "note": note, "at": _now()})
        (d / f"{name}.json").unlink()


class RootRefused(Exception):
    """A caller-supplied root is not an ancestor of the path being checked."""


def ledger_roots(start) -> list[Path]:
    """EVERY ancestor of ``start`` (inclusive) that has a stop store, so an empty store planted
    deeper cannot shadow the real one."""
    p = Path(start).resolve()
    return [c for c in (p, *p.parents) if os.path.lexists(stops_dir(c)) or os.path.lexists(legacy_dir(c))]


def check_claimed_root(start, claimed) -> None:
    """A ``--root`` is never trusted: it must be an ancestor of ``start`` and is otherwise ignored."""
    p, c = Path(start).resolve(), Path(claimed).resolve()
    if c != p and c not in p.parents:
        raise RootRefused(f"--root {claimed} is not an ancestor of {start}; the stop root is derived from the path")


def blocking_for(start, scope: str | None = None) -> list[dict]:
    """Open stops from every ledger above ``start`` that apply to ``scope``. Raises
    :class:`StopLedgerError` (fail closed) if any ledger cannot be read or verified."""
    out: list[dict] = []
    for r in ledger_roots(start):
        out += blocking(r, scope)
    return out
