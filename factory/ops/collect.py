"""Read-only collectors for the HISTORICAL tabs of the dashboard.

Everything here reads from the git object database at a given sha (``git ls-tree`` / ``git show``), so any past
commit can be rebuilt after later commits exist. A working-tree source is available for uncommitted state.
Nothing in this module touches runtime data; that lives in ``runtime.py`` and never enters a snapshot.

Each collector returns ``{"available": True, "summary": {...}, "items": [...]}`` or
``{"available": False, "reason": "..."}``. A missing artifact is never an empty success.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

COLLECTOR_VERSION = "1"
TABS = ("architecture", "research", "experiments", "adrs", "prd_journeys", "evals", "bug_log", "dev_journey", "git", "hitl")


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout if p.returncode == 0 else b""


class GitSource:
    """Files as of a commit, from the object database."""

    def __init__(self, repo: Path, sha: str):
        self.repo = Path(repo)
        self.sha = sha
        self._paths: list[str] | None = None

    def paths(self) -> list[str]:
        if self._paths is None:
            out = _git(self.repo, "ls-tree", "-r", "--name-only", "-z", self.sha)
            self._paths = [p for p in out.decode("utf-8", "replace").split("\0") if p]
        return self._paths

    def _pathset(self) -> set[str]:
        if getattr(self, "_ps_for", None) is not self._paths or not hasattr(self, "_ps"):
            self._ps = set(self.paths())
            self._ps_for = self._paths
        return self._ps

    def glob(self, pattern: str) -> list[str]:
        depth = pattern.count("/")
        return sorted(p for p in self.paths() if p.count("/") == depth and fnmatch.fnmatchcase(p, pattern))

    def read(self, path: str) -> bytes | None:
        if path not in self._pathset():
            return None
        return _git(self.repo, "show", f"{self.sha}:{path}")

    def text(self, path: str) -> str | None:
        b = self.read(path)
        return None if b is None else b.decode("utf-8", "replace")

    def commit_date(self) -> str | None:
        """Committer date of the snapshot commit (None for the working tree or when unknown)."""
        out = _git(self.repo, "show", "-s", "--format=%cI", self.sha, check=False).decode("utf-8", "replace").strip()
        return out or None

    def commits(self, limit: int = 200) -> list[dict]:
        out = _git(self.repo, "log", f"-n{limit}", "--format=%H%x1f%cI%x1f%s", self.sha).decode("utf-8", "replace")
        rows = []
        for line in out.splitlines():
            h, d, s = (line.split("\x1f") + ["", ""])[:3]
            rows.append({"sha": h, "date": d, "subject": s})
        return rows


class WorkTreeSource(GitSource):
    """Files as they are on disk (uncommitted state). Git history is still read from HEAD."""

    def __init__(self, repo: Path):
        super().__init__(repo, "HEAD")

    def commit_date(self) -> str | None:
        return None

    def paths(self) -> list[str]:
        if self._paths is None:
            out = _git(self.repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
            self._paths = sorted({p for p in out.decode("utf-8", "replace").split("\0") if p and (self.repo / p).is_file() and not (self.repo / p).is_symlink()})
        return self._paths

    def read(self, path: str) -> bytes | None:
        f = self.repo / path
        # never follow a symlink out of the repository (a planted link must not expose other files)
        if f.is_symlink() or not f.is_file():
            return None
        try:
            f.resolve().relative_to(self.repo.resolve())
        except ValueError:
            return None
        return f.read_bytes()


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


def ok(items: list, **summary) -> dict:
    return {"available": True, "summary": {"count": len(items), **summary}, "items": items}


def _json(src: GitSource, path: str):
    t = src.text(path)
    if t is None:
        return None, f"{path} missing"
    try:
        return json.loads(t), None
    except json.JSONDecodeError as e:
        return None, f"{path} is not valid JSON: {e}"


def _title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    return m.group(1) if m else fallback


# ---- architecture -----------------------------------------------------------------------------------------

def architecture(src: GitSource) -> dict:
    paths = sorted(set(src.glob("docs/explorer/*.model.json")) | set(src.glob("docs/architecture/*.model.json")))
    if not paths:
        return unavailable("no docs/explorer/*.model.json or docs/architecture/*.model.json at this commit")
    items = []
    for p in paths:
        model, err = _json(src, p)
        if err:
            items.append({"path": p, "error": err})
            continue
        nodes = model.get("nodes", {}) if isinstance(model, dict) else {}
        items.append({
            "path": p,
            "title": (model.get("meta") or {}).get("title") or p,
            "nodes": len(nodes),
            "diagrams": sum(1 for n in nodes.values() if n.get("diagram")),
            "model": model,  # lifted into its own blob by the bundler
        })
    return ok(items)


# ---- research ---------------------------------------------------------------------------------------------

def research(src: GitSource) -> dict:
    paths = src.glob("research/*.md")
    if not paths:
        return unavailable("no research/*.md at this commit")
    items = []
    for p in paths:
        t = src.text(p) or ""
        m = re.search(r"as of:?\**:?\s*([^\n.]*)", t, re.I)
        items.append({"path": p, "title": _title(t, Path(p).stem), "as_of": m.group(1).strip() if m else None})
    return ok(items)


# ---- experiments ------------------------------------------------------------------------------------------

def experiments(src: GitSource) -> dict:
    res, rsv = src.glob("experiments/*/results.json"), src.glob("experiments/*/resolved.json")
    if not res and not rsv:
        return unavailable("no experiments/*/results.json and no experiments/*/resolved.json at this commit")
    items = []
    for p in res:
        data, err = _json(src, p)
        items.append({"path": p, "name": p.split("/")[1], "kind": "experiment", **({"error": err} if err else {"results": data})})
    for p in rsv:
        data, err = _json(src, p)
        row = {"path": p, "name": p.split("/")[1], "kind": "resolved"}
        if err or not isinstance(data, dict):
            row["error"] = err or f"{p} must be an object"
        else:
            row.update({k: data.get(k) for k in ("question", "resolved_by", "sources", "as_of")})
        items.append(row)
    items.sort(key=lambda i: (i["name"], i["kind"]))
    return ok(items)


# ---- adrs -------------------------------------------------------------------------------------------------

def adrs(src: GitSource) -> dict:
    paths = src.glob("docs/adr/*.md")
    if not paths:
        return unavailable("no docs/adr/*.md at this commit")
    items = []
    for p in paths:
        t = src.text(p) or ""
        stem = Path(p).stem
        idm = re.match(r"(ADR-\d+)", stem, re.I)
        st = re.search(r"\*\*Status:?\*\*:?\s*(.+)|^Status:\s*(.+)", t, re.I | re.M)
        dt = re.search(r"\*\*Date:?\*\*:?\s*(\S+)|^Date:\s*(\S+)", t, re.I | re.M)
        pick = lambda m: next((g.strip() for g in m.groups() if g), None) if m else None
        items.append({"path": p, "id": idm.group(1).upper() if idm else stem, "title": _title(t, stem),
                      "status": pick(st), "date": pick(dt)})
    return ok(items)


# ---- prd journeys -----------------------------------------------------------------------------------------

def _stories(text: str) -> list[str]:
    lines = text.splitlines()
    out, level, on = [], 0, False
    for ln in lines:
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


def _onepager(src: GitSource) -> tuple[list[dict], str | None]:
    text = src.text(ONEPAGER)
    if text is None:
        return [], None
    lines = text.splitlines()
    existing = {p.split("/")[2] for p in src.paths() if p.startswith("docs/slices/") and p.count("/") >= 3}
    journeys: list[dict] = []
    cur = None
    for ln in lines:
        m = _JOURNEY.match(ln)
        if m:
            cur = {"kind": "journey", "name": m.group(1), "steps": [], "slices": [], "flags": [], "_has_slices": False}
            journeys.append(cur)
            continue
        if re.match(r"#{1,6}\s", ln):  # any other heading closes the journey
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
                j["flags"].append(f"unknown slice {s_['id']}")
        if not 1 <= len(j["steps"]) <= 5:
            j["flags"].append(f"{len(j['steps'])} steps (expected 1 to 5)")
    return journeys, ("longer than one page" if len(lines) > 80 else None)


def prd_journeys(src: GitSource) -> dict:
    items, warning = _onepager(src)
    props = src.glob("docs/slices/*/proposal.md")
    prds = src.glob("docs/prds/*.md")
    rows = []
    for p in props:
        t = src.text(p) or ""
        pri = re.search(r"^priority:\s*(\S+)", t, re.I | re.M) or re.search(r"\*\*Priority:?\*\*:?\s*(\S+)", t, re.I)
        rows.append({"slice": p.split("/")[2], "path": p, "title": _title(t, p.split("/")[2]),
                     "priority": pri.group(1) if pri else None, "stories": _stories(t)})
    rows.sort(key=lambda i: (str(i["priority"] or "~"), i["slice"]))
    items += rows
    for p in prds:
        t = src.text(p) or ""
        d = re.search(r"\*\*Delivers\*\*\s*\|\s*(.+?)\s*\|?\s*$|^Delivers:\s*(.+)$", t, re.M)
        items.append({"kind": "prd", "path": p, "title": _title(t, Path(p).stem),
                      "delivers": next((g.strip() for g in d.groups() if g), None) if d else None})
    if not items:
        return unavailable(f"no slices (docs/slices/*/proposal.md), no {ONEPAGER} and no docs/prds/*.md at this commit")
    out = ok(items, journeys=sum(1 for i in items if i.get("kind") == "journey"))
    if warning:
        out["warning"] = warning
        out["summary"]["warning"] = warning
    return out


# ---- evals ------------------------------------------------------------------------------------------------

def evals(src: GitSource) -> dict:
    latest, err = _json(src, "evals/agents/results/latest.json")
    golden = src.text("evals/agents/GOLDEN.json")
    membership = None
    if golden is not None:
        try:
            ids = json.loads(golden)
            ids = list(ids) if isinstance(ids, list) else list(ids.get("golden", []))
            membership = {"golden": len(ids), "diagnostic": sum(1 for i in ids if "-D-" in str(i))}
        except (json.JSONDecodeError, AttributeError) as e:
            return unavailable(f"evals/agents/GOLDEN.json unreadable: {e}")
    if latest is not None:
        return ok([{"results": latest}], results_committed=True, membership=membership)
    if membership is not None:
        return ok([], results_committed=False, membership=membership, note="no results committed")
    return unavailable("no evals/agents/results/latest.json and no evals/agents/GOLDEN.json at this commit")


# ---- bug log ----------------------------------------------------------------------------------------------

BUG_STATUSES = ("open", "fixed", "wontfix")


def _first_heading(text: str, fallback: str) -> str:
    m = re.search(r"^#{1,6}\s+(.+?)\s*$", text, re.M)
    return m.group(1) if m else fallback


def _line(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*(?:\*\*)?{key}:?(?:\*\*)?:?[ \t]*(.*?)\s*$", text, re.I | re.M)
    return m.group(1).strip().strip("*_ \t") if m else None


def _qa_notes(src: GitSource) -> list[dict]:
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
                          "text": f"signature {m.group(1)}: " + " ".join(blk.split("\n", 1)[1].split())})
    return items


def bug_log(src: GitSource) -> dict:
    items = []
    t = src.text("docs/bug-log.jsonl")
    if t is not None:
        for i, ln in enumerate(t.splitlines(), 1):
            if ln.strip():
                try:
                    items.append(json.loads(ln))
                except json.JSONDecodeError:
                    items.append({"error": f"docs/bug-log.jsonl line {i} is not valid JSON"})
    for p in src.glob("docs/bugs/*.md"):
        tx = src.text(p) or ""
        st = (_line(tx, "Status") or "").lower()
        items.append({"id": Path(p).stem, "path": p, "title": _first_heading(tx, Path(p).stem),
                      "status": st if st in BUG_STATUSES else "invalid",
                      "slice": _line(tx, "Slice") or None, "criterion": _line(tx, "Criterion") or None})
    items += _qa_notes(src)
    if not items:
        return unavailable("no entries in docs/bugs/*.md, docs/bug-log.jsonl or docs/slices/*/qa-notes.md at this commit")
    return ok(items)


# ---- dev journey ------------------------------------------------------------------------------------------

_VERIFIED = {"verified", "pass", "passed", "ok", "done", "green"}


def _count_verification(data) -> dict:
    if isinstance(data, dict) and isinstance(data.get("verified"), int) and isinstance(data.get("total"), int):
        return {"verified": data["verified"], "total": data["total"]}
    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for k in ("criteria", "items", "tasks", "checks"):
            if isinstance(data.get(k), list):
                rows = data[k]
                break
        if rows is None:
            rows = [{"verified": v} if isinstance(v, bool) else {"status": v} if isinstance(v, str) else v
                    for v in data.values() if isinstance(v, (bool, str, dict))]
    rows = rows or []
    n = sum(1 for r in rows if isinstance(r, dict) and (r.get("verified") is True or str(r.get("status", "")).lower() in _VERIFIED))
    return {"verified": n, "total": len(rows)}


def _events(text: str | None) -> list[dict]:
    out = []
    for ln in (text or "").splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                out.append({"error": "unparseable event line", "raw": ln[:200]})
    return out


def dev_journey(src: GitSource) -> dict:
    slices = sorted({p.split("/")[2] for p in src.paths() if p.startswith("docs/slices/") and p.count("/") >= 3})
    events = _events(src.text("ops/events.jsonl"))
    if not slices and not events:
        return unavailable("no docs/slices/ and no ops/events.jsonl at this commit")
    items = []
    for s in slices:
        base = f"docs/slices/{s}"
        row: dict = {"slice": s}
        tasks = src.text(f"{base}/tasks.md")
        if tasks is not None:
            done = len(re.findall(r"^\s*[-*]\s+\[[xX]\]", tasks, re.M))
            todo = len(re.findall(r"^\s*[-*]\s+\[ \]", tasks, re.M))
            row["tasks"] = {"done": done, "open": todo, "total": done + todo}
        else:
            row["tasks"] = {"available": False, "reason": f"{base}/tasks.md missing"}
        ver = src.text(f"{base}/verification.json")
        if ver is not None:
            try:
                row["verification"] = _count_verification(json.loads(ver))
            except json.JSONDecodeError as e:
                row["verification"] = {"available": False, "reason": f"verification.json invalid: {e}"}
        else:
            row["verification"] = {"available": False, "reason": f"{base}/verification.json missing"}
        am = src.text(f"{base}/amendments.md")
        row["amendments"] = (
            {"count": len(re.findall(r"^#{2,}\s+\S", am, re.M)) or len(re.findall(r"^\s*[-*]\s+\S", am, re.M)),
             "titles": re.findall(r"^#{2,}\s+(.+)$", am, re.M)}
            if am is not None else {"available": False, "reason": f"{base}/amendments.md missing"})
        items.append(row)
    return {"available": True, "summary": {"count": len(items), "slices": len(items), "events": len(events)},
            "items": items, "events": events}


# ---- git --------------------------------------------------------------------------------------------------

def git_history(src: GitSource) -> dict:
    rows = src.commits()
    return ok(rows) if rows else unavailable("no commits reachable from this sha")


# ---- human stops (historical part) -----------------------------------------------------------------------

_OPEN_ADR = ("proposed", "pending")


def hitl(src: GitSource) -> dict:
    items = []
    for it in (adrs(src).get("items") or []):
        word = re.sub(r"[*_`]", "", it.get("status") or "").strip().lower().split()
        if word and word[0].strip(".,:;()") in _OPEN_ADR:
            items.append({"kind": "adr", **it})
    cut = None
    cd = src.commit_date()
    if cd:
        try:
            cut = datetime.fromisoformat(cd.replace("Z", "+00:00"))
        except ValueError:
            cut = None
    for e in _events(src.text("ops/events.jsonl")):
        if e.get("stage") != "hitl":
            continue
        if cut is not None:
            try:
                at = datetime.fromisoformat(str(e.get("at")).replace("Z", "+00:00"))
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
                if at > cut:
                    continue
            except ValueError:
                pass
        items.append({"kind": "event", **e})
    if not items:
        return unavailable("no ADR with status Proposed or Pending in docs/adr/*.md and no stage-hitl event in ops/events.jsonl at this commit")
    return ok(items)


COLLECTORS = {
    "architecture": architecture, "research": research, "experiments": experiments, "adrs": adrs,
    "prd_journeys": prd_journeys, "evals": evals, "bug_log": bug_log, "dev_journey": dev_journey, "git": git_history,
    "hitl": hitl,
}


def collect_all(src: GitSource) -> dict[str, dict]:
    return {t: COLLECTORS[t](src) for t in TABS}
