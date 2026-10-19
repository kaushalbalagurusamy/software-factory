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
from pathlib import Path

COLLECTOR_VERSION = "1"
TABS = ("architecture", "research", "experiments", "adrs", "prd_journeys", "evals", "bug_log", "dev_journey", "git")


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
    paths = src.glob("experiments/*/results.json")
    if not paths:
        return unavailable("no experiments/*/results.json at this commit")
    items = []
    for p in paths:
        data, err = _json(src, p)
        items.append({"path": p, "name": p.split("/")[1], **({"error": err} if err else {"results": data})})
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


def prd_journeys(src: GitSource) -> dict:
    paths = src.glob("docs/slices/*/proposal.md")
    if not paths:
        return unavailable("no slices at this commit (docs/slices/*/proposal.md)")
    items = []
    for p in paths:
        t = src.text(p) or ""
        pri = re.search(r"^priority:\s*(\S+)", t, re.I | re.M) or re.search(r"\*\*Priority:?\*\*:?\s*(\S+)", t, re.I)
        items.append({"slice": p.split("/")[2], "path": p, "title": _title(t, p.split("/")[2]),
                      "priority": pri.group(1) if pri else None, "stories": _stories(t)})
    items.sort(key=lambda i: (str(i["priority"] or "~"), i["slice"]))
    return ok(items)


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
        st = re.search(r"\*\*Status:?\*\*:?\s*(.+)|^Status:\s*(.+)", tx, re.I | re.M)
        items.append({"path": p, "title": _title(tx, Path(p).stem),
                      "status": next((g.strip() for g in st.groups() if g), None) if st else None})
    if not items and t is None and not src.glob("docs/bugs/*.md"):
        return unavailable("no docs/bugs/*.md and no docs/bug-log.jsonl at this commit")
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


COLLECTORS = {
    "architecture": architecture, "research": research, "experiments": experiments, "adrs": adrs,
    "prd_journeys": prd_journeys, "evals": evals, "bug_log": bug_log, "dev_journey": dev_journey, "git": git_history,
}


def collect_all(src: GitSource) -> dict[str, dict]:
    return {t: COLLECTORS[t](src) for t in TABS}
