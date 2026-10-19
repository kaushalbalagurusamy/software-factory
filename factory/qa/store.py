"""QA runtime state in .sf/slices/<id>/: state.json plus hash-chained append-only logs.

attempts.jsonl and failures.jsonl are chained (each line carries prev and hash); state.json
records the length and head hash of both, so rewrites, deletions and truncation are detected by
`audit`. Counters are always derived from the log, never trusted from state.json.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ZERO = "0" * 64
COUNTED = ("pass", "fail")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SIG = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")


def check_signature(sig) -> str:
    """Signatures become file names and headers; accept only [A-Za-z0-9_-]{1,64}."""
    if not isinstance(sig, str) or not _SIG.match(sig):
        raise ValueError("invalid signature: must match ^[A-Za-z0-9_-]{1,64}$")
    return sig


class AuditError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


class SliceStore:
    def __init__(self, root, slice_id: str):
        if not _ID.match(slice_id):
            raise ValueError(f"bad slice id {slice_id!r}")
        self.root, self.id = Path(root), slice_id
        self.dir = self.root / ".sf" / "slices" / slice_id

    # state.json -------------------------------------------------------------
    @property
    def state(self) -> dict:
        return json.loads((self.dir / "state.json").read_text(encoding="utf-8"))

    def _save(self, st: dict) -> None:
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.dir / "state.json")

    def init(self, criteria, force=False) -> None:
        if (self.dir / "state.json").exists() and not force:
            raise FileExistsError(f"{self.dir / 'state.json'} exists; use force to change criteria")
        old = self.state if (self.dir / "state.json").exists() else {}
        self.dir.mkdir(parents=True, exist_ok=True)
        st = {"schema_version": 1, "slice": self.id, "criteria": sorted(set(criteria)),
              "verified": old.get("verified", []), "proposals": old.get("proposals", {}),
              "reviewer": old.get("reviewer", {}), "status": old.get("status", "active"),
              "waits_on": old.get("waits_on"), "feedback_count": old.get("feedback_count", 0),
              "attempts_len": old.get("attempts_len", 0), "attempts_head": old.get("attempts_head", ZERO),
              "failures_len": old.get("failures_len", 0), "failures_head": old.get("failures_head", ZERO)}
        self._save(st)
        for n in ("attempts.jsonl", "failures.jsonl"):
            (self.dir / n).touch()

    def _update(self, **kw) -> dict:
        st = self.state
        st.update(kw)
        self._save(st)
        return st

    def note_proposal(self, sig: str, path: str) -> None:
        check_signature(sig)
        st = self.state
        st["proposals"][sig] = path
        self._save(st)

    def set_reviewer_verdict(self, sig: str, verdict: str, note: str) -> None:
        check_signature(sig)
        if verdict not in ("amended", "unresolved"):
            raise ValueError("verdict must be amended or unresolved")
        st = self.state
        st["reviewer"][sig] = {"verdict": verdict, "note": note, "at_len": st["attempts_len"], "at": now()}
        if verdict == "amended":
            st["status"], st["waits_on"] = "active", None
        self._save(st)

    def set_status(self, status: str, waits_on=None) -> None:
        self._update(status=status, waits_on=waits_on)

    def mark_verified(self, ids) -> None:
        st = self.state
        st["verified"] = sorted(set(st["verified"]) | set(ids))
        self._save(st)

    def next_feedback_number(self) -> int:
        st = self.state
        st["feedback_count"] += 1
        self._save(st)
        return st["feedback_count"]

    # chained logs -----------------------------------------------------------
    def append(self, log: str, entry: dict) -> dict:
        st = self.state
        key = log.split(".")[0]
        body = dict(entry, seq=st[f"{key}_len"] + 1, at=now(), prev=st[f"{key}_head"])
        body["hash"] = _hash(body["prev"], {k: v for k, v in body.items() if k not in ("hash", "prev")})
        with open(self.dir / log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, sort_keys=True) + "\n")
        st[f"{key}_len"], st[f"{key}_head"] = body["seq"], body["hash"]
        self._save(st)
        return body

    def read(self, log: str) -> list:
        p = self.dir / log
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []

    def audit(self) -> list:
        problems = []
        try:
            st = self.state
        except (OSError, ValueError) as e:
            return [f"state.json unreadable: {e}"]
        for log in ("attempts.jsonl", "failures.jsonl"):
            key = log.split(".")[0]
            prev, n = ZERO, 0
            try:
                lines = self.read(log)
            except ValueError as e:
                problems.append(f"{log}: unparsable line: {e}")
                continue
            for i, l in enumerate(lines, 1):
                body = {k: v for k, v in l.items() if k not in ("hash", "prev")}
                if l.get("seq") != i:
                    problems.append(f"{log} line {i}: seq {l.get('seq')} out of order (line removed or inserted)")
                if l.get("prev") != prev:
                    problems.append(f"{log} line {i}: chain broken (prev mismatch)")
                if l.get("hash") != _hash(l.get("prev", ""), body):
                    problems.append(f"{log} line {i}: hash mismatch (line was edited)")
                prev, n = l.get("hash", ""), i
            if n != st[f"{key}_len"]:
                problems.append(f"{log} length {n} != recorded {st[f'{key}_len']} (truncated or appended outside the tool)")
            elif prev != (st[f"{key}_head"] if n else ZERO):
                problems.append(f"{log} head hash differs from state.json (history was replaced)")
        return problems

    # derived facts ----------------------------------------------------------
    def facts(self) -> dict:
        st = self.state
        reviewer = st["reviewer"]
        amend_at = {s: v["at_len"] for s, v in reviewer.items() if v["verdict"] == "amended"}
        base_all = max(amend_at.values(), default=0)
        f = {"runs": 0, "counted": 0, "counted_window": 0, "flakes": 0, "env_runs": 0, "gate": "none",
             "trailing_suspects": 0, "env_pending": False, "env_consecutive": 0, "current_sig": None,
             "fails_by_sig": {}, "last_fail_seq": 0, "sig_info": {}, "last_tier_by_sig": {},
             "tokens": 0, "cost_usd": 0.0, "last": None, "last_tier": None}
        for l in self.read("attempts.jsonl"):
            o = l["outcome"]
            f["runs"] += 1
            f["last"], f["last_tier"] = l, l.get("tier")
            f["tokens"] += l.get("tokens") or 0
            f["cost_usd"] += l.get("cost_usd") or 0
            f["current_sig"] = None
            if o == "environment":
                f.update(env_pending=True, gate="failed", trailing_suspects=0)
                f["env_runs"] += 1
                f["env_consecutive"] += 1
                continue
            f["env_pending"], f["env_consecutive"] = False, 0
            if o == "suspect":
                f["trailing_suspects"] += 1
                f["gate"], f["current_sig"] = "failed", l["signature"]
                f["sig_info"][l["signature"]] = {"case": l.get("case"), "criterion": l.get("criterion")}
                continue
            f["trailing_suspects"] = 0
            if o == "flake":
                f["flakes"] += 1
                f["gate"] = "passed"
                continue
            f["counted"] += 1
            if l["seq"] > base_all:
                f["counted_window"] += 1
            if o == "pass":
                f["gate"] = "passed"
            else:
                sig = l["signature"]
                f["gate"], f["current_sig"], f["last_fail_seq"] = "failed", sig, l["seq"]
                f["sig_info"][sig] = {"case": l.get("case"), "criterion": l.get("criterion")}
                f["last_tier_by_sig"][sig] = l.get("tier")
                if l["seq"] > amend_at.get(sig, 0):
                    f["fails_by_sig"].setdefault(sig, []).append(l["seq"])
        return f
