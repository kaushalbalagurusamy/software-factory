"""Parse a slice directory into a structure the checker and gates can query."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SECTIONS = ["Why", "UX stories", "What Changes", "Out of scope", "Impact"]
PRIORITIES = ("P0", "P1", "P2", "P3")
STATUSES = ("draft", "approved", "in-progress", "implemented", "done", "blocked", "abandoned")
META_KEYS = ("id", "title", "priority", "depends_on", "status", "source_requirement_ids")

STORY_HEAD = re.compile(r"^### (US-\d+)\b.*$", re.M)
STORY_BODY = re.compile(r"\bAs an? .+? I can .+? so that\b", re.S)
STORY_CONTEXT = re.compile(r"^(Device|Context):\s*\S", re.M | re.I)
REQ_HEAD = re.compile(r"^### Requirement: (AC-\d+)\s+(\S.*)$", re.M)
SCN_HEAD = re.compile(r"^#### Scenario: (AC-\d+\.\d+)\s+(\S.*)$", re.M)
SERVES = re.compile(r"^Serves:\s*(US-\d+(?:\s*,\s*US-\d+)*)\s*$", re.M)
TASK = re.compile(r"^- \[( |x)\] (\d+\.\d+) (.*)$")
TASK_GROUP = re.compile(r"^## (\d+)\. \S")
CITE = re.compile(r"AC-\d+(?:\.\d+)?")
CITE_GROUP = re.compile(r"\((AC-\d+(?:\.\d+)?(?:\s*,\s*AC-\d+(?:\.\d+)?)*)\)")


def sha(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


@dataclass
class Task:
    id: str
    checked: bool
    text: str
    cites: list[str]
    line: int

    @property
    def sha(self) -> str:
        return sha(f"{self.id} {self.text}")


@dataclass
class Slice:
    path: Path
    meta: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    stories: dict[str, str] = field(default_factory=dict)
    reqs: dict[str, dict] = field(default_factory=dict)  # id -> {name, text, serves, scenarios{id:text}}
    tasks: list[Task] = field(default_factory=list)

    def items(self) -> dict[str, str]:
        """Lockable items: stories, requirements, scenarios, each with a content hash."""
        out = {k: sha(v) for k, v in self.stories.items()}
        for rid, r in self.reqs.items():
            out[rid] = sha(r["text"])
            for sid, st in r["scenarios"].items():
                out[sid] = sha(st)
        return out


def read_frontmatter(path: Path) -> tuple[dict, str, list[str]]:
    errs: list[str] = []
    if not path.is_file():
        return {}, "", [f"{path.name}: missing"]
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return {}, text, ["proposal.md: no YAML frontmatter"]
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        return {}, m.group(2), [f"proposal.md: frontmatter is not valid YAML: {exc}"]
    if not isinstance(meta, dict):
        return {}, m.group(2), ["proposal.md: frontmatter must be a mapping"]
    return meta, m.group(2), errs


def _h2(body: str) -> list[tuple[str, int]]:
    return [(m.group(1).strip(), m.start()) for m in re.finditer(r"^## (.+)$", body, re.M)]


def parse(path: Path) -> Slice:
    s = Slice(path=path)
    s.meta, body, errs = read_frontmatter(path / "proposal.md")
    s.errors += errs
    heads = _h2(body)
    s.sections = [h for h, _ in heads]
    for i, (h, pos) in enumerate(heads):
        if h == "UX stories":
            end = heads[i + 1][1] if i + 1 < len(heads) else len(body)
            block = body[pos:end]
            ms = list(STORY_HEAD.finditer(block))
            for j, m in enumerate(ms):
                e = ms[j + 1].start() if j + 1 < len(ms) else len(block)
                s.stories[m.group(1)] = block[m.start():e].strip()
    for spec in sorted((path / "specs").glob("*/spec.md")):
        _parse_spec(s, spec)
    tp = path / "tasks.md"
    if tp.is_file():
        for n, line in enumerate(tp.read_text(encoding="utf-8").splitlines()):
            m = TASK.match(line)
            if m:
                g = CITE_GROUP.search(m.group(3))
                s.tasks.append(Task(m.group(2), m.group(1) == "x", m.group(3),
                                    CITE.findall(g.group(1)) if g else [], n))
    return s


def _parse_spec(s: Slice, spec: Path) -> None:
    text = spec.read_text(encoding="utf-8")
    cap = spec.parent.name
    marks = sorted([(m.start(), "R", m) for m in REQ_HEAD.finditer(text)]
                   + [(m.start(), "S", m) for m in SCN_HEAD.finditer(text)]
                   + [(m.start(), "H", m) for m in re.finditer(r"^## .+$", text, re.M)],
                   key=lambda t: t[0])
    cur = None
    for i, (pos, kind, m) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        block = text[pos:end].strip()
        if kind == "R":
            rid = m.group(1)
            if rid in s.reqs:
                s.errors.append(f"{rid}: duplicate requirement id")
            serves = SERVES.search(block)
            cur = {"name": m.group(2), "text": block, "capability": cap, "scenarios": {},
                   "serves": re.findall(r"US-\d+", serves.group(1)) if serves else None}
            s.reqs[rid] = cur
        elif kind == "S":
            sid = m.group(1)
            if cur is None or not sid.startswith(next(k for k, v in s.reqs.items() if v is cur) + "."):
                s.errors.append(f"{cap}: scenario {sid} is not under its requirement")
                continue
            if any(sid in r["scenarios"] for r in s.reqs.values()):
                s.errors.append(f"{sid}: duplicate scenario id")
            cur["scenarios"][sid] = block
        else:
            cur = None
