"""Shared harness for SFN-07 acceptance tests (eli12 docs). Everything runs in tmp dirs.

Finding codes are ASSUMED (see the clarification list in the hand-off report); change them here only.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "eli12-docs"
CLI = SKILL / "scripts" / "eli12.py"

C_MISSING = "missing-entry"
C_ORPHAN = "orphan-entry"
C_SIG = "stale-signature"
C_DEPS = "stale-dependencies"
C_TODO = "todo"
C_FORMAT = "format"
C_LONG = "too-long"
C_PARAM = "bad-param"
C_JARGON = "jargon"
C_UNPARSE = "unparseable"

FINDING_RE = re.compile(r"^(?P<path>[^:\n]+):(?P<line>\d+): (?P<code>[a-z][a-z0-9-]*): (?P<msg>.+)$")

UTIL = '''"""Utilities."""


def helper(x: int) -> int:
    return x + 1


def _private(x):
    return x


def ping() -> None:
    return None


class Box:
    def __init__(self, v: int):
        self.v = v

    def get(self) -> int:
        return helper(self.v)

    def _hidden(self):
        return 0
'''

CORE = '''import functools

from pkg import util
from pkg.util import helper


def run(n: int) -> int:
    box = util.Box(n)
    return helper(box.v)


def outer(n: int) -> int:
    return run(helper(n))


def unresolved(x):
    return mystery_call(x)


@functools.lru_cache(maxsize=None)
def cached(n: int) -> int:
    return n * 2


async def fetch(url: str) -> str:
    return url
'''


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def eli(*args: str, cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess:
    assert CLI.is_file(), "missing %s (a missing script also exits 2, so existence is asserted first)" % CLI
    return subprocess.run([sys.executable, str(CLI), *args], cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout)


def findings(proc: subprocess.CompletedProcess) -> list:
    out = []
    for ln in proc.stdout.splitlines():
        if ln.strip():
            m = FINDING_RE.match(ln)
            assert m, "not a `path:line: code: message` line: %r" % ln
            out.append(m.groupdict())
    return out


def codes(proc) -> list:
    return [f["code"] for f in findings(proc)]


def doc_path(root: Path, module: str) -> Path:
    return root / "docs" / "eli12" / (module + ".md")


def sections(text: str) -> dict:
    """name -> section text (from '## name' to the next '## ')."""
    parts = re.split(r"(?m)^## ", text)
    return {p.split("\n", 1)[0].strip(): "## " + p for p in parts[1:]}


def block(section: str, label: str) -> str:
    """Text of one labelled block, from its label to the next labelled line / hidden comment / end."""
    m = re.search(r"(?ms)^\*\*%s:\*\*(.*?)(?=^\*\*[A-Za-z ]+:\*\*|^<!--|\Z)" % re.escape(label), section)
    assert m, "label %r not found in section:\n%s" % (label, section)
    return m.group(0)


def edit_section(text: str, name: str, fn) -> str:
    secs = sections(text)
    assert name in secs, "section %r not in doc:\n%s" % (name, text)
    return text.replace(secs[name], fn(secs[name]), 1)


def fill_text(text: str) -> str:
    return text.replace("TODO", "a plain thing here")


def fill_all(root: Path) -> None:
    for p in (root / "docs" / "eli12").glob("*.md"):
        p.write_text(fill_text(p.read_text(encoding="utf-8")), encoding="utf-8")


def src_line(root: Path, rel: str, needle: str) -> int:
    for i, ln in enumerate((root / rel).read_text().splitlines(), 1):
        if needle in ln:
            return i
    raise AssertionError(needle)


def scaffold_all(root: Path, files=("pkg/util.py", "pkg/core.py")):
    p = eli("scaffold", "--root", str(root), *files, cwd=root)
    assert p.returncode == 0, p.stdout + p.stderr
    return p


def check(root: Path, *extra: str):
    return eli("check", "--root", str(root), *extra, cwd=root)


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    write(root, "pkg/util.py", UTIL)
    write(root, "pkg/core.py", CORE)
    return root


@pytest.fixture
def clean(proj):
    """Project with scaffolded + filled docs; asserts a clean check as the precondition."""
    scaffold_all(proj)
    fill_all(proj)
    p = check(proj)
    assert p.returncode == 0 and not p.stdout.strip(), p.stdout + p.stderr
    return proj
