#!/usr/bin/env python3
"""lsf: the lite software factory. One standard-library file, Python 3.9 or newer, plus git.

State lives in .lsf/ inside the project: profile.json, phases.jsonl (the phase clock), events.jsonl (telemetry),
stops.jsonl (human checkpoints, hash chained). Exit codes: 0 ok, 1 check failed, 2 usage, 3 refused by a human stop.
No command makes a network request. `lsf serve` binds 127.0.0.1 only.
"""
import argparse
import ast
import contextlib
import datetime
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import difflib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1"
MAX_READ = 5 * 1024 * 1024
MAX_FILES = 20000
MAX_FILE_API = 1024 * 1024
MAX_NOTE = 2000
SKIP_DIRS = (".git", "node_modules", ".venv")
EDITORS = ["vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate", "none"]
GROUPS = ("align", "review", "build")
PHASES = [
    ("0-intake", "align"), ("1-sweep", "align"), ("2-research", "align"), ("3-experiments", "align"),
    ("4-prd", "align"), ("5-evals", "align"), ("6-decide", "align"),
    ("7-implement", "build"), ("8-qa", "build"),
    ("9-review", "review"), ("10-docs", "review"),
]
# lsf phase id -> the matching /sf stage (docs/sf-flow.md), so events from both tools read the same
SF_ALIAS = {
    "0-intake": "0", "1-sweep": "0", "2-research": "1", "3-experiments": "2", "4-prd": "4", "5-evals": "5",
    "6-decide": "3", "7-implement": "6", "8-qa": "7", "9-review": "8b", "10-docs": "10",
}
DEFAULT_WEIGHTS = {"align": 0.6, "review": 0.2, "build": 0.2}
GENESIS = "0" * 64


def _jd(o):
    if isinstance(o, (set, frozenset, tuple)):
        return sorted(o) if not isinstance(o, tuple) else list(o)
    raise TypeError("not JSON serializable: %s" % type(o).__name__)


class Usage(Exception):
    pass


class Fail(Exception):
    pass


class StopError(Exception):
    pass


# ---------------------------------------------------------------- time and files
def now():
    v = os.environ.get("LSF_NOW")
    if v:
        t = parse_ts(v)
        if t is None:
            raise Usage("LSF_NOW must be an ISO UTC time such as 2026-10-20T10:00:00Z")
        return t
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def parse_ts(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S+00:00"):
        try:
            return datetime.datetime.strptime(s, fmt).replace(microsecond=0)
        except ValueError:
            pass
    return None


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_between(a, b):
    return max(0.0, (b - a).total_seconds() / 60.0)


def lsf_dir(root):
    return os.path.join(root, ".lsf")


def lpath(root, name):
    return os.path.join(lsf_dir(root), name)


def append_line(path, obj):
    """One O_APPEND write per record, so concurrent writers never interleave inside a line."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (json.dumps(obj, separators=(",", ":"), default=_jd) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def read_capped(path, tail=False):
    """Bytes of a file, never more than MAX_READ (the tail when tail=True). None when it does not exist."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > MAX_READ:
                if tail:
                    f.seek(size - MAX_READ)
                    f.readline()
                    return f.read()
                return f.read(MAX_READ)
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Fail("cannot read %s: %s" % (path, e))


def read_jsonl(path, tail=False):
    raw = read_capped(path, tail)
    rows = []
    if raw is None:
        return rows
    for ln in raw.decode("utf-8", "replace").splitlines():
        if ln.strip():
            try:
                v = json.loads(ln)
            except ValueError:
                continue
            if isinstance(v, dict):
                rows.append(v)
    return rows


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _lock_is_stale(d):
    """A lock is stale when its owner process is gone, or when it is older than 5 seconds."""
    try:
        pid = int(open(os.path.join(d, "pid")).read().strip())
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, ValueError):
        pass
    try:
        return time.time() - os.path.getmtime(d) > 5
    except OSError:
        return False


@contextlib.contextmanager
def locked(root):
    """A portable directory lock around ledger writes (no OS-specific locking calls)."""
    d = lpath(root, ".lock")
    os.makedirs(lsf_dir(root), exist_ok=True)
    end = time.time() + 6
    while True:
        try:
            os.mkdir(d)
            with contextlib.suppress(OSError):
                with open(os.path.join(d, "pid"), "w") as f:
                    f.write(str(os.getpid()))
            break
        except FileExistsError:
            if _lock_is_stale(d):
                shutil.rmtree(d, ignore_errors=True)
                continue
            if time.time() > end:
                raise Fail("another lsf process holds %s" % d)
            time.sleep(0.05)
    try:
        yield
    finally:
        shutil.rmtree(d, ignore_errors=True)


def git(root, *args, **kw):
    try:
        p = subprocess.run(["git", "-C", root] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=kw.get("timeout", 30))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def head_sha(root):
    out = git(root, "rev-parse", "HEAD", timeout=5)
    s = out.decode().strip() if out else ""
    return s if re.match(r"^[0-9a-f]{40,64}$", s) else "unknown"


def find_root(arg):
    if arg:
        if not os.path.isdir(arg):
            raise Usage("--root %s is not a directory" % arg)
        return os.path.realpath(arg)
    out = git(os.getcwd(), "rev-parse", "--show-toplevel", timeout=5)
    return os.path.realpath(out.decode().strip()) if out else os.path.realpath(os.getcwd())


# ---------------------------------------------------------------- redaction
_SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?:npm|hf)_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<=://)[^/\s:@]+:[^@\s/]+(?=@)"),
    re.compile(r"(?i)(?<=\s-u\s)\S+:\S+"),
    re.compile(r"(?i)(?<=--token )\S+|(?<=--password )\S+|(?<=--passwd )\S+|(?<=--secret )\S+|(?<=--api-key )\S+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"glpat-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]*"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{12,}"),
]
_KV = re.compile(r"(?i)\b([A-Za-z0-9_\-]*(?:api[_-]?key|secret|token|passw(?:or)?d|authorization|credential)[A-Za-z0-9_\-]*)"
                 r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)")


def redact(text):
    for rx in _SECRETS:
        text = rx.sub("[REDACTED]", text)
    return _KV.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)


def clean_note(text, limit=MAX_NOTE):
    text = "" if text is None else str(text)
    text = "".join(" " if (ord(c) < 32 or 127 <= ord(c) < 160) else c for c in text)
    return redact(text)[:limit]


# ---------------------------------------------------------------- profile
def default_profile(root, minutes=60, checkpoints="align", editor="vscode", weights=None):
    cp = {}
    for pid, grp in PHASES:
        cp[pid] = checkpoints == "all" or (checkpoints == "align" and grp == "align")
    return {
        "version": VERSION, "session_minutes": minutes,
        "phases": [{"id": p, "group": g} for p, g in PHASES],
        "weights": dict(weights or DEFAULT_WEIGHTS), "checkpoints": cp,
        "editor": editor, "workspace_root": root,
    }


def load_profile(root):
    p = lpath(root, "profile.json")
    raw = read_capped(p)
    if raw is None:
        return default_profile(root)
    try:
        prof = json.loads(raw.decode("utf-8"))
        if not isinstance(prof, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise Fail("%s is not valid JSON: %s" % (p, e))
    base = default_profile(root)
    for k, v in base.items():
        prof.setdefault(k, v)
    return prof


def check_weights(prof):
    w = prof.get("weights")
    if not isinstance(w, dict):
        raise Usage("profile weights must be an object with align, review and build")
    tot = 0.0
    for g in GROUPS:
        v = w.get(g)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise Usage("weight %s must be a non-negative number" % g)
        tot += v
    if abs(tot - 1.0) > 0.001:
        raise Usage("weights must sum to 1.0 within 0.001 (got %.4f)" % tot)
    return w


def phase_ids(prof):
    return [p["id"] for p in prof["phases"]]


def group_of(prof, pid):
    for p in prof["phases"]:
        if p["id"] == pid:
            return p["group"]
    return None


# ---------------------------------------------------------------- events
def emit_event(root, stage, verdict, note="", source="lsf", phase=None, slice_=None, role=None,
               duration_s=None, extra=None, force=False):
    if not force and (os.environ.get("SF_EVENTS") == "off" or os.environ.get("LSF_EVENTS") == "off"):
        return False
    try:
        one = lambda v: None if v is None else clean_note(v, 200)
        ev = {"at": iso(now()), "stage": one(stage), "slice": one(slice_), "phase": one(phase), "verdict": one(verdict),
              "note": clean_note(note), "source": source, "sha": head_sha(root)}
        if role:
            ev["role"] = clean_note(role, 80)
        if extra and extra.get("model"):
            extra = dict(extra, model=clean_note(extra["model"], 120))
        if duration_s is not None:
            ev["duration_s"] = duration_s
        if extra:
            ev.update(extra)
        append_line(lpath(root, "events.jsonl"), ev)
        return True
    except (OSError, ValueError) as e:
        sys.stderr.write("event not recorded: %s\n" % e)
        return False


# ---------------------------------------------------------------- phase clock
def phase_rows(root):
    return read_jsonl(lpath(root, "phases.jsonl"))


def intervals(rows, at):
    """[{phase, start, end (None when open), verdict}] from the append-only phase rows."""
    out, cur = [], None
    for r in rows:
        t = parse_ts(r.get("at"))
        if t is None:
            continue
        if r.get("type") == "start":
            if cur is not None:
                cur["end"], cur["verdict"] = t, "switched"
            cur = {"phase": r.get("phase"), "start": t, "end": None, "verdict": None}
            out.append(cur)
        elif r.get("type") == "end" and cur is not None and cur["phase"] == r.get("phase"):
            cur["end"], cur["verdict"] = t, r.get("verdict")
            cur = None
    return out


def open_phase(rows):
    for iv in reversed(intervals(rows, None)):
        return iv if iv["end"] is None else None
    return None


# ---------------------------------------------------------------- stop ledger
def _chain(prev, text):
    return hashlib.sha256((prev + text).encode("utf-8")).hexdigest()


def _entry_text(e):
    return json.dumps({k: v for k, v in e.items() if k not in ("chain", "hash")}, sort_keys=True, separators=(",", ":"), default=_jd)


def _parse_ledger(raw):
    """(valid entries, error) where valid is the longest verified prefix of the ledger text."""
    prev, entries = GENESIS, []
    try:
        lines = raw.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return entries, True
    if lines and lines[-1] == "":
        lines.pop()
    for i, ln in enumerate(lines, 1):
        try:
            e = json.loads(ln)
        except ValueError:
            return entries, True
        if not isinstance(e, dict) or e.get("seq") != i or not isinstance(e.get("chain"), str) \
                or e.get("prev") != prev or e.get("hash") != e.get("chain") \
                or not hmac.compare_digest(_chain(prev, _entry_text(e)), e["chain"]):
            return entries, True
        prev = e["chain"]
        entries.append(e)
    return entries, False


def _write_head(root, entries):
    atomic_write(lpath(root, "stops.head"), json.dumps({"seq": len(entries), "chain": entries[-1]["chain"]}, default=_jd) + "\n")


def stops_raw(root):
    """Verified ledger entries. Raises Fail('stop ledger failed verification') on any tamper."""
    bad = Fail("stop ledger failed verification")
    p, head = lpath(root, "stops.jsonl"), lpath(root, "stops.head")
    raw = read_capped(p)
    hraw = read_capped(head)
    if raw is None:
        if hraw is not None:
            raise bad
        return []
    entries, broken = _parse_ledger(raw)
    if broken or not entries:
        raise bad
    try:
        h = json.loads(hraw.decode("utf-8")) if hraw is not None else None
    except ValueError:
        raise bad
    if isinstance(h, dict) and h.get("seq") == len(entries) - 1 and len(entries) >= 1 \
            and h.get("chain") == (entries[-2]["chain"] if len(entries) > 1 else GENESIS):
        # crash window between the ledger append and the head write: exactly one valid extra entry, heal the head
        try:
            _write_head(root, entries)
        except OSError:
            pass
        return entries
    if not isinstance(h, dict) or h.get("seq") != len(entries) or h.get("chain") != entries[-1]["chain"]:
        raise bad
    return entries


def cross_check(root, entries):
    """Every stop opened or released must also appear in the append-only event log, and the reverse for opens."""
    ev = [e for e in read_jsonl(lpath(root, "events.jsonl"), tail=True) if e.get("stage") == "hitl"]
    base_seq = 0
    for i in range(len(ev) - 1, -1, -1):
        if ev[i].get("verdict") == "repaired":
            base_seq = int(ev[i].get("ledger_seq") or 0)
            ev = ev[i + 1:]
            break
    led = {}
    for e in entries:
        if e.get("seq", 0) > base_seq:
            k = (e.get("kind"), e.get("name"))
            led[k] = led.get(k, 0) + 1
    evc = {}
    for e in ev:
        kind = {"opened": "open", "released": "release", "recorded": "recorded", "applied": "applied"}.get(e.get("verdict"))
        if kind:
            k = (kind, e.get("stop"))
            evc[k] = evc.get(k, 0) + 1
    for k, n in evc.items():
        if k[0] == "open" and led.get(k, 0) < n:
            raise Fail("stop ledger inconsistent: stop %s was opened (events.jsonl) but is missing from the ledger" % k[1])
    for k, n in led.items():
        if k[0] in ("release", "recorded", "applied") and evc.get(k, 0) < n:
            raise Fail("stop ledger inconsistent: stop %s is %s in the ledger with no %s event"
                       % (k[1], {"release": "released"}.get(k[0], k[0]), k[0]))


def derive_stops(entries):
    stops = []
    for e in entries:
        if e.get("kind") == "open":
            stops.append({"id": e.get("name"), "name": e.get("name"), "question": e.get("question"), "artifact": e.get("artifact") or [],
                          "reason": e.get("reason"), "opened_at": e.get("opened_at"), "state": "asked",
                          "options": e.get("options") or [], "proposal_hash": e.get("proposal_hash"), "unbound": e.get("unbound") or [], "answer": None,
                          "answered_at": None, "recorded_where": None, "recorded_at": None,
                          "applied_evidence": None, "applied_at": None})
        elif e.get("kind") in ("release", "recorded", "applied"):
            # a release closes the latest asked stop of that name; recorded/applied advance the latest stop of that name
            want = {"release": "asked", "recorded": "answered", "applied": "recorded"}[e["kind"]]
            for s in reversed(stops):
                if s["name"] != e.get("name"):
                    continue
                if s["state"] == want:
                    if e["kind"] == "release":
                        s["released_at"], s["released_by"], s["note"] = e.get("released_at"), e.get("released_by"), e.get("note")
                        s["via"] = e.get("via") or "unknown"
                        s["answer"], s["answered_at"], s["state"] = e.get("answer"), e.get("released_at"), "answered"
                    elif e["kind"] == "recorded":
                        s["recorded_where"], s["recorded_at"], s["state"] = e.get("where"), e.get("recorded_at"), "recorded"
                    else:
                        s["applied_evidence"], s["applied_at"], s["state"] = e.get("evidence"), e.get("applied_at"), "applied"
                break
    return stops


def stops_append(root, entry):
    """Caller holds the lock. Appends one chained entry and moves the head pointer."""
    entries = stops_raw(root)
    prev = entries[-1]["chain"] if entries else GENESIS
    entry = dict(entry)
    entry["seq"] = len(entries) + 1
    entry["prev"] = prev
    entry["chain"] = entry["hash"] = _chain(prev, _entry_text(entry))
    append_line(lpath(root, "stops.jsonl"), entry)
    atomic_write(lpath(root, "stops.head"), json.dumps({"seq": entry["seq"], "chain": entry["chain"]}, default=_jd) + "\n")


def stops_state(root):
    entries = stops_raw(root)
    cross_check(root, entries)
    return derive_stops(entries)


def open_stops(root):
    return [s for s in stops_state(root) if "released_at" not in s]


def strict_hitl(root):
    return bool(load_profile(root).get("require_tty_release"))


def require_tty_if_strict(root, what):
    if strict_hitl(root) and not sys.stdin.isatty():
        out("refused: %s needs an interactive terminal (require_tty_release is on); a human must run it" % what)
        raise StopError()


MAX_OPTIONS = 6
MAX_OPTION = 120
MAX_PROPOSAL_FILE = 1024 * 1024


def _artifact_sha(root, path):
    """sha256 of the file bytes, or None when missing, not a regular file, outside the repo root, or over 1 MiB."""
    path = re.sub(r":\d+$", "", path)  # a trailing :LINE names a position in the file
    try:
        real = os.path.realpath(os.path.join(root, path))
        base = os.path.realpath(root)
        if real != base and not real.startswith(base + os.sep):
            return None
        if not os.path.isfile(real) or os.path.getsize(real) > MAX_PROPOSAL_FILE:
            return None
        with open(real, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, ValueError):
        return None


def proposal_hash(root, question, options, artifacts):
    doc = {"question": question, "options": list(options),
           "artifacts": [{"path": a, "sha256": _artifact_sha(root, a) or "unbound"} for a in artifacts]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def latest_stop(root, name):
    mine = [s for s in stops_state(root) if s["name"] == name]
    if not mine:
        raise Fail("unknown stop %s" % name)
    return mine[-1]


def hitl_open(root, name, question, artifacts, reason, options=None, bind=True):
    check_name(name)
    opts = [clean_note(o, MAX_OPTION + 1).strip() for o in (options or [])]
    if len(opts) > MAX_OPTIONS or any(not o or len(o) > MAX_OPTION for o in opts):
        raise Usage("--option may repeat at most %d times, each 1-%d characters" % (MAX_OPTIONS, MAX_OPTION))
    with locked(root):
        if any(s["name"] == name for s in open_stops(root)):
            raise Fail("stop %s is already open" % name)
        q, arts = clean_note(question, 500), [clean_note(a, 300) for a in artifacts]
        unbound = [a for a in arts if _artifact_sha(root, a) is None]
        if unbound and bind:
            raise Usage("cannot hash artifact(s) (missing, not a regular file, outside the repo, or over 1 MiB): " + ", ".join(unbound))
        stops_append(root, {"kind": "open", "name": name, "question": q, "artifact": arts, "reason": clean_note(reason, 500),
                            "opened_at": iso(now()), "options": opts, "proposal_hash": proposal_hash(root, q, opts, arts),
                            "unbound": unbound})
        emit_event(root, "hitl", "opened", "%s: %s" % (name, question), phase=name, extra={"stop": name}, force=True)


def hitl_release(root, name, note="", by=None, via="cli-nontty", answer=None, proposal_hash=None):
    check_name(name)
    by = by or os.environ.get("LSF_BY") or os.environ.get("USER") or "human"
    with locked(root):
        stops = stops_state(root)
        mine = [s for s in stops if s["name"] == name]
        if not mine:
            raise Fail("unknown stop %s" % name)
        st = mine[-1]
        if "released_at" in st:
            raise Fail("stop %s is already released" % name)
        if st.get("options"):
            if answer not in st["options"]:
                raise Usage("stop %s needs an answer, exactly one of: %s" % (name, " | ".join(st["options"])))
        elif answer:
            raise Usage("stop %s has no options; release it without an answer" % name)
        stored = st.get("proposal_hash")
        if proposal_hash is not None and proposal_hash != stored:
            raise Fail("stale proposal hash for stop %s; reload and answer the current proposal" % name)
        if stored and _stop_hash(root, st) != stored:
            raise Fail("proposal changed since it was asked; ask again")
        t = iso(now())
        opened = parse_ts(st["opened_at"])
        wait = int(minutes_between(opened, parse_ts(t)) * 60) if opened else None
        # the release event goes first so a ledger release can never exist without it
        if not emit_event(root, "hitl", "released", "%s released by %s via %s%s%s" % (name, by, via, (" with answer: " + answer) if answer else "", (": " + note) if note else ""),
                          phase=name, duration_s=wait, extra={"stop": name, "via": via}, force=True):
            raise Fail("release event could not be recorded; nothing released")
        entry = {"kind": "release", "name": name, "released_at": t, "released_by": clean_note(by, 120),
                 "note": clean_note(note, 500), "via": via}
        if stored:
            entry["answer"], entry["proposal_hash"] = answer, stored
        stops_append(root, entry)
    return t


def _stop_hash(root, st):
    return proposal_hash(root, st.get("question"), st.get("options") or [], st.get("artifact") or [])


def _advance(root, name, verdict, kind, want, extra_entry, note):
    """Shared by recorded/applied: the stop's latest state must be `want`; the event goes first, then the chained entry."""
    with locked(root):
        st = latest_stop(root, name)
        if st["state"] != want:
            raise Fail("stop %s is %s; %s is only valid after %s" % (name, st["state"], kind, want))
        if not emit_event(root, "hitl", verdict, "%s %s: %s" % (name, verdict, note), phase=name, extra={"stop": name}, force=True):
            raise Fail("%s event could not be recorded; nothing changed" % verdict)
        e = dict(extra_entry, kind=kind, name=name)
        stops_append(root, e)


def hitl_recorded(root, name, where, note=""):
    check_name(name)
    real = os.path.realpath(os.path.join(root, where or ""))
    base = os.path.realpath(root)
    if not where or (real != base and not real.startswith(base + os.sep)) or not os.path.exists(real) \
            or not (os.path.isfile(real) or os.path.isdir(real)):
        raise Fail("--where must be an existing file or directory inside the repository")
    rel = os.path.relpath(real, base)
    t = iso(now())
    _advance(root, name, "recorded", "recorded", "answered",
             {"where": clean_note(rel, 300), "recorded_at": t, "record_note": clean_note(note, 500)}, rel)
    return t


def hitl_applied(root, name, evidence):
    check_name(name)
    ev = clean_note(evidence, 500).strip()
    if not ev:
        raise Fail("--evidence is required and must not be blank")
    t = iso(now())
    _advance(root, name, "applied", "applied", "recorded", {"evidence": ev, "applied_at": t}, ev)
    return t


def hitl_repair(root):
    """Quarantine a bad ledger and rebuild it from its longest verified prefix. A human act."""
    p = lpath(root, "stops.jsonl")
    with locked(root):
        raw = read_capped(p)
        if raw is None:
            raise Fail("no stop ledger to repair")
        entries, _ = _parse_ledger(raw)
        stamp = now().strftime("%Y%m%d%H%M%S")
        moved = p + ".corrupt-" + stamp
        os.replace(p, moved)
        with contextlib.suppress(OSError):
            os.replace(lpath(root, "stops.head"), lpath(root, "stops.head.corrupt-" + stamp))
        if entries:
            data = "".join(json.dumps(e, separators=(",", ":"), default=_jd) + "\n" for e in entries)
            atomic_write(p, data)
            _write_head(root, entries)
        emit_event(root, "hitl", "repaired", "ledger quarantined as %s; kept %d valid entries" % (os.path.basename(moved), len(entries)),
                   extra={"ledger_seq": len(entries)}, force=True)
    return moved, len(entries)


def check_name(name):
    if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,79}$", name):
        raise Usage("stop name must be 1-80 characters of letters, digits and . _ : -")


def wait_intervals(stops, at):
    out = []
    for s in stops:
        a = parse_ts(s.get("opened_at"))
        if a is None:
            continue
        b = parse_ts(s.get("released_at")) if "released_at" in s else at
        out.append((a, b or at))
    return out


def merged(ivs):
    ivs = sorted(ivs)
    out = []
    for a, b in ivs:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# ---------------------------------------------------------------- budget
def budget_data(root, at=None):
    prof = load_profile(root)
    w = check_weights(prof)
    at = at or now()
    ivs = intervals(phase_rows(root), at)
    ledger_error = None
    try:
        stops = stops_state(root)
    except Fail as e:
        stops, ledger_error = [], str(e)
    wait = merged(wait_intervals(stops, at))
    groups = {g: {"planned_minutes": round(prof["session_minutes"] * w[g], 2), "actual_minutes": None,
                  "percent_of_plan": None, "flag": "under (not measured)", "waiting_minutes": 0.0} for g in GROUPS}
    for iv in ivs:
        g = group_of(prof, iv["phase"])
        if g is None:
            continue
        a, b = iv["start"], iv["end"] or at
        mins = minutes_between(a, b)
        for wa, wb in wait:
            lo, hi = max(a, wa), min(b, wb)
            if hi > lo:
                mins -= minutes_between(lo, hi)
        groups[g]["actual_minutes"] = (groups[g]["actual_minutes"] or 0.0) + max(0.0, mins)
    for g, d in groups.items():
        if d["actual_minutes"] is not None:
            d["actual_minutes"] = round(d["actual_minutes"], 2)
            if d["planned_minutes"] > 0:
                d["percent_of_plan"] = round(100.0 * d["actual_minutes"] / d["planned_minutes"], 1)
            d["flag"] = "over plan" if d["actual_minutes"] > d["planned_minutes"] else "under plan"
    total = sum(minutes_between(a, b) for a, b in wait)
    for st in stops:
        a0 = parse_ts(st.get("opened_at"))
        if a0 is None:
            continue
        b0 = parse_ts(st.get("released_at")) if "released_at" in st else at
        g = group_of(prof, str(st.get("name", "")).replace("-review", ""))
        if g is None:
            for iv in ivs:
                if iv["start"] <= a0 and (iv["end"] is None or a0 <= iv["end"]):
                    g = group_of(prof, iv["phase"])
        if g:
            groups[g]["waiting_minutes"] = round(groups[g]["waiting_minutes"] + minutes_between(a0, b0 or at), 2)
    measured = sum(d["actual_minutes"] or 0.0 for d in groups.values())
    out_ = {"groups": groups, "waiting_on_human_minutes": None if ledger_error else round(total, 2),
            "session_minutes": prof["session_minutes"], "session_total_minutes": round(measured + (0 if ledger_error else total), 2),
            "clock_overridden": bool(os.environ.get("LSF_NOW"))}
    if ledger_error:
        out_["ledger_error"] = ledger_error
    return out_


# ---------------------------------------------------------------- collectors (item shapes follow factory.ops.collect)
def _base_dir(pattern):
    segs = pattern.split("/")
    keep = []
    for seg in segs[:-1]:
        if any(c in seg for c in "*?["):
            break
        keep.append(seg)
    return "/".join(keep)


class Source(object):
    """Files as of a commit, read straight from the git object database, one directory at a time."""

    def __init__(self, root, sha):
        self.root, self.sha = root, sha
        self.where = "commit " + sha[:12]
        self.truncated = 0
        self._dirs = {}

    def _raw_list(self, d):
        out_ = git(self.root, "ls-tree", "-r", "--name-only", "-z", self.sha, "--", d + "/")
        if out_ is None:
            raise Fail("git ls-tree failed for %s at %s" % (d, self.sha[:12]))
        return [p for p in out_.decode("utf-8", "replace").split("\0") if p]

    def ls(self, d):
        if d not in self._dirs:
            ps = [p for p in self._raw_list(d) if not any(c in SKIP_DIRS for c in p.split("/"))]
            if len(ps) > MAX_FILES:
                self.truncated = MAX_FILES
                ps = ps[:MAX_FILES]
            self._dirs[d] = ps
        return self._dirs[d]

    def glob(self, pattern):
        depth = pattern.count("/")
        return sorted(p for p in self.ls(_base_dir(pattern)) if p.count("/") == depth and fnmatch.fnmatchcase(p, pattern))

    def has(self, path):
        return path in self.ls(os.path.dirname(path))

    def has_dir(self, d):
        return any(p.startswith(d.rstrip("/") + "/") for p in self.ls(os.path.dirname(d.rstrip("/"))))

    def read(self, path):
        out_ = git(self.root, "show", "%s:%s" % (self.sha, path))
        return None if out_ is None else out_[:MAX_READ]

    def text(self, path):
        b = self.read(path)
        return None if b is None else b.decode("utf-8", "replace")

    def commits(self, limit=200):
        out_ = git(self.root, "log", "-n%d" % limit, "--format=%H%x1f%cI%x1f%s", self.sha) or b""
        rows = []
        for line in out_.decode("utf-8", "replace").splitlines():
            h, d, s_ = (line.split("\x1f") + ["", ""])[:3]
            rows.append({"sha": h, "date": d, "subject": s_})
        return rows


class WorkTree(Source):
    """Files as they are on disk."""

    def __init__(self, root):
        Source.__init__(self, root, "HEAD")
        self.where = "the working tree"

    def _raw_list(self, d):
        out_ = git(self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", d)
        if out_ is not None:
            cand = [p for p in out_.decode("utf-8", "replace").split("\0") if p]
        else:
            cand = []
            for dp, dn, fn in os.walk(os.path.join(self.root, d)):
                dn[:] = [x for x in dn if x not in SKIP_DIRS]
                for f in fn:
                    cand.append(os.path.relpath(os.path.join(dp, f), self.root).replace(os.sep, "/"))
                if len(cand) > MAX_FILES:
                    break
        return sorted({p for p in cand if os.path.isfile(os.path.join(self.root, p))})

    def read(self, path):
        f = os.path.join(self.root, path)
        if os.path.islink(f) or not os.path.isfile(f):
            return None
        try:
            if os.path.commonpath([os.path.realpath(f), self.root]) != self.root:
                return None
        except ValueError:
            return None
        return read_capped(f)


def unavailable(reason):
    return {"available": False, "reason": reason}


def ok(items, **summary):
    s = {"count": len(items)}
    s.update(summary)
    return {"available": True, "summary": s, "items": items}


def _json(src, path):
    t = src.text(path)
    if t is None:
        return None, "%s missing" % path
    try:
        return json.loads(t), None
    except ValueError as e:
        return None, "%s is not valid JSON: %s" % (path, e)


def _title(text, fallback):
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    return m.group(1) if m else fallback


def stem(p):
    return os.path.splitext(os.path.basename(p))[0]


def c_architecture(src):
    paths = sorted(set(src.glob("docs/explorer/*.model.json")) | set(src.glob("docs/architecture/*.model.json")))
    if not paths:
        return unavailable("no docs/explorer/*.model.json or docs/architecture/*.model.json in %s" % src.where)
    items = []
    for p in paths:
        model, err = _json(src, p)
        if err:
            items.append({"path": p, "error": err})
            continue
        nodes = model.get("nodes", {}) if isinstance(model, dict) else {}
        items.append({"path": p, "title": (model.get("meta") or {}).get("title") or p, "nodes": len(nodes),
                      "diagrams": sum(1 for n in nodes.values() if n.get("diagram")), "model": model})
    return ok(items)


def c_research(src):
    paths = src.glob("research/*.md")
    if not paths:
        return unavailable("no research/*.md in %s" % src.where)
    items = []
    for p in paths:
        t = src.text(p) or ""
        m = re.search(r"as of:?\**:?\s*([^\n.]*)", t, re.I)
        items.append({"path": p, "title": _title(t, stem(p)), "as_of": m.group(1).strip() if m else None})
    return ok(items)


def c_experiments(src):
    res, rsv = src.glob("experiments/*/results.json"), src.glob("experiments/*/resolved.json")
    if not res and not rsv:
        return unavailable("no experiments/*/results.json and no experiments/*/resolved.json in %s" % src.where)
    items = []
    for p in res:
        data, err = _json(src, p)
        row = {"path": p, "name": p.split("/")[1], "kind": "experiment"}
        row.update({"error": err} if err else {"results": data})
        items.append(row)
    for p in rsv:
        data, err = _json(src, p)
        row = {"path": p, "name": p.split("/")[1], "kind": "resolved"}
        if err or not isinstance(data, dict):
            row["error"] = err or "%s must be an object" % p
        else:
            row.update({k: data.get(k) for k in ("question", "resolved_by", "sources", "as_of")})
        items.append(row)
    items.sort(key=lambda i: (i["name"], i["kind"]))
    return ok(items)


def _field(text, name):
    m = re.search(r"\*\*%s:?\*\*:?\s*(.+)|^%s:\s*(.+)" % (name, name), text, re.I | re.M)
    return next((g.strip() for g in m.groups() if g), None) if m else None


def c_adrs(src):
    paths = src.glob("docs/adr/*.md")
    if not paths:
        return unavailable("no docs/adr/*.md in %s" % src.where)
    items = []
    for p in paths:
        t = src.text(p) or ""
        s = stem(p)
        idm = re.match(r"(ADR-\d+)", s, re.I)
        st = re.search(r"\*\*Status:?\*\*:?\s*(.+)|^Status:\s*(.+)", t, re.I | re.M)
        dt = re.search(r"\*\*Date:?\*\*:?\s*(\S+)|^Date:\s*(\S+)", t, re.I | re.M)
        pick = lambda m: next((g.strip() for g in m.groups() if g), None) if m else None
        items.append({"path": p, "id": idm.group(1).upper() if idm else s, "title": _title(t, s),
                      "status": pick(st), "date": pick(dt)})
    return ok(items)


def _stories(text):
    out, level, on = [], 0, False
    for ln in text.splitlines():
        h = re.match(r"(#+)\s+(.*)", ln)
        if h:
            if re.search(r"ux stor|user stor|stories", h.group(2), re.I):
                on, level = True, len(h.group(1))
                continue
            if on and len(h.group(1)) <= level:
                on = False
        elif on and ln.strip():
            out.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", ln).strip())
    return out


ONEPAGER = "docs/prd/onepager.md"
_JOURNEY = re.compile(r"^##[ \t]+Journey:[ \t]*(.*?)[ \t]*$")


def _onepager(src):
    text = src.text(ONEPAGER)
    if text is None:
        return [], None, None
    lines = text.splitlines()
    tm = re.search(r"^#[ \t]+(.+?)[ \t]*$", text, re.M)
    existing = {p.split("/")[2] for p in src.ls("docs/slices") if p.count("/") >= 3}
    journeys, cur = [], None
    for ln in lines:
        m = _JOURNEY.match(ln)
        if m:
            cur = {"kind": "journey", "name": m.group(1), "steps": [], "slices": [], "flags": [], "_has_slices": False}
            journeys.append(cur)
            continue
        if re.match(r"#{1,6}\s", ln):
            cur = None
            continue
        if cur is None:
            continue
        sm = re.match(r"^\s*Slices:[ \t]*(.*?)\s*$", ln)
        if sm:
            cur["_has_slices"] = True
            for sid in (x.strip() for x in sm.group(1).split(",")):
                if sid and sid not in (x["id"] for x in cur["slices"]):
                    cur["slices"].append({"id": sid, "exists": sid in existing})
            continue
        bm = re.match(r"^\s*[-*]\s+(.*\S)\s*$", ln)
        if bm:
            cur["steps"].append(bm.group(1))
    for j in journeys:
        if not j.pop("_has_slices"):
            j["flags"].append("missing Slices line")
        for s_ in j["slices"]:
            if not s_["exists"]:
                j["flags"].append("unknown slice %s" % s_["id"])
        if not 1 <= len(j["steps"]) <= 5:
            j["flags"].append("%d steps (expected 1 to 5)" % len(j["steps"]))
    return journeys, ("longer than one page" if len(lines) > 80 else None), (tm.group(1) if tm else None)


def c_prd_journeys(src):
    items, warning, title = _onepager(src)
    rows = []
    for p in src.glob("docs/slices/*/proposal.md"):
        t = src.text(p) or ""
        pri = re.search(r"^priority:\s*(\S+)", t, re.I | re.M) or re.search(r"\*\*Priority:?\*\*:?\s*(\S+)", t, re.I)
        rows.append({"slice": p.split("/")[2], "path": p, "title": _title(t, p.split("/")[2]),
                     "priority": pri.group(1) if pri else None, "stories": _stories(t)})
    rows.sort(key=lambda i: (str(i["priority"] or "~"), i["slice"]))
    items += rows
    for p in src.glob("docs/prds/*.md"):
        t = src.text(p) or ""
        d = re.search(r"\*\*Delivers\*\*\s*\|\s*(.+?)\s*\|?\s*$|^Delivers:\s*(.+)$", t, re.M)
        items.append({"kind": "prd", "path": p, "title": _title(t, stem(p)),
                      "delivers": next((g.strip() for g in d.groups() if g), None) if d else None})
    if not items:
        return unavailable("no slices (docs/slices/*/proposal.md), no %s and no docs/prds/*.md in %s" % (ONEPAGER, src.where))
    res = ok(items, journeys=sum(1 for i in items if i.get("kind") == "journey"))
    if title:
        res["title"] = title
        res["summary"]["title"] = title
    if warning:
        res["warning"] = warning
        res["summary"]["warning"] = warning
    return res


BUG_STATUSES = ("open", "fixed", "wontfix")


def _first_heading(text, fallback):
    m = re.search(r"^#{1,6}\s+(.+?)\s*$", text, re.M)
    return m.group(1) if m else fallback


def _line(text, key):
    m = re.search(r"^\s*(?:\*\*)?%s:?(?:\*\*)?:?[ \t]*(.*?)\s*$" % key, text, re.I | re.M)
    return m.group(1).strip().strip("*_ \t") if m else None


def _qa_notes(src):
    items = []
    for p in src.glob("docs/slices/*/qa-notes.md"):
        text = src.text(p) or ""
        slice_id = p.split("/")[2]
        for blk in re.split(r"^(?=## Signature )", text, flags=re.M):
            m = re.match(r"## Signature (\S+)", blk)
            if not m:
                continue
            att = re.search(r"attempts\s+(\d+)", blk)
            items.append({"kind": "qa-note", "slice": slice_id, "path": p, "signature": m.group(1),
                          "attempts": int(att.group(1)) if att else None,
                          "criteria": [c.strip() for c in (_line(blk, "criteria") or "").split(",") if c.strip()],
                          "text": "signature %s: " % m.group(1) + " ".join(blk.split("\n", 1)[1].split())})
    return items


def c_bug_log(src):
    items = []
    t = src.text("docs/bug-log.jsonl")
    if t is not None:
        for i, ln in enumerate(t.splitlines(), 1):
            if ln.strip():
                try:
                    items.append(json.loads(ln))
                except ValueError:
                    items.append({"error": "docs/bug-log.jsonl line %d is not valid JSON" % i})
    for p in src.glob("docs/bugs/*.md"):
        tx = src.text(p) or ""
        st = (_line(tx, "Status") or "").lower()
        items.append({"id": stem(p), "path": p, "title": _first_heading(tx, stem(p)),
                      "status": st if st in BUG_STATUSES else "invalid",
                      "slice": _line(tx, "Slice") or None, "criterion": _line(tx, "Criterion") or None})
    items += _qa_notes(src)
    if not items:
        return unavailable("no entries in docs/bugs/*.md, docs/bug-log.jsonl or docs/slices/*/qa-notes.md in %s" % src.where)
    return ok(items)


def c_git(src):
    rows = src.commits()
    return ok(rows) if rows else unavailable("no commits reachable from %s" % src.where)


def c_docs(src):
    p = "docs/eli12/index.json"
    t = src.text(p)
    if t is None:
        return unavailable("docs/eli12/index.json not found")
    try:
        idx = json.loads(t)
    except ValueError as e:
        return unavailable("docs/eli12/index.json is not valid JSON: %s" % e)
    if isinstance(idx, dict) and isinstance(idx.get("modules"), dict):
        idx = idx["modules"]
    if isinstance(idx, list):
        pairs = [(x.get("module"), x.get("doc")) for x in idx if isinstance(x, dict)]
    elif isinstance(idx, dict):
        pairs = [(k, v) for k, v in idx.items() if isinstance(v, str)]
    else:
        return unavailable("docs/eli12/index.json has an unknown shape")
    items = []
    for n, (mod, doc) in enumerate(sorted((str(a), str(b)) for a, b in pairs if a and b)):
        row = {"module": mod, "doc": doc}
        if n < 200:
            md, code = src.text(doc) or "", src.text(mod) or ""
            syms = []
            for name in re.findall(r"^##\s+(\S+)", md, re.M):
                leaf = name.split(".")[-1]
                m = re.search(r"^[ \t]*(?:async\s+)?(?:def|class)\s+%s\b" % re.escape(leaf), code, re.M)
                syms.append({"name": name, "line": code[:m.start()].count("\n") + 1 if m else None})
            row["symbols"] = syms
        items.append(row)
    if not items:
        return unavailable("docs/eli12/index.json lists no modules")
    return ok(items)


COLLECTORS = [("research", c_research), ("experiments", c_experiments), ("adrs", c_adrs), ("bug_log", c_bug_log),
              ("prd_journeys", c_prd_journeys), ("architecture", c_architecture), ("git", c_git), ("docs", c_docs)]


def collect_tabs(src):
    tabs = {}
    for name, fn in COLLECTORS:
        src.truncated = 0
        try:
            tabs[name] = fn(src)
        except Exception as e:  # a broken source must show as unavailable, never as a crash or an empty success
            tabs[name] = unavailable("%s collector failed: %s" % (name, e))
        if src.truncated:
            t = tabs[name]
            if t["available"]:
                t["summary"]["truncated"] = "truncated: scan stopped at %d files" % src.truncated
            else:
                t["reason"] = "truncated: scan stopped at %d files; %s" % (src.truncated, t["reason"])
    return tabs


def resolve_sha(root, sha):
    if not isinstance(sha, str) or not re.match(r"^[0-9a-fA-F]{4,64}$", sha):
        raise Usage("sha must be 4 to 64 hex characters")
    out = git(root, "rev-parse", "--verify", "--quiet", sha + "^{commit}", timeout=10)
    if not out:
        raise Fail("unknown revision %s" % sha)
    return out.decode().strip()


# ---------------------------------------------------------------- rollback (a revert commit; history only grows)
def _vc(root, *args):
    try:
        p = subprocess.run(["git", "-C", root] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail("version control command failed: %s" % e)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def rollback_plan(root, sha):
    """Validate every refusal in D-14 and return (full sha, subject, changed files). Changes nothing."""
    try:
        full = resolve_sha(root, sha)
    except Usage:
        raise Fail("%s does not resolve to a commit" % sha)
    code, dirty, _ = _vc(root, "status", "--porcelain", "--untracked-files=no")
    if code != 0:
        raise Fail("cannot read the working tree status")
    if dirty.strip():
        raise Fail("working tree is not clean (tracked or staged changes); commit or discard them first")
    if _vc(root, "merge-base", "--is-ancestor", full, "HEAD")[0] != 0:
        raise Fail("%s is not an ancestor of HEAD" % full[:8])
    parents = _vc(root, "rev-list", "--parents", "-n1", full)[1].split()[1:]
    if not parents:
        raise Fail("%s is the root commit and cannot be reverted" % full[:8])
    if len(parents) > 1:
        raise Fail("%s is a merge commit and cannot be reverted" % full[:8])
    subject = _vc(root, "log", "-n1", "--format=%s", full)[1].strip()
    files = [f for f in _vc(root, "diff-tree", "--no-commit-id", "--name-only", "-r", full)[1].splitlines() if f]
    return full, subject, files


def rollback(root, sha, confirm_sha=None):
    with locked(root):
        full, subject, files = rollback_plan(root, sha)
        if confirm_sha is not None and confirm_sha != full:
            raise Fail("confirm_sha does not match the resolved commit %s" % full)
        code, _, err = _vc(root, "revert", "--no-edit", full)
        if code != 0:
            _vc(root, "revert", "--abort")
            if "conflict" in err.lower():
                raise Fail("revert conflicts; resolve by hand")
            raise Fail("revert failed: %s" % (err.strip().splitlines() or ["unknown error"])[-1][:200])
        new = head_sha(root)
        emit_event(root, "rollback", "reverted", "reverted %s as %s" % (full[:8], (new or "")[:8]),
                   extra={"reverted": full, "new_head": new}, force=True)
    return {"ok": True, "reverted": full, "new_head": new}


# ---------------------------------------------------------------- runtime state for status, serve
def read_events(root, limit=1000):
    return read_jsonl(lpath(root, "events.jsonl"), tail=True)[-limit:]


def cost_summary(root):
    by, tot = {}, 0.0
    for e in read_jsonl(lpath(root, "events.jsonl"), tail=True):
        if e.get("type") != "cost":
            continue
        m = e.get("model") or "unspecified"
        d = by.setdefault(m, {"usd": 0.0, "tokens": 0, "entries": 0})
        d["usd"] += float(e.get("usd") or 0)
        d["tokens"] += int(e.get("tokens") or 0)
        d["entries"] += 1
        tot += float(e.get("usd") or 0)
    for d in by.values():
        d["usd"] = round(d["usd"], 6)
    return {"label": "manual", "total_usd": round(tot, 6), "by_model": by}


def status_data(root):
    prof = load_profile(root)
    check_weights(prof)
    at = now()
    rows = phase_rows(root)
    ivs = intervals(rows, at)
    op = open_phase(rows)
    ids = phase_ids(prof)
    last = ivs[-1]["phase"] if ivs else None
    nxt = ids[0] if last is None else (ids[ids.index(last) + 1] if last in ids and ids.index(last) + 1 < len(ids) else None)
    stops = stops_state(root)
    return {
        "root": root, "now": iso(at), "session_minutes": prof["session_minutes"],
        "open_phase": ({"phase": op["phase"], "group": group_of(prof, op["phase"]), "started_at": iso(op["start"]),
                        "elapsed_minutes": round(minutes_between(op["start"], at), 2)} if op else None),
        "session_elapsed_minutes": round(minutes_between(ivs[0]["start"], at), 2) if ivs else None,
        "open_stops": [s for s in stops if "released_at" not in s], "next_phase": nxt,
        "stop_ledger": "ok", "clock_overridden": bool(os.environ.get("LSF_NOW")),
    }


def runtime_state(root):
    out = {"now": iso(now())}
    try:
        out["status"] = status_data(root)
    except (Fail, Usage) as e:
        out["status"] = {"error": str(e)}
    try:
        out["budget"] = budget_data(root)
    except (Fail, Usage) as e:
        out["budget"] = {"error": str(e)}
    try:
        out["stops"] = stops_state(root)
        out["stop_ledger"] = "ok"
    except Fail as e:
        out["stops"] = []
        out["stop_ledger"] = str(e)
    out["intervals"] = [{"phase": i["phase"], "start": iso(i["start"]), "end": iso(i["end"]) if i["end"] else None,
                         "verdict": i["verdict"]} for i in intervals(phase_rows(root), None)]
    out["events"] = read_events(root)
    out["cost"] = cost_summary(root)
    return out


def full_state(root):
    prof = load_profile(root)
    pub = {k: prof.get(k) for k in ("session_minutes", "phases", "weights", "checkpoints", "editor", "workspace_root", "models")}
    return {"tabs": collect_tabs(WorkTree(root)), "runtime": runtime_state(root), "profile": pub}


# ---------------------------------------------------------------- commands
def out(s=""):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def cmd_init(a, root):
    d = lsf_dir(root)
    existed = os.path.isfile(lpath(root, "profile.json"))
    os.makedirs(d, exist_ok=True)
    if existed:
        load_profile(root)
        out("lsf already initialised at %s (profile, events and stops kept)" % d)
        return 0
    if a.minutes <= 0:
        raise Usage("--minutes must be positive")
    w = dict(DEFAULT_WEIGHTS)
    for item in a.weight or []:
        k, _, v = item.partition("=")
        if k not in GROUPS:
            raise Usage("--weight needs align=, review= or build=")
        try:
            w[k] = float(v)
        except ValueError:
            raise Usage("bad weight %r" % item)
    prof = default_profile(root, a.minutes, a.checkpoints, a.editor, w)
    if a.strict_hitl:
        prof["require_tty_release"] = True
    check_weights(prof)
    atomic_write(lpath(root, "profile.json"), json.dumps(prof, indent=2, default=_jd) + "\n")
    out("initialised %s (session %d min, checkpoints: %s, editor: %s)" % (d, a.minutes, a.checkpoints, a.editor))
    out("next: lsf phase start 0-intake   |   dashboard: lsf serve --open")
    return 0


def require_clear(root):
    """Refuse (exit 3) while any human stop is open; a broken ledger is a failure, never 'no stops'."""
    try:
        op = open_stops(root)
    except Fail as e:
        out(str(e))
        raise
    if op:
        out("refused: %d open human stop(s); a human must release them (lsf hitl release NAME)" % len(op))
        for s in op:
            out("  - %s: %s" % (s["name"], s["question"]))
        raise StopError()


def cmd_phase(a, root):
    prof = load_profile(root)
    if a.name not in phase_ids(prof):
        raise Usage("unknown phase %r; one of %s" % (a.name, ", ".join(phase_ids(prof))))
    at = now()
    rows = phase_rows(root)
    op = open_phase(rows)
    if a.action == "start":
        require_clear(root)
        if op is not None:
            append_line(lpath(root, "phases.jsonl"), {"at": iso(at), "type": "end", "phase": op["phase"], "verdict": "switched"})
            emit_event(root, op["phase"], "switched", "ended by start of %s" % a.name, phase=op["phase"], slice_=a.slice,
                       duration_s=int((at - op["start"]).total_seconds()), extra={"type": "phase_end", "sf_stage": SF_ALIAS.get(op["phase"])})
        append_line(lpath(root, "phases.jsonl"), {"at": iso(at), "type": "start", "phase": a.name})
        emit_event(root, a.name, "started", a.note or "", phase=a.name, slice_=a.slice,
                   extra={"type": "phase_start", "sf_stage": SF_ALIAS.get(a.name)})
        out("started %s (%s)" % (a.name, group_of(prof, a.name)))
        return 0
    if op is None or op["phase"] != a.name:
        raise Fail("phase %s is not open" % a.name)
    verdict = a.verdict or "done"
    append_line(lpath(root, "phases.jsonl"), {"at": iso(at), "type": "end", "phase": a.name, "verdict": verdict})
    emit_event(root, a.name, verdict, a.note or "", phase=a.name, slice_=a.slice,
               duration_s=int((at - op["start"]).total_seconds()), extra={"type": "phase_end", "sf_stage": SF_ALIAS.get(a.name)})
    out("ended %s (%s, %.1f min)" % (a.name, verdict, minutes_between(op["start"], at)))
    cps = prof.get("checkpoints") if isinstance(prof.get("checkpoints"), dict) else {}
    mode_default = group_of(prof, a.name) == "align"
    if cps.get(a.name, mode_default):
        name = a.name + "-review"
        hitl_open(root, name, a.ask or "Approve %s?" % a.name, a.artifact or [],
                  "checkpoint after %s (%s)" % (a.name, verdict), bind=False)
        out("human checkpoint opened: %s  (release: lsf hitl release %s, or click Approve in the dashboard)" % (name, name))
    return 0


def cmd_event(a, root):
    if not a.stage.strip() or not a.verdict.strip():
        raise Usage("stage and verdict are required")
    op = open_phase(phase_rows(root))
    emit_event(root, a.stage, a.verdict, a.note or "", source=a.source, phase=a.phase or (op["phase"] if op else None),
               slice_=a.slice, role=a.role)
    return 0


def cmd_rollback(a, root):
    full, subject, files = rollback_plan(root, a.sha)
    if not a.yes:
        out("would revert %s: %s" % (full[:8], subject))
        out("files changed (%d): %s" % (len(files), ", ".join(files[:20]) + (" ..." if len(files) > 20 else "")))
        out("this adds a new commit that undoes it; history is kept. Re-run with --yes to do it.")
        return 2
    require_tty_if_strict(root, "rollback")
    r = rollback(root, full, full)
    out("reverted %s; new commit %s (history is kept)" % (full[:8], (r["new_head"] or "")[:8]))
    return 0


def fmt_stop(s):
    st = s.get("state") or ("answered" if "released_at" in s else "asked")
    when = "released %s by %s" % (s["released_at"], s.get("released_by")) if "released_at" in s else "OPEN since %s" % s["opened_at"]
    line = "%s: %s [%s, %s]%s" % (s["name"], s["question"], st, when, (" artifacts: " + ", ".join(s["artifact"])) if s["artifact"] else "")
    if s.get("options"):
        line += " options: " + " | ".join(s["options"])
    if s.get("answer"):
        line += " answer: " + s["answer"]
    if s.get("recorded_where"):
        line += " recorded in: " + s["recorded_where"]
    if s.get("applied_at"):
        line += " applied: " + (s.get("applied_evidence") or "")
    return line


def cmd_hitl(a, root):
    if a.action == "request":
        hitl_open(root, a.name, a.question, a.artifact or [], a.reason or "requested by the agent", a.option)
        out("human stop opened: %s" % a.name)
        return 0
    if a.action == "recorded":
        t = hitl_recorded(root, a.name, a.where, a.note or "")
        out("recorded %s at %s (answer written to %s; not applied yet)" % (a.name, t, a.where))
        return 0
    if a.action == "applied":
        t = hitl_applied(root, a.name, a.evidence)
        out("applied %s at %s" % (a.name, t))
        return 0
    if a.action == "release":
        require_tty_if_strict(root, "hitl release")
        via = "cli-tty" if sys.stdin.isatty() else "cli-nontty"
        t = hitl_release(root, a.name, a.note or "", a.by, via, answer=a.answer)
        out("released %s at %s via %s (a recorded procedure, not proof of identity)" % (a.name, t, via))
        return 0
    if a.action == "repair":
        if not a.yes:
            raise Usage("hitl repair moves the stop ledger aside and rebuilds it from its valid prefix; add --yes to do that")
        require_tty_if_strict(root, "hitl repair")
        moved, kept = hitl_repair(root)
        out("quarantined the old ledger as %s; kept %d valid entries" % (moved, kept))
        return 0
    try:
        stops = stops_state(root)
    except Fail as e:
        out(str(e))
        return 1
    op = [s for s in stops if "released_at" not in s]
    if a.json:
        out(json.dumps(stops, indent=2, default=_jd))
    elif not stops:
        out("no human stops recorded")
    else:
        for s in stops:
            out(fmt_stop(s))
    return 3 if op else 0


def cmd_status(a, root):
    try:
        d = status_data(root)
    except Fail as e:
        out(str(e))
        out("waiting on human: not measured (stop ledger failed verification)")
        raise
    if a.json:
        out(json.dumps(d, indent=2, default=_jd))
        return 0
    op = d["open_phase"]
    out("lsf status  %s" % d["now"])
    if os.environ.get("LSF_NOW"):
        out("WARN: clock overridden by LSF_NOW")
    out("open phase: %s" % ("%s (%s), elapsed %.1f min" % (op["phase"], op["group"], op["elapsed_minutes"]) if op else "none"))
    if d["session_elapsed_minutes"] is not None:
        out("session: %.1f of %d min" % (d["session_elapsed_minutes"], d["session_minutes"]))
    out("open human stops: %d" % len(d["open_stops"]))
    for s in d["open_stops"]:
        out("  - %s" % fmt_stop(s))
    out("next phase: %s" % (d["next_phase"] or "none (all phases done)"))
    return 0


def cmd_budget(a, root):
    d = budget_data(root)
    if a.json:
        out(json.dumps({"groups": d["groups"], "waiting_on_human_minutes": d["waiting_on_human_minutes"],
                        "session_total_minutes": d["session_total_minutes"], "session_minutes": d["session_minutes"],
                        "clock_overridden": d["clock_overridden"], "ledger_error": d.get("ledger_error")}, indent=2, default=_jd))
        return 1 if d.get("ledger_error") else 0
    if d["clock_overridden"]:
        out("WARN: clock overridden by LSF_NOW")
    for g in GROUPS:
        x = d["groups"][g]
        if x["actual_minutes"] is None:
            out("%-7s planned %.1f min, actual not measured, %s, human wait %.1f min" % (g, x["planned_minutes"], x["flag"], x["waiting_minutes"]))
        else:
            out("%-7s planned %.1f min, actual %.1f min (%.1f%% of plan), %s, human wait %.1f min" % (
                g, x["planned_minutes"], x["actual_minutes"], x["percent_of_plan"] or 0.0, x["flag"], x["waiting_minutes"]))
    if d.get("ledger_error"):
        out("waiting on human: not measured (stop ledger failed verification)")
        out(d["ledger_error"])
        return 1
    out("waiting on human: %.1f min (counted separately, not in the groups above)" % d["waiting_on_human_minutes"])
    out("session total: %.1f of %d planned min (phases plus waiting on human)" % (d["session_total_minutes"], d["session_minutes"]))
    return 0


def cmd_cost(a, root):
    if a.action == "add":
        if a.usd != a.usd or a.usd < 0 or a.usd == float("inf"):
            raise Usage("--usd must be a finite non-negative number")
        if a.tokens is not None and a.tokens < 0:
            raise Usage("--tokens must not be negative")
        extra = {"type": "cost", "usd": a.usd, "label": "manual"}
        if a.tokens is not None:
            extra["tokens"] = a.tokens
        if a.model:
            extra["model"] = clean_note(a.model, 120)
        emit_event(root, "cost", "manual", a.note or "", source="agent", extra=extra)
        out("cost recorded (manual): $%s" % a.usd)
        return 0
    s = cost_summary(root)
    if a.json:
        out(json.dumps(s, indent=2, default=_jd))
        return 0
    out("cost summary (manual entries, nothing is estimated)")
    for m, d in sorted(s["by_model"].items()):
        out("  %s: $%.4f, %d tokens, %d entries" % (m, d["usd"], d["tokens"], d["entries"]))
    out("  total: $%.4f" % s["total_usd"])
    return 0


def cmd_bundle(a, root):
    if a.sha:
        full = resolve_sha(root, a.sha)
        src = Source(root, full)
    else:
        src = WorkTree(root)
    tabs = collect_tabs(src)
    if a.json:
        out(json.dumps({"tabs": tabs}, default=_jd))
        return 0
    for name, t in tabs.items():
        out("%-13s %s" % (name, ("available, %d items" % len(t["items"])) if t["available"] else "not available: " + t["reason"]))
    return 0


# ---------------------------------------------------------------- hooks
def script_path():
    return os.path.abspath(__file__)


def hooks_config():
    base = "python3 %s hook " % shlex.quote(script_path())
    def grp(name, matcher=None):
        g = {"hooks": [{"type": "command", "command": base + name}]}
        if matcher:
            g = dict([("matcher", matcher)], **g)
        return [g]
    return {"hooks": {"SubagentStop": grp("SubagentStop"), "Stop": grp("Stop"), "PostToolUse": grp("PostToolUse", "Bash"),
                      "PreToolUse": grp("guard", "Bash")}}


def _own(cmd):
    return isinstance(cmd, str) and re.search(r"lsf\.py'?\s+hook\s", cmd) is not None


def merge_hooks(settings, install):
    s = json.loads(json.dumps(settings, default=_jd))
    hooks = s.setdefault("hooks", {}) if install else s.get("hooks", {})
    if not isinstance(hooks, dict):
        raise Fail("settings 'hooks' is not an object")
    for ev in list(hooks):
        groups = hooks[ev]
        if not isinstance(groups, list):
            continue
        keep = []
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                rest = [h for h in g["hooks"] if not (isinstance(h, dict) and _own(h.get("command")))]
                if rest:
                    g = dict(g)
                    g["hooks"] = rest
                    keep.append(g)
                elif not g["hooks"]:
                    keep.append(g)
            else:
                keep.append(g)
        if keep:
            hooks[ev] = keep
        else:
            del hooks[ev]
    if install:
        for ev, groups in hooks_config()["hooks"].items():
            hooks.setdefault(ev, [])
            hooks[ev].extend(groups)
    elif not hooks:
        s.pop("hooks", None)
    return s


def cmd_hooks(a, root):
    if a.action == "print":
        out(json.dumps(hooks_config(), indent=2, default=_jd))
        return 0
    proj = os.path.abspath(a.project)
    if not os.path.isdir(proj):
        raise Usage("--project %s is not a directory" % a.project)
    target = os.path.join(proj, ".claude", "settings.local.json")
    raw = read_capped(target)
    try:
        cur = json.loads(raw.decode("utf-8")) if raw is not None else {}
        if not isinstance(cur, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise Fail("%s is not valid JSON: %s" % (target, e))
    new = merge_hooks(cur, a.action == "install")
    before = json.dumps(cur, indent=2, sort_keys=True, default=_jd).splitlines()
    after = json.dumps(new, indent=2, sort_keys=True, default=_jd).splitlines()
    diff = list(difflib.unified_diff(before, after, "a/settings.local.json", "b/settings.local.json", lineterm=""))
    if not diff:
        out("no change: %s" % ("lsf hooks already installed" if a.action == "install" else "no lsf hooks found"))
        return 0
    for ln in diff:
        out(ln)
    if not a.apply:
        out("dry run: nothing written; add --apply to write %s" % target)
        return 0
    atomic_write(target, json.dumps(new, indent=2, default=_jd) + "\n")
    out("wrote %s" % target)
    return 0


def summarize(text, limit=200):
    return clean_note(" ".join(str(text).split()), limit)


_COMMIT = re.compile(r"(?:^|&&|\|\||;|\n|\()\s*(?:\w+=\S+\s+)*git\s+(?:-\S+\s+(?:[^-\s]\S*\s+)?)*commit\b")
_DENY_RELEASE = re.compile(r"hitl\s+(?:release|repair)\b")
_DENY_ROLLBACK = re.compile(r"\blsf(?:\.py)?\b[^\n;|&]*\brollback\b[^\n;|&]*--yes")
_STOPS_TOUCH = re.compile(r"\.lsf/(?:stops|\.lock)|stops\.(?:jsonl|head)")
_WRITES = re.compile(r"(?:>|\brm\b|\bmv\b|\btruncate\b|\btee\b|\bsed\b[^|;&]*\s-i|\bcp\b|\bdd\b|\bperl\b|\bpython|\bnode\b|\bln\b|\bchmod\b|\bsh\s+-c)")


def guard_reason(command):
    """Friction, not proof: a PreToolUse hook cannot stop every way of editing a file. Returns a denial reason or None."""
    if _DENY_RELEASE.search(command):
        return "lsf hitl release and repair are human acts; ask the owner to run them in their own terminal"
    if _STOPS_TOUCH.search(command) and _WRITES.search(command):
        return "the human stop ledger (.lsf/stops*) must not be written by an agent"
    if _DENY_ROLLBACK.search(command):
        return "lsf rollback --yes is a human act; ask the owner to run it in their own terminal"
    if re.search(r"/api/rollback", command):
        return "the rollback route is for the human's browser; an agent must not call it"
    if re.search(r"/api/hitl/release", command):
        return "the release route is for the human's browser; an agent must not call it"
    return None


def hook_root(root_arg, payload):
    """Nearest directory (from --root, else the payload cwd, else the cwd) that already has .lsf; None if there is none."""
    start = root_arg or (payload.get("cwd") if isinstance(payload.get("cwd"), str) else None)
    try:
        d = os.path.realpath(start or os.getcwd())
    except OSError:
        return None
    while True:
        if os.path.isdir(os.path.join(d, ".lsf")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def cmd_hook(a, root_arg):
    """Exits 0 and prints nothing on stdout, whatever arrives on stdin; only `guard` may exit 2 (a denial on stderr)."""
    try:
        raw = sys.stdin.buffer.read(MAX_READ)
        try:
            p = json.loads(raw.decode("utf-8", "replace").replace("\x00", " "))
        except ValueError:
            return 0
        if not isinstance(p, dict):
            return 0
        name = a.name
        ti = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        root = hook_root(root_arg, p)
        if name.lower() == "guard":
            why = guard_reason(cmd) if cmd else None
            if why:
                if root:
                    emit_event(root, "guard", "denied", summarize(cmd), source="hook")
                sys.stderr.write("lsf guard: %s (friction, not proof)\n" % why)
                return 2
            return 0
        if root is None:
            return 0
        role = p.get("agent_type") if isinstance(p.get("agent_type"), str) else None
        if name.lower().replace("-", "") in ("posttooluse", "posttool"):
            if not _COMMIT.search(cmd):
                return 0
            note = "%s: %s" % (p.get("tool_name") or "Bash", summarize(cmd))
            verdict = "commit"
        else:
            msg = p.get("last_assistant_message") or p.get("reason") or ""
            note = summarize(msg) if msg else "%s hook fired" % name
            verdict = "stopped"
        op = open_phase(phase_rows(root))
        emit_event(root, name, verdict, note[:200], source="hook", phase=op["phase"] if op else None, role=role)
    except BaseException:
        pass
    return 0


# ---------------------------------------------------------------- doctor
_ALLOWED_IMPORTS = {"argparse", "ast", "contextlib", "datetime", "fnmatch", "hashlib", "hmac", "json", "os", "re", "secrets",
                    "shlex", "subprocess", "sys", "tempfile", "time", "difflib", "http", "webbrowser", "platform",
                    "shutil", "threading", "io", "signal"}
_FORBIDDEN = ["".join(x) for x in (("fc", "ntl"), ("res", "ource"), ("tom", "llib"), ("pw", "d"), ("grp",), ("term", "ios"))]


def self_check():
    path = script_path()
    with open(path, "rb") as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=path, feature_version=(3, 9))
    except SyntaxError as e:
        return False, "does not parse as Python 3.9: line %s: %s" % (e.lineno, e.msg)
    bad = []
    for n in ast.walk(tree):
        mods = []
        if isinstance(n, ast.Import):
            mods = [x.name for x in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods = [n.module]
        for m in mods:
            top = m.split(".")[0]
            if top not in _ALLOWED_IMPORTS or top in _FORBIDDEN:
                bad.append(m)
        if n.__class__.__name__ in ("Match", "TryStar"):
            bad.append("3.10+ syntax (%s at line %s)" % (n.__class__.__name__, getattr(n, "lineno", "?")))
    if bad:
        return False, "disallowed: %s" % ", ".join(sorted(set(bad)))
    return True, "Python 3.9 syntax, standard library only"


def cmd_doctor(a, root):
    results = []

    def add(name, status, detail):
        results.append((name, status, detail))

    ok_py = sys.version_info >= (3, 9)
    add("python", "PASS" if ok_py else "FAIL", "Python %d.%d.%d" % sys.version_info[:3])
    g = git(root, "--version", timeout=10)
    add("git", "PASS" if g else "FAIL", g.decode().strip() if g else "git not found")
    top = git(root, "rev-parse", "--show-toplevel", timeout=10)
    add("repository", "PASS" if top else "FAIL", root if top else "%s is not a git repository" % root)
    try:
        port = int(a.port)
        if not 1 <= port <= 65535:
            raise ValueError
        srv = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
        srv.server_close()
        add("port", "PASS", "port %d is free" % port)
    except ValueError:
        add("port", "FAIL", "bad port %r" % a.port)
    except OSError as e:
        add("port", "FAIL", "port %s is not free: %s" % (a.port, e))
    try:
        os.makedirs(lsf_dir(root), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".doctor-", dir=lsf_dir(root))
        os.close(fd)
        os.unlink(tmp)
        add("writable", "PASS", "%s is writable" % lsf_dir(root))
    except OSError as e:
        add("writable", "FAIL", "%s is not writable: %s" % (lsf_dir(root), e))
    try:
        ed = load_profile(root).get("editor")
        add("editor", "PASS" if ed in EDITORS else "FAIL", "%s%s" % (ed, "" if ed in EDITORS else " is not one of " + ", ".join(EDITORS)))
    except Fail as e:
        add("editor", "FAIL", str(e))
    try:
        ok_s, why = self_check()
    except OSError as e:
        ok_s, why = False, "could not read lsf.py: %s" % e
    add("self-check", "PASS" if ok_s else "FAIL", why)
    node = subprocess.run(["node", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip() \
        if _has("node") else None
    if os.environ.get("LSF_NOW"):
        add("clock", "WARN", "LSF_NOW is set (%s): every timestamp is overridden" % os.environ["LSF_NOW"])
    add("node", "INFO", node or "not found (optional, only for browser-free checks)")
    for n, s, d in results:
        out("%s %s: %s" % (s, n, d))
    return 1 if any(s == "FAIL" for _, s, _ in results) else 0


def _has(cmd):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        f = os.path.join(d, cmd)
        if os.path.isfile(f) and os.access(f, os.X_OK):
            return True
    return False


# ---------------------------------------------------------------- serve
def _unquote(s):
    s = s.replace("+", " ")
    return re.sub(rb"%([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), s.encode("utf-8")).decode("utf-8", "replace")


def parse_query(q):
    d = {}
    for part in q.split("&"):
        if part:
            k, _, v = part.partition("=")
            d.setdefault(_unquote(k), _unquote(v))
    return d


def safe_rel(rel):
    """Validate a path from the browser. Returns (ok, status, message)."""
    if not rel or "\0" in rel or "\\" in rel or rel.startswith("/") or len(rel) > 4096:
        return False, 400, "bad path"
    segs = rel.split("/")
    if any(s in ("", ".", "..") for s in segs):
        return False, 400, "bad path"
    return True, 200, ""


def forbidden_rel(rel):
    segs = rel.split("/")
    if any(s.lower() == ".git" for s in segs):
        return True
    if any(s.lower().startswith(".env") for s in segs):
        return True
    if segs[0].lower() == ".lsf" and any(("secret" in s.lower() or "token" in s.lower()) for s in segs):
        return True
    return False


def read_repo_file(root, rel):
    ok_, status, msg = safe_rel(rel)
    if not ok_:
        return status, msg, None
    if forbidden_rel(rel):
        return 403, "forbidden", None
    full = os.path.join(root, *rel.split("/"))
    real = os.path.realpath(full)
    try:
        inside = os.path.commonpath([real, root]) == root
    except ValueError:
        inside = False
    if not inside:
        return 403, "outside the repository", None
    rrel = os.path.relpath(real, root).replace(os.sep, "/")
    if forbidden_rel(rrel):
        return 403, "forbidden", None
    if not os.path.isfile(real):
        return 404, "not found", None
    try:
        if os.path.getsize(real) > MAX_FILE_API:
            return 413, "file larger than 1 MiB", None
        with open(real, "rb") as f:
            data = f.read(MAX_FILE_API + 1)
        return 200, "", data.decode("utf-8")
    except UnicodeDecodeError:
        return 415, "not UTF-8 text", None
    except OSError as e:
        return 404, str(e), None


def make_handler(root, token, assets_html):
    class H(BaseHTTPRequestHandler):
        server_version = "lsf"
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt, *args):  # never log request lines, bodies or the token
            pass

        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _err(self, status, msg):
            self._send(status, json.dumps({"error": msg}, default=_jd))

        def _host_ok(self):
            host = self.headers.get("Host", "")
            h = host.rsplit(":", 1)[0] if not host.endswith("]") else host
            if h not in ("127.0.0.1", "localhost", "[::1]"):
                return False
            org = self.headers.get("Origin")
            if org:
                m = re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", org)
                if not m:
                    return False
            return True

        def do_GET(self):
            try:
                if not self._host_ok():
                    return self._err(403, "forbidden host")
                path, _, q = self.path.partition("?")
                qs = parse_query(q)
                if path == "/":
                    return self._send(200, assets_html(), "text/html; charset=utf-8",
                                      {"Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; "
                                       "style-src 'unsafe-inline'; img-src 'self' data:; frame-src 'self'"})
                if path == "/api/state":
                    return self._send(200, json.dumps(full_state(root), default=_jd))
                if path == "/api/file":
                    status, msg, text = read_repo_file(root, qs.get("path", ""))
                    if status != 200:
                        return self._err(status, msg)
                    if qs.get("view") == "html" and qs.get("path", "").lower().endswith(".html"):
                        return self._send(200, text, "text/html; charset=utf-8",
                                          {"Content-Security-Policy": "sandbox allow-scripts"})
                    return self._send(200, text, "text/plain; charset=utf-8")
                if path == "/api/at":
                    try:
                        full = resolve_sha(root, qs.get("sha", ""))
                    except (Usage, Fail) as e:
                        return self._err(400, str(e))
                    return self._send(200, json.dumps({"sha": full, "tabs": collect_tabs(Source(root, full))}, default=_jd))
                return self._err(404, "not found")
            except Exception as e:
                return self._err(500, "internal error: %s" % e.__class__.__name__)

        def do_POST(self):
            try:
                if not self._host_ok():
                    return self._err(403, "forbidden host")
                path = self.path.partition("?")[0]
                if path not in ("/api/hitl/release", "/api/rollback"):
                    return self._err(404, "not found")
                if not hmac.compare_digest(self.headers.get("X-LSF-Token", "").encode("utf-8", "replace"), token.encode()):
                    return self._err(403, "missing or wrong token")
                try:
                    n = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    return self._err(411, "Content-Length required")
                if n < 0 or n > 65536:
                    return self._err(413, "body too large")
                if path == "/api/rollback":
                    return self._rollback(n)
                try:
                    body = json.loads(self.rfile.read(n).decode("utf-8"))
                    name, note = body["name"], body.get("note", "")
                    answer, ph = body.get("answer"), body.get("proposal_hash")
                    if not isinstance(name, str) or not isinstance(note, str) \
                            or not all(v is None or isinstance(v, str) for v in (answer, ph)):
                        raise ValueError
                except (ValueError, KeyError, TypeError, AttributeError):
                    return self._err(400, "body must be JSON {name, note, answer, proposal_hash}")
                try:
                    mine = [x for x in stops_state(root) if x["name"] == name]
                    if ph is None and mine and mine[-1]["state"] == "asked" and mine[-1].get("proposal_hash") and mine[-1].get("options"):
                        return self._err(400, "proposal_hash is required for this stop")
                    t = hitl_release(root, name, note, "dashboard", answer=answer or None, proposal_hash=ph)
                except Usage as e:
                    return self._err(400, str(e))
                except Fail as e:
                    return self._err(409, str(e))
                return self._send(200, json.dumps({"ok": True, "name": name, "released_at": t}, default=_jd))
            except Exception as e:
                return self._err(500, "internal error: %s" % e.__class__.__name__)

        def _rollback(self, n):
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                sha, confirm = body["sha"], body["confirm_sha"]
                if not isinstance(sha, str) or not isinstance(confirm, str):
                    raise ValueError
            except (ValueError, KeyError, TypeError, AttributeError):
                return self._err(400, "body must be JSON {sha, confirm_sha}")
            try:
                r = rollback(root, sha, confirm)
            except Usage as e:
                return self._err(400, str(e))
            except Fail as e:
                return self._err(409, str(e))
            return self._send(200, json.dumps(r, default=_jd))

        def _no(self):
            self._err(405, "method not allowed")

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _no

    return H


def cmd_serve(a, root):
    asset = os.path.join(os.path.dirname(os.path.dirname(script_path())), "assets", "dashboard.html")
    if not os.path.isfile(asset):
        raise Fail("dashboard asset missing: %s" % asset)

    def assets_html():
        with open(asset, "rb") as f:
            return f.read()

    token = secrets.token_hex(16)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(root, token, assets_html))
    except OSError as e:
        raise Fail("cannot listen on 127.0.0.1:%d: %s" % (a.port, e))
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/#token=%s" % (srv.server_address[1], token)
    out("lsf dashboard: %s" % url)
    out("serving %s on 127.0.0.1 only; press Ctrl-C to stop" % root)
    if a.open:
        opened = False
        for opener in ("open", "xdg-open"):
            if _has(opener):
                try:
                    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    opened = True
                    break
                except OSError:
                    pass
        if not opened:
            import webbrowser
            webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


# ---------------------------------------------------------------- parser and main
def build_parser():
    ap = argparse.ArgumentParser(prog="lsf", description="lite software factory: phase clock, telemetry, human checkpoints, dashboard",
                                 epilog="Every command accepts --root DIR (default: nearest git root, else the current directory). "
                                        "Exit codes: 0 ok, 1 check failed, 2 usage, 3 refused by a human stop.")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")
    sub.required = True

    def mk(name, fn, help_):
        p = sub.add_parser(name, help=help_, description=help_)
        p.set_defaults(fn=fn)
        p.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS, help="project root (default: nearest git root)")
        return p

    p = mk("init", cmd_init, "create .lsf/profile.json")
    p.add_argument("--minutes", type=int, default=60, help="session length in minutes (default 60)")
    p.add_argument("--checkpoints", choices=["align", "all", "none"], default="align")
    p.add_argument("--editor", choices=EDITORS, default="vscode")
    p.add_argument("--strict-hitl", action="store_true", help="hitl release and repair refuse unless stdin is a terminal")
    p.add_argument("--weight", action="append", metavar="GROUP=W", help="align|review|build weight, repeatable; must sum to 1.0")

    p = mk("phase", cmd_phase, "start or end a phase")
    ps = p.add_subparsers(dest="action", metavar="start|end")
    ps.required = True
    for act in ("start", "end"):
        q = ps.add_parser(act)
        q.add_argument("name")
        q.add_argument("--note")
        q.add_argument("--slice")
        q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
        if act == "end":
            q.add_argument("--verdict")
            q.add_argument("--ask", help="the question for the checkpoint this phase opens")
            q.add_argument("--artifact", action="append", help="artifact path for the checkpoint, repeatable")

    p = mk("event", cmd_event, "append one telemetry event")
    p.add_argument("stage")
    p.add_argument("verdict")
    p.add_argument("--note")
    p.add_argument("--role")
    p.add_argument("--slice")
    p.add_argument("--phase")
    p.add_argument("--source", choices=["lsf", "hook", "agent"], default="agent")

    p = mk("rollback", cmd_rollback, "revert a commit with a new commit (never rewrites history)")
    p.add_argument("sha")
    p.add_argument("--yes", action="store_true", help="do it; without this only show what would be reverted")

    p = mk("hitl", cmd_hitl, "human decisions: request, status, release, recorded, applied")
    hs = p.add_subparsers(dest="action", metavar="request|status|release|recorded|applied|repair")
    hs.required = True
    q = hs.add_parser("request")
    q.add_argument("name")
    q.add_argument("--question", required=True)
    q.add_argument("--artifact", action="append")
    q.add_argument("--option", action="append", help="an answer the human may pick; repeat up to 6 times")
    q.add_argument("--reason")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = hs.add_parser("recorded", description="After the answer is written down (answered -> recorded).")
    q.add_argument("name")
    q.add_argument("--where", required=True, help="existing file or directory inside the repo")
    q.add_argument("--note")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = hs.add_parser("applied", description="After the recorded answer was acted on (recorded -> applied).")
    q.add_argument("name")
    q.add_argument("--evidence", required=True)
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = hs.add_parser("status")
    q.add_argument("--json", action="store_true")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = hs.add_parser("repair", description="Quarantine a failed stop ledger and rebuild it from its valid prefix. A human act.")
    q.add_argument("--yes", action="store_true")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = hs.add_parser("release", description="Release is a human act; agents must never run it. It records who and when; it is a procedure, not proof of identity.")
    q.add_argument("name")
    q.add_argument("--note")
    q.add_argument("--answer", help="required when the stop has options; must equal one of them")
    q.add_argument("--by")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)

    p = mk("status", cmd_status, "open phase, elapsed time, open stops, next phase")
    p.add_argument("--json", action="store_true")
    p = mk("budget", cmd_budget, "planned versus actual minutes per group")
    p.add_argument("--json", action="store_true")
    p = mk("serve", cmd_serve, "serve the dashboard on 127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true")
    p = mk("bundle", cmd_bundle, "print the dashboard tab data")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sha", help="read the tabs as of this commit")

    p = mk("hooks", cmd_hooks, "print, install or uninstall the Claude Code hooks")
    hk = p.add_subparsers(dest="action", metavar="print|install|uninstall")
    hk.required = True
    hk.add_parser("print").add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    for act in ("install", "uninstall"):
        q = hk.add_parser(act)
        q.add_argument("--project", required=True, metavar="DIR")
        q.add_argument("--apply", action="store_true", help="write the change (default: show the diff only)")
        q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)

    p = mk("hook", cmd_hook, "hook entry point (reads the JSON payload on stdin; always exits 0)")
    p.add_argument("name")
    p = mk("doctor", cmd_doctor, "check the environment")
    p.add_argument("--port", default=8765)
    p = mk("cost", cmd_cost, "manual cost log")
    cs = p.add_subparsers(dest="action", metavar="add|summary")
    cs.required = True
    q = cs.add_parser("add")
    q.add_argument("--usd", type=float, required=True)
    q.add_argument("--tokens", type=int)
    q.add_argument("--model")
    q.add_argument("--note")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    q = cs.add_parser("summary")
    q.add_argument("--json", action="store_true")
    q.add_argument("--root", metavar="DIR", default=argparse.SUPPRESS)
    return ap


def extract_root(argv):
    rest, root, i = [], None, 0
    while i < len(argv):
        x = argv[i]
        if x == "--root":
            if i + 1 >= len(argv):
                raise Usage("--root needs a directory")
            root, i = argv[i + 1], i + 2
            continue
        if x.startswith("--root="):
            root, i = x[7:], i + 1
            continue
        rest.append(x)
        i += 1
    return rest, root


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        argv, root_arg = extract_root(argv)
        args = build_parser().parse_args(argv)
        if args.cmd == "hook":
            return args.fn(args, os.path.abspath(root_arg) if root_arg else None)
        root = find_root(root_arg)
        return args.fn(args, root)
    except Usage as e:
        sys.stderr.write("usage error: %s\n" % e)
        return 2
    except StopError:
        return 3
    except Fail as e:
        sys.stderr.write("%s\n" % e)
        return 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
