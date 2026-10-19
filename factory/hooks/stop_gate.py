"""Stop gate (TB-09): refuse a 'done' from the implement agent that hides weakened tests or
skipped verification.

Contracts: ``docs/prds/TB-09-stop-gate.md``, ``docs/contracts/hook-io.md``,
``docs/contracts/profile.md`` and the TB-09 clauses of ``docs/contracts/clarifications.md``.
Deterministic: runs only ``git`` locally, no network, no model call. Nothing project-specific
is hard-coded; paths and the test command come from the profile.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from factory.hooks.core import Decision, HookConfig, Payload

ROLE = "implement"
CAP = 5
STATE_DIR = Path(".factory") / "state"
LOG_FILE = Path(".factory") / "stop_gate.log"
BASELINE_FILE = Path(".factory") / "baseline.json"
OWN_FILE = Path(".factory") / "own.json"
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
GIT_TIMEOUT = 60

# ---- markers (whole tokens, test files only: C-05, C-06) ---------------------------------------
_SKIP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("@pytest.mark.skip", re.compile(r"@pytest\.mark\.skip\b")),
    ("skipif", re.compile(r"(?<![\w])skipif\b")),
    ("xfail", re.compile(r"(?<![\w])xfail\b")),
    ("pytest.skip(", re.compile(r"(?<![\w])pytest\.skip\s*\(")),
    ("@unittest.skip", re.compile(r"@unittest\.skip(?:If|Unless)?\b")),
    ("it.skip", re.compile(r"(?<![\w])it\.skip\b")),
    ("test.skip", re.compile(r"(?<![\w])test\.skip\b")),
    ("xit", re.compile(r"(?<![\w.])xit\b")),
    ("xdescribe", re.compile(r"(?<![\w.])xdescribe\b")),
)
_TRIVIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("assert True", re.compile(r"(?<![\w.])assert\s+True\s*(?:$|[,;#)])")),
    ("assert 1", re.compile(r"(?<![\w.])assert\s+1\s*(?:$|[,;#)])")),
    ("assertTrue(True)", re.compile(r"(?<![\w])assertTrue\(\s*True\s*\)")),
    ("expect(true).toBe(true)", re.compile(r"(?<![\w])expect\(\s*true\s*\)\.toBe\(\s*true\s*\)")),
)
_PY_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_JS_TEST_CALL = re.compile(r"""^\s*(?:it|test)\s*\(\s*(['"`])(.*?)\1""")


def is_test_file(rel: str) -> bool:
    p = PurePosixPath(rel)
    if any(part in ("tests", "test", "__tests__") for part in p.parts[:-1]):
        return True
    name = p.name
    return bool(
        name.startswith("test_") and name.endswith(".py") or name.endswith("_test.py")
        or re.fullmatch(r".+\.(?:test|spec)\..+", name)
    )


# ---- globs: ``**`` and ``*`` only ----------------------------------------------------------------
def glob_to_regex(glob: str) -> re.Pattern[str]:
    g = glob[2:] if glob.startswith("./") else glob
    out: list[str] = []
    i = 0
    while i < len(g):
        if g.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif g.startswith("**", i):
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        elif g[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    return re.compile("".join(out) + r"\Z", re.DOTALL)


def _matches_any(rel: str, regexes: list[re.Pattern[str]]) -> bool:
    return any(r.match(rel) for r in regexes)


def _glob_prefix(glob: str) -> str:
    g = glob[2:] if glob.startswith("./") else glob
    parts: list[str] = []
    for comp in g.split("/"):
        if "*" in comp or "?" in comp:
            break
        parts.append(comp)
    return "/".join(parts)


def _files_matching(root: Path, globs: tuple[str, ...]) -> set[str]:
    regexes = [glob_to_regex(g) for g in globs]
    found: set[str] = set()
    for g in globs:
        start = root / _glob_prefix(g) if _glob_prefix(g) else root
        if start.is_file():
            candidates = [start]
        elif start.is_dir():
            candidates = []
            for dirpath, dirnames, filenames in os.walk(start):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                candidates.extend(Path(dirpath) / f for f in filenames)
        else:
            continue
        for c in candidates:
            if c.is_file():
                rel = c.relative_to(root).as_posix()
                if _matches_any(rel, regexes):
                    found.add(rel)
    return found


# ---- git change set -----------------------------------------------------------------------------
class ChangeSet:
    def __init__(self) -> None:
        self.paths: set[str] = set()
        self.added: dict[str, list[str]] = {}      # path -> added lines
        self.removed: dict[str, list[str]] = {}    # path -> removed lines
        self.deleted_files: set[str] = set()


class GitUnavailable(Exception):
    pass


def _git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in ("GIT_EXEC_PATH",)}
    try:
        proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, env=env,
                              timeout=GIT_TIMEOUT)
    except FileNotFoundError:
        raise GitUnavailable("no git executable") from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitUnavailable(f"git failed: {type(exc).__name__}") from None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitUnavailable(detail[0] if detail else f"git {args[0]} exited {proc.returncode}")
    return proc.stdout.decode("utf-8", "replace")


def _strip_prefix(p: str, prefix: str) -> str | None:
    if p == "/dev/null":
        return None
    p = p.split("\t", 1)[0]
    if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
        p = p[1:-1]
    return p[len(prefix):] if p.startswith(prefix) else p


def _header_path(rest: str) -> str:
    n = (len(rest) - 5) // 2
    if n > 0 and len(rest) == 2 * n + 5 and rest[2:2 + n] == rest[n + 5:]:
        return rest[2:2 + n]
    m = re.match(r"a/(.*) b/(.*)$", rest)
    return m.group(2) if m else rest


def parse_diff(text: str, cs: ChangeSet) -> None:
    path: str | None = None
    old: str | None = None
    deleted = False
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            path = _header_path(line[len("diff --git "):])
            old = path
            deleted = False
            in_hunk = False
            cs.paths.add(path)
            continue
        if in_hunk:
            if line.startswith("+"):
                cs.added.setdefault(path or "", []).append(line[1:])
            elif line.startswith("-"):
                cs.removed.setdefault(old or path or "", []).append(line[1:])
            continue
        if line.startswith("deleted file mode"):
            deleted = True
            if path:
                cs.deleted_files.add(path)
        elif line.startswith("--- "):
            o = _strip_prefix(line[4:], "a/")
            if o:
                old = o
        elif line.startswith("+++ "):
            n = _strip_prefix(line[4:], "b/")
            if n:
                path = n
                cs.paths.add(n)
            elif deleted and old:
                path = old
        elif line.startswith("rename to "):
            path = line[len("rename to "):]
            cs.paths.add(path)
        elif line.startswith("@@"):
            in_hunk = True


def compute_change_set(root: Path) -> ChangeSet:
    """Raises :class:`GitUnavailable` (C-07: no git, not a repository, or no HEAD commit)."""
    _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    cs = ChangeSet()
    parse_diff(_git(root, "-c", "core.quotepath=off", "diff", "HEAD", "--unified=0", "--relative"), cs)
    untracked = _git(root, "-c", "core.quotepath=off", "ls-files", "-z", "--others", "--exclude-standard")
    for rel in sorted(p for p in untracked.split("\0") if p):
        cs.paths.add(rel)
        try:
            data = (root / rel).read_bytes()
        except OSError:
            continue
        cs.added[rel] = data.decode("utf-8", "replace").splitlines()  # C-04: every line is added
    return cs


# ---- individual checks --------------------------------------------------------------------------
def check_markers(cs: ChangeSet) -> tuple[list[str], list[str]]:
    skips: list[str] = []
    trivial: list[str] = []
    for path in sorted(cs.added):
        if not is_test_file(path):
            continue
        s: set[str] = set()
        t: set[str] = set()
        for line in cs.added[path]:
            s.update(name for name, rx in _SKIP_PATTERNS if rx.search(line))
            t.update(name for name, rx in _TRIVIAL_PATTERNS if rx.search(line))
        if s:
            skips.append(f"{path} ({', '.join(sorted(s))})")
        if t:
            trivial.append(f"{path} ({', '.join(sorted(t))})")
    return skips, trivial


def _test_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        m = _PY_TEST_DEF.match(line)
        if m:
            names.add(m.group(1))
            continue
        m = _JS_TEST_CALL.match(line)
        if m:
            names.add(m.group(2))
    return names


def check_removed(cs: ChangeSet) -> list[str]:
    out: list[str] = []
    for path in sorted(cs.deleted_files):
        if is_test_file(path):
            out.append(f"{path} (file removed)")
    for path in sorted(cs.removed):
        if path in cs.deleted_files or not is_test_file(path):
            continue
        gone = _test_names(cs.removed[path]) - _test_names(cs.added.get(path, []))
        if gone:
            out.append(f"{path} ({', '.join(sorted(gone))})")
    return out


def check_frozen(cfg: HookConfig) -> list[str]:
    """Reasons for the frozen-file check (empty when frozen_tests is unset or all hashes match)."""
    if not cfg.frozen_tests:
        return []
    root = cfg.project_root
    manifest_path = root / BASELINE_FILE
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in manifest.items()
        ):
            raise ValueError("not an object mapping path to digest")
    except (OSError, ValueError) as exc:
        return [f"frozen tests cannot be verified: {BASELINE_FILE.as_posix()} is missing or invalid "
                f"({type(exc).__name__})"]
    regexes = [glob_to_regex(g) for g in cfg.frozen_tests]
    on_disk = _files_matching(root, cfg.frozen_tests)
    in_manifest = {k for k in manifest if _matches_any(k, regexes)}
    changed: list[str] = []
    unlisted: list[str] = []
    missing: list[str] = []
    for rel in sorted(on_disk | in_manifest):
        if rel not in manifest:
            unlisted.append(rel)
        elif rel not in on_disk:
            missing.append(rel)
        else:
            digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
            if digest.lower() != manifest[rel].strip().lower():
                changed.append(rel)
    out: list[str] = []
    if changed:
        out.append("frozen test changed from baseline: " + ", ".join(changed))
    if unlisted:
        out.append(f"frozen test missing from {BASELINE_FILE.as_posix()}: " + ", ".join(unlisted))
    if missing:
        out.append("frozen test missing on disk: " + ", ".join(missing))
    return out


def _log(root: Path, line: str) -> None:
    path = root / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line.replace("\n", " ") + "\n")


def _transcript_path(payload: Payload) -> str | None:
    if payload.event == "Stop":  # C-03
        tp = payload.raw.get("transcript_path")
        if isinstance(tp, str) and tp:
            return tp
    return payload.agent_transcript_path or None


def _tool_uses(obj: dict) -> list[dict]:
    content = None
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        content = msg["content"]
    elif isinstance(obj.get("content"), list):
        content = obj["content"]
    return [b for b in (content or []) if isinstance(b, dict) and b.get("type") == "tool_use"]


def check_transcript(payload: Payload, cfg: HookConfig, label: str) -> list[str]:
    """C-01, C-02, C-32: skipped when ``checks.test`` is unset; unreadable transcript is logged."""
    test_cmd = cfg.checks.test
    if not test_cmd:
        return []
    root = cfg.project_root
    tp = _transcript_path(payload)
    calls: list[tuple[str, str]] = []
    problem: str | None = None
    if not tp:
        problem = "no transcript path in payload"
    else:
        p = Path(tp)
        if not p.is_absolute():
            p = root / p
        try:
            text = p.read_text(encoding="utf-8")
            if not text.strip():
                raise ValueError("empty transcript")
            for line in text.splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("line is not a JSON object")
                for block in _tool_uses(obj):
                    name = block.get("name")
                    inp = block.get("input")
                    cmd = inp.get("command") if isinstance(inp, dict) else None
                    calls.append((name if isinstance(name, str) else "",
                                  cmd if isinstance(cmd, str) else ""))
        except (OSError, ValueError) as exc:
            problem = f"transcript {tp} unreadable ({type(exc).__name__}: {exc})"
    if problem is not None:
        _log(root, f"stop_gate agent={label}: check skipped: {problem}")
        return []
    last_edit = -1
    for i, (name, _cmd) in enumerate(calls):
        if name in EDIT_TOOLS:
            last_edit = i
    if last_edit < 0:
        return []
    for name, cmd in calls[last_edit + 1:]:
        if name == "Bash" and test_cmd in cmd:  # C-10: containment
            return []
    return [f"no full-suite run after the last edit: expected a Bash call containing "
            f"checks.test ({test_cmd!r}) after the last Edit or Write"]


def check_own(cs: ChangeSet, cfg: HookConfig) -> list[str]:
    path = cfg.project_root / OWN_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        globs = data["paths"] if isinstance(data, dict) else None
        if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
            raise ValueError("'paths' must be a list of globs")
    except (OSError, ValueError, KeyError) as exc:
        return [f"{OWN_FILE.as_posix()} is invalid ({type(exc).__name__}: {exc})"]
    regexes = [glob_to_regex(g) for g in globs]
    gate_files = {LOG_FILE.as_posix()}
    outside = sorted(
        p for p in cs.paths
        if not _matches_any(p, regexes) and p not in gate_files
        and not p.startswith(STATE_DIR.as_posix() + "/")
    )
    if not outside:
        return []
    return [f"change outside the paths in {OWN_FILE.as_posix()}: " + ", ".join(outside)]


# ---- counter ------------------------------------------------------------------------------------
def _label(payload: Payload) -> str:
    raw = payload.agent_id or "main"
    return re.sub(r"[^A-Za-z0-9._-]", "_", raw) or "main"


def _read_count(path: Path) -> int:
    try:
        n = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0
    return max(n, 0)


def gather_reasons(payload: Payload, cfg: HookConfig) -> list[str]:
    """Every failed check, in the stable order: git, markers, trivial assertions, removals,
    frozen files, test run evidence, ownership."""
    root = cfg.project_root
    reasons: list[str] = []
    cs: ChangeSet | None = None
    try:
        cs = compute_change_set(root)
    except GitUnavailable as exc:
        reasons.append(f"git unavailable, cannot compute the change set: {exc}")
    if cs is not None:
        skips, trivial = check_markers(cs)
        if skips:
            reasons.append("skip or expected-failure marker added: " + "; ".join(skips))
        if trivial:
            reasons.append("trivial assertion added: " + "; ".join(trivial))
        removed = check_removed(cs)
        if removed:
            reasons.append("test removed: " + "; ".join(removed))
    reasons.extend(check_frozen(cfg))
    reasons.extend(check_transcript(payload, cfg, _label(payload)))
    if cs is not None:
        reasons.extend(check_own(cs, cfg))
    return reasons


def decide(payload: Payload, cfg: HookConfig) -> Decision:
    if payload.event not in ("SubagentStop", "Stop"):
        return Decision("allow")
    if cfg.role_for(payload) != ROLE:
        return Decision("allow")
    root = cfg.project_root
    label = _label(payload)
    counter = root / STATE_DIR / f"stop_gate_{label}"
    reasons = gather_reasons(payload, cfg)
    if not reasons:
        try:
            counter.unlink()  # C-08: a clean stop resets the counter
        except FileNotFoundError:
            pass
        return Decision("allow")
    count = _read_count(counter)
    if count >= CAP:
        _log(root, f"stop_gate agent={label}: allowed after {CAP} blocks; unresolved: "
                   + " | ".join(reasons))
        return Decision("allow")
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(count + 1), encoding="utf-8")
    body = "\n".join(f"- {r}" for r in reasons)
    return Decision("block", f"stop gate: {len(reasons)} check(s) failed "
                             f"(block {count + 1} of {CAP}):\n{body}")
