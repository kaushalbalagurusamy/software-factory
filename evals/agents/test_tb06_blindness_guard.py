"""TB-06 implement blindness guard evals.

Sources: docs/prds/TB-06-blindness-guard.md (behaviours 1 to 7), R-11 in docs/factory/requirements.md,
docs/contracts/profile.md (`paths.eval`, `paths.held_out`), docs/contracts/hook-io.md (payload fields; main session
maps to main_session_role, default orchestrator). Profiles: base (eval evals/**, held_out tests/held_out/**) and
alt (eval qa/cases/**, qa/golden/**, held_out qa/secret/**).

Tokens in commands and paths: {ROOT} is replaced by the absolute project root.
"""
from __future__ import annotations

import builtins
import io
import os

import pytest

from evals.agents import lib

TB = "06"
HOOK = "factory.hooks.blindness_guard"
REQS = ("R-11",)
MARKER = "EVAL-CONTENT-MARKER-6d1f"


def case(cid: str, *values, reqs=REQS):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.param(*values, marks=pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs)), id=cid)


FILES = {
    "src/app.py": "print('app')\n",
    "src/util/helpers.py": "x = 1\n",
    "tests/unit/test_app.py": "def test_ok():\n    assert 1\n",
    "docs/readme.md": "readme\n",
    "evals_notes.md": "not an eval\n",
    "evals/case_a.py": f"# {MARKER}\n",
    "evals/sub/deep.py": f"# {MARKER}\n",
    "tests/held_out/h.py": f"# {MARKER}\n",
    "qa/cases/c.py": f"# {MARKER}\n",
    "qa/golden/g.py": f"# {MARKER}\n",
    "qa/secret/s.py": f"# {MARKER}\n",
    "qa/other/o.py": "x = 1\n",
}
SYMLINKS = {"src/alias": "evals", "peek.py": "evals/case_a.py"}


def _root(tmp_path, profile="base"):
    prof = profile if isinstance(profile, dict) else lib.profile_dict(profile)
    return lib.make_project(tmp_path, prof, files=FILES, symlinks=SYMLINKS)


def _sub(v, root):
    return v.replace("{ROOT}", str(root)) if isinstance(v, str) else v


def _run(tmp_path, profile, agent, tool, tool_input, cwd_sub=None):
    root = _root(tmp_path, profile)
    ti = {k: _sub(v, root) for k, v in tool_input.items()}
    pl = lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent)
    if cwd_sub:
        pl["cwd"] = str(root / cwd_sub)
    return lib.run_decide(HOOK, pl, root)


def _check(d, expected, clause):
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason, "a non-allow decision carries a reason (hook-io Decision)"


# ---------------------------------------------------------------- behaviour 3: Read

READ_CASES = [
    case("TB06-G-001", "base", "{ROOT}/evals/case_a.py", None, "deny", "B3 Read: deny a protected file_path (paths.eval)"),
    case("TB06-G-002", "base", "{ROOT}/src/app.py", None, "allow", "B5-style negative control: unprotected Read allowed"),
    case("TB06-G-004", "base", "{ROOT}/tests/held_out/h.py", None, "deny", "B2 held_out paths are protected"),
    case("TB06-D-001", "base", "evals/case_a.py", None, "deny", "B2 normalised against cwd (relative)"),
    case("TB06-D-002", "base", "{ROOT}/src/../evals/case_a.py", None, "deny", "B2 '..' collapsed"),
    case("TB06-D-003", "base", "{ROOT}/./evals/./case_a.py", None, "deny", "B2 '.' collapsed"),
    case("TB06-D-004", "base", "{ROOT}/src/alias/case_a.py", None, "deny", "B2 symlinks resolved when the path exists (dir link)"),
    case("TB06-D-005", "base", "{ROOT}/peek.py", None, "deny", "B2 symlinks resolved when the path exists (file link)"),
    case("TB06-D-006", "base", "{ROOT}/evals/sub/deep.py", None, "deny", "B2 lies under a protected glob"),
    case("TB06-D-007", "base", "../evals/case_a.py", "src", "deny", "B2 normalised against cwd (cwd=src, parent path)"),
    case("TB06-D-008", "base", "{ROOT}/evals/not_yet.py", None, "deny", "B2 match by glob even when the file does not exist"),
    case("TB06-D-009", "base", "{ROOT}/evals_notes.md", None, "allow", "B2 evals/** does not cover evals_notes.md"),
    case("TB06-D-010", "base", "{ROOT}/tests/unit/test_app.py", None, "allow", "B5 agent's own tests readable"),
    case("TB06-D-011", "base", "{ROOT}/docs/readme.md", None, "allow", "B5 other directories readable"),
    case("TB06-D-012", "alt", "{ROOT}/qa/cases/c.py", None, "deny", "B2 eval paths from profile (alt)"),
    case("TB06-D-013", "alt", "{ROOT}/qa/golden/g.py", None, "deny", "B2 every eval glob (alt)"),
    case("TB06-D-014", "alt", "{ROOT}/qa/secret/s.py", None, "deny", "B2 held_out from profile (alt)"),
    case("TB06-D-015", "alt", "{ROOT}/evals/case_a.py", None, "allow", "B2 evals/** not protected in alt"),
    case("TB06-D-016", "alt", "{ROOT}/qa/other/o.py", None, "allow", "B2 sibling of protected dirs not protected (alt)"),
    case("TB06-D-017", "base", "{ROOT}/tests/held_out/../held_out/h.py", None, "deny", "B2 '..' collapsed back into held_out"),
]


@pytest.mark.parametrize("profile,file_path,cwd_sub,expected,clause", READ_CASES)
def test_read(tmp_path, profile, file_path, cwd_sub, expected, clause):
    """TB-06 B2-B3: Read of a protected file_path by implement is denied; other reads are allowed."""
    d = _run(tmp_path, profile, "implement", "Read", {"file_path": file_path}, cwd_sub)
    _check(d, expected, clause)


# ---------------------------------------------------------------- behaviour 3: Grep and Glob

SEARCH_CASES = [
    case("TB06-G-003", "base", "Grep", {"pattern": "x", "path": "{ROOT}/evals"}, "deny", "B3 Grep: deny a protected path"),
    case("TB06-D-179", "base", "Grep", {"pattern": "x", "path": "{ROOT}/src"}, "allow", "B3/B5 Grep on a source dir allowed"),
    case("TB06-D-018", "base", "Grep", {"pattern": "x"}, "deny", "B3 deny a path that is missing"),
    case("TB06-D-019", "base", "Grep", {"pattern": "x", "path": "."}, "deny", "B3 deny a path that is '.'"),
    case("TB06-D-020", "base", "Grep", {"pattern": "x", "path": "{ROOT}"}, "deny", "B3 strict ancestor of a protected path"),
    case("TB06-D-021", "base", "Grep", {"pattern": "x", "path": "{ROOT}/tests"}, "deny", "B3 strict ancestor (tests of tests/held_out)"),
    case("TB06-D-022", "base", "Grep", {"pattern": "x", "path": "{ROOT}/tests/held_out"}, "deny", "B3 protected held_out path"),
    case("TB06-D-023", "base", "Grep", {"pattern": "x", "path": "{ROOT}/evals/case_a.py"}, "deny", "B3 protected file path"),
    case("TB06-D-024", "base", "Grep", {"pattern": "x", "path": "{ROOT}/src", "glob": "*.py"}, "allow", "B3 unprotected path and glob"),
    case("TB06-D-025", "base", "Grep", {"pattern": "x", "path": "{ROOT}/src", "glob": "../evals/**"}, "deny", "B3 deny a protected glob"),
    case("TB06-D-026", "base", "Grep", {"pattern": "x", "path": "{ROOT}/src/alias"}, "deny", "B2 symlink to evals resolved"),
    case("TB06-D-027", "base", "Grep", {"pattern": "x", "path": "{ROOT}/tests/unit"}, "allow", "B3 non-ancestor sibling allowed"),
    case("TB06-D-028", "alt", "Grep", {"pattern": "x", "path": "{ROOT}/qa"}, "deny", "B3 strict ancestor (alt)"),
    case("TB06-D-029", "alt", "Grep", {"pattern": "x", "path": "{ROOT}/qa/other"}, "allow", "B3 not an ancestor (alt)"),
    case("TB06-D-030", "alt", "Grep", {"pattern": "x", "path": "{ROOT}/tests"}, "allow", "B3 tests is no ancestor of a protected path in alt"),
    case("TB06-D-031", "base", "Grep", {"pattern": "x", "path": "src/../evals"}, "deny", "B2 normalised relative path"),
    case("TB06-D-032", "base", "Glob", {"pattern": "**/*.py"}, "deny", "B3 Glob with missing path"),
    case("TB06-D-033", "base", "Glob", {"pattern": "*.py", "path": "{ROOT}/evals"}, "deny", "B3 Glob protected path"),
    case("TB06-D-034", "base", "Glob", {"pattern": "*", "path": "."}, "deny", "B3 Glob path '.'"),
    case("TB06-D-035", "base", "Glob", {"pattern": "**/*.py", "path": "{ROOT}/src"}, "allow", "B3 Glob on a source dir"),
    case("TB06-D-036", "base", "Glob", {"pattern": "../evals/*", "path": "{ROOT}/src"}, "deny", "B3 protected glob via parent"),
    case("TB06-D-037", "base", "Glob", {"pattern": "*.py", "path": "{ROOT}/tests/unit"}, "allow", "B3 non-ancestor sibling"),
    case("TB06-D-038", "base", "Glob", {"pattern": "*", "path": "{ROOT}/tests"}, "deny", "B3 strict ancestor"),
    case("TB06-D-039", "alt", "Glob", {"pattern": "*", "path": "{ROOT}/qa/secret"}, "deny", "B3 held_out path (alt)"),
]


@pytest.mark.parametrize("profile,tool,tool_input,expected,clause", SEARCH_CASES)
def test_grep_glob(tmp_path, profile, tool, tool_input, expected, clause):
    """TB-06 B3: Grep and Glob deny a protected path or glob, and a path that is missing, '.', or a strict ancestor
    of a protected path."""
    d = _run(tmp_path, profile, "implement", tool, tool_input)
    _check(d, expected, clause)


# ---------------------------------------------------------------- behaviour 4: Bash

BASH_DENY = [
    # (a) names a protected path
    case("TB06-G-005", "base", "cat evals/case_a.py", None, "B4a names a protected path"),
    case("TB06-D-040", "base", "cat ./evals/case_a.py", None, "B4a relative form"),
    case("TB06-D-041", "base", "cat src/../evals/case_a.py", None, "B4a parent form"),
    case("TB06-D-042", "base", "cat 'evals/case_a.py'", None, "B4a single-quoted form"),
    case("TB06-D-043", "base", 'cat "evals/case_a.py"', None, "B4a double-quoted form"),
    case("TB06-D-044", "base", "cat {ROOT}/evals/case_a.py", None, "B4a absolute form"),
    case("TB06-D-045", "base", "cat ../evals/case_a.py", "src", "B4a parent (../) form against cwd"),
    case("TB06-D-046", "base", "ls ev*/", None, "B4a glob form ev*/"),
    case("TB06-D-047", "base", "cat e*/case_a.py", None, "B4a glob form that could expand to it"),
    case("TB06-D-048", "base", "cat **/evals/*.py", None, "B4a glob form **/evals"),
    case("TB06-D-049", "base", "cat $PWD/evals/case_a.py", None, "B4a $VAR form"),
    case("TB06-D-050", "base", "cat ${PWD}/evals/case_a.py", None, "B4a ${VAR} form"),
    case("TB06-D-051", "base", "cat ~+/evals/case_a.py", None, "B4a tilde form that expands to cwd"),
    case("TB06-D-052", "base", "D=evals; cat $D/case_a.py", None, "B4a names a protected path in an argument"),
    case("TB06-D-053", "base", 'cat "ev"als/case_a.py', None, "B4a quoted form (shell quote concatenation)"),
    case("TB06-D-054", "base", "cat eval\\s/case_a.py", None, "B4a quoted form (backslash escape)"),
    case("TB06-D-055", "base", "cat tests/held_out/h.py", None, "B4a held_out path"),
    case("TB06-D-056", "base", "head -n 3 evals/case_a.py", None, "B4a head"),
    case("TB06-D-057", "base", "tail evals/case_a.py", None, "B4a tail"),
    case("TB06-D-058", "base", "less evals/case_a.py", None, "B4a less"),
    case("TB06-D-059", "base", "grep x evals/case_a.py", None, "B4a grep on a protected file"),
    case("TB06-D-060", "base", "rg x evals", None, "B4a rg on a protected dir"),
    case("TB06-D-061", "base", "find evals -name '*.py'", None, "B4a find on a protected dir"),
    case("TB06-D-062", "base", "ls evals", None, "B4a ls of a protected dir"),
    case("TB06-D-063", "base", "ls -la tests/held_out", None, "B4a ls of held_out"),
    case("TB06-D-064", "base", "tree evals", None, "B4a tree of a protected dir"),
    case("TB06-D-065", "base", "du -a evals", None, "B4a du of a protected dir"),
    case("TB06-D-066", "base", "fd py evals", None, "B4a fd on a protected dir"),
    case("TB06-D-067", "base", "ag x evals", None, "B4a ag on a protected dir"),
    case("TB06-D-068", "base", "cp evals/case_a.py /tmp/leak.py", None, "B4a names a protected path"),
    case("TB06-D-069", "base", "tar czf /tmp/e.tgz evals", None, "B4a names a protected path"),
    case("TB06-D-070", "base", "echo evals/case_a.py | xargs cat", None, "B4a names a protected path (xargs, R-11)"),
    case("TB06-D-071", "base", "git show HEAD:evals/case_a.py", None, "B4a argument references a protected path"),
    case("TB06-D-072", "base", "git log -p -- evals", None, "B4a names a protected path"),
    case("TB06-D-073", "base", "git diff HEAD -- evals/", None, "B4a names a protected path"),
    case("TB06-D-074", "base", "cat src/app.py evals/case_a.py", None, "B4a any argument"),
    case("TB06-D-075", "base", "grep -r x src evals", None, "B4a any argument"),
    case("TB06-D-076", "base", "ln -s ../evals src/e", None, "B4a names a protected path"),
    case("TB06-D-077", "base", "cat src/alias/case_a.py", None, "B2 symlink (dir) resolved"),
    case("TB06-D-078", "base", "cat peek.py", None, "B2 symlink (file) resolved"),
    case("TB06-D-079", "base", "ls src/alias", None, "B2 symlink (dir) resolved"),
    case("TB06-D-080", "base", "make build && cat evals/case_a.py", None, "B4a any segment"),
    case("TB06-D-081", "alt", "cat qa/cases/c.py", None, "B4a eval path (alt)"),
    case("TB06-D-082", "alt", "cat qa/secret/s.py", None, "B4a held_out path (alt)"),
    case("TB06-D-083", "alt", "head qa/golden/g.py", None, "B4a eval path (alt)"),
    # (b) recursive search or listing on '.', no path or a strict ancestor
    case("TB06-G-006", "base", "grep -r TODO .", None, "B4b grep -r on '.'"),
    case("TB06-D-084", "base", "grep -r TODO", None, "B4b grep -r with no path"),
    case("TB06-D-085", "base", "grep -rn TODO tests", None, "B4b strict ancestor"),
    case("TB06-D-086", "base", "grep -R TODO .", None, "B4b grep -R"),
    case("TB06-D-087", "base", "grep --recursive TODO .", None, "B4b grep --recursive"),
    case("TB06-D-088", "base", "rg TODO", None, "B4b rg with no path"),
    case("TB06-D-089", "base", "rg TODO .", None, "B4b rg on '.'"),
    case("TB06-D-090", "base", "rg TODO {ROOT}", None, "B4b rg on the root (strict ancestor)"),
    case("TB06-D-091", "base", "find .", None, "B4b find on '.'"),
    case("TB06-D-092", "base", "find . -name '*.py'", None, "B4b find on '.'"),
    case("TB06-D-093", "base", "find", None, "B4b find with no path"),
    case("TB06-D-094", "base", "find ..", "src", "B4b find on a strict ancestor (cwd=src)"),
    case("TB06-D-095", "base", "ls -R", None, "B4b ls -R with no path"),
    case("TB06-D-096", "base", "ls -R .", None, "B4b ls -R on '.'"),
    case("TB06-D-097", "base", "ls -lR", None, "B4b ls -R combined flags"),
    case("TB06-D-098", "base", "tree", None, "B4b tree with no path"),
    case("TB06-D-099", "base", "tree .", None, "B4b tree on '.'"),
    case("TB06-D-100", "base", "du -a", None, "B4b du with no path"),
    case("TB06-D-101", "base", "du -a .", None, "B4b du on '.'"),
    case("TB06-D-102", "base", "fd py", None, "B4b fd with no path"),
    case("TB06-D-103", "base", "ag TODO", None, "B4b ag with no path"),
    case("TB06-D-104", "alt", "grep -r x qa", None, "B4b strict ancestor (alt)"),
    # (c) test runners on a protected path
    case("TB06-G-007", "base", "pytest evals", None, "B4c pytest on a protected path"),
    case("TB06-D-105", "base", "pytest evals/case_a.py", None, "B4c pytest on a protected file"),
    case("TB06-D-106", "base", "python -m pytest tests/held_out", None, "B4c python -m pytest"),
    case("TB06-D-107", "base", "python -m unittest discover -s evals", None, "B4c unittest"),
    case("TB06-D-108", "base", "node --test evals/", None, "B4c node --test"),
    case("TB06-D-109", "base", "pytest -q -k foo tests/held_out", None, "B4c pytest with options"),
    case("TB06-D-110", "alt", "pytest qa/cases", None, "B4c protected path (alt)"),
    # (d) interpreter one-liners
    case("TB06-G-008", "base", "python -c \"print(open('evals/case_a.py').read())\"", None, "B4d python -c names a protected path"),
    case("TB06-D-111", "base", "python3 -c \"print(open('evals/case_a.py').read())\"", None, "B4d python one-liner (python3)"),
    case("TB06-D-112", "base", "node -e \"console.log(require('fs').readFileSync('evals/case_a.py','utf8'))\"", None, "B4d node -e"),
    case("TB06-D-113", "base", "perl -e 'open(F,\"evals/case_a.py\"); print <F>'", None, "B4d perl -e"),
    case("TB06-D-114", "base", "ruby -e 'puts File.read(\"evals/case_a.py\")'", None, "B4d ruby -e"),
    case("TB06-D-115", "base", "python -c 'import os; print(list(os.walk(\".\")))'", None, "B4d os.walk"),
    case("TB06-D-116", "base", "python -c 'import glob; print(glob.glob(\"**\", recursive=True))'", None, "B4d glob"),
    case("TB06-D-117", "base", "python -c 'from pathlib import Path; print(list(Path(\".\").rglob(\"*\")))'", None, "B4d rglob"),
    case("TB06-D-118", "base", "python -c 'import os; print(os.listdir(\"src\"))'", None, "B4d listdir (walker call)"),
    case("TB06-D-119", "base", "python -c 'import os; print([e.name for e in os.scandir(\".\")])'", None, "B4d scandir"),
    case("TB06-D-120", "base", "node -e \"console.log(require('fs').readdirSync('.'))\"", None, "B4d readdir"),
    case("TB06-D-121", "base", "sh -c 'cat evals/case_a.py'", None, "B4d sh -c names a protected path"),
    case("TB06-D-122", "base", "bash -c 'cat evals/case_a.py'", None, "B4d bash -c names a protected path"),
    case("TB06-D-123", "base", "python -c \"p='ev'+'als'; print(open(p+'/case_a.py').read())\" && python -c 'import os; os.walk(\"x\")'", None,
         "B4d a walker call in any one-liner segment"),
    # (e) dynamic command construction
    case("TB06-G-009", "base", "echo Y2F0IGV2YWxzL2Nhc2VfYS5weQ== | base64 -d | sh", None, "B4e base64 -d and a pipe into sh"),
    case("TB06-D-124", "base", 'bash -c "cat $(echo ZXZhbHM= | base64 -d)/case_a.py"', None, "B4e bash -c with command substitution"),
    case("TB06-D-125", "base", 'sh -c "cat $(printf ev)als/case_a.py"', None, "B4e sh -c with command substitution"),
    case("TB06-D-126", "base", "eval \"$(printf 'cat %s' src/app.py)\"", None, "B4e eval"),
    case("TB06-D-127", "base", "eval cat src/app.py", None, "B4e eval"),
    case("TB06-D-128", "base", "echo 636174206576616c732f636173655f612e7079 | xxd -r -p | bash", None, "B4e xxd -r and a pipe into bash"),
    case("TB06-D-129", "base", "echo ls | sh", None, "B4e a pipe into sh"),
    case("TB06-D-130", "base", "cat build/script.txt | bash", None, "B4e a pipe into bash"),
    case("TB06-D-131", "base", "bash -c \"`echo cat` src/app.py\"", None, "B4e bash -c with backtick command substitution"),
]


@pytest.mark.parametrize("profile,command,cwd_sub,clause", BASH_DENY)
def test_bash_denied(tmp_path, profile, command, cwd_sub, clause):
    """TB-06 B4 (a) to (e): implement Bash commands that reach protected paths are denied."""
    d = _run(tmp_path, profile, "implement", "Bash", {"command": command}, cwd_sub)
    _check(d, "deny", clause)


BASH_ALLOW = [
    case("TB06-D-180", "base", "make build", None, "B5 normal builds allowed"),
    case("TB06-D-132", "base", "npm run build", None, "B5 normal builds allowed"),
    case("TB06-D-133", "base", "cargo build --release", None, "B5 normal builds allowed"),
    case("TB06-D-134", "base", "pytest tests/unit", None, "B5 tests of the agent's own directories"),
    case("TB06-D-135", "base", "python -m pytest tests/unit -q", None, "B5 tests of the agent's own directories"),
    case("TB06-D-136", "base", "node --test src/", None, "B5 tests of own directories"),
    case("TB06-D-137", "base", "git diff src/app.py", None, "B5 git diff of its own files"),
    case("TB06-D-138", "base", "git log --oneline -5 -- src", None, "B5 no protected path"),
    case("TB06-D-139", "base", "ls src", None, "B5 ls src"),
    case("TB06-D-140", "base", "ls", None, "B4b lists only recursive listings; plain ls is not one"),
    case("TB06-D-141", "base", "ls -la", None, "B4b plain ls -la is not recursive"),
    case("TB06-D-142", "base", "cat src/app.py", None, "B5 reads of other directories"),
    case("TB06-D-143", "base", "cat docs/readme.md", None, "B5 reads of other directories"),
    case("TB06-D-144", "base", "grep -r TODO src", None, "B4b recursive search on a source dir is fine"),
    case("TB06-D-145", "base", "rg TODO src", None, "B4b rg on a source dir"),
    case("TB06-D-146", "base", "find src -name '*.py'", None, "B4b find on a source dir"),
    case("TB06-D-147", "base", "ls -R src", None, "B4b ls -R on a source dir"),
    case("TB06-D-148", "base", "tree src", None, "B4b tree on a source dir"),
    case("TB06-D-149", "base", "du -sh src", None, "B4b du on a source dir"),
    case("TB06-D-150", "base", "fd py src", None, "B4b fd on a source dir"),
    case("TB06-D-151", "base", "python src/app.py", None, "B5 no protected path (script run is the documented residual gap, B7)"),
    case("TB06-D-152", "base", "python -c 'print(1 + 1)'", None, "B4d only one-liners naming protected paths or walkers"),
    case("TB06-D-153", "base", "echo hello", None, "B5 no protected path"),
    case("TB06-D-154", "base", "cat evals_notes.md", None, "B2 evals_notes.md is not under evals/"),
    case("TB06-D-155", "base", "bash -c 'ls src'", None, "B4d/e bash -c without protected path, walker or substitution"),
    case("TB06-D-156", "base", "grep -rn TODO tests/unit", None, "B4b tests/unit is no ancestor of tests/held_out"),
    case("TB06-D-157", "alt", "cat evals/case_a.py", None, "B2 evals/** not protected in alt"),
    case("TB06-D-158", "alt", "grep -r x tests", None, "B4b tests is no ancestor of a protected path in alt"),
    case("TB06-D-159", "alt", "grep -r x qa/other", None, "B4b qa/other is not an ancestor (alt)"),
    case("TB06-D-160", "alt", "pytest evals", None, "B4c evals is not protected in alt"),
]


@pytest.mark.parametrize("profile,command,cwd_sub,clause", BASH_ALLOW)
def test_bash_allowed(tmp_path, profile, command, cwd_sub, clause):
    """TB-06 B5: 'Bash commands that reference no protected path and do not fall under (b) to (e) are allowed,
    including normal builds, tests of the agent's own directories, git diff of its own files and ls src.'"""
    d = _run(tmp_path, profile, "implement", "Bash", {"command": command}, cwd_sub)
    _check(d, "allow", clause)


# ---------------------------------------------------------------- behaviour 1: other roles unaffected

OTHER_ROLES = [
    case("TB06-G-010", "test", "Read", {"file_path": "{ROOT}/evals/case_a.py"}, "B1 every other role always gets allow (test reads evals)"),
    case("TB06-D-161", "orchestrator", "Read", {"file_path": "{ROOT}/evals/case_a.py"}, "B1 orchestrator unaffected"),
    case("TB06-D-162", None, "Read", {"file_path": "{ROOT}/tests/held_out/h.py"}, "B1 main session (orchestrator by default) unaffected"),
    case("TB06-D-163", "review", "Grep", {"pattern": "x", "path": "."}, "B1 review unaffected"),
    case("TB06-D-164", "test", "Bash", {"command": "pytest evals"}, "B1 test runs the evals"),
    case("TB06-D-165", "research", "Bash", {"command": "cat evals/case_a.py"}, "B1 research unaffected"),
    case("TB06-D-166", "audit", "Bash", {"command": "grep -r x ."}, "B1 audit unaffected"),
    case("TB06-D-167", "design", "Glob", {"pattern": "**/*.py"}, "B1 design unaffected"),
    case("TB06-D-168", "review", "Bash", {"command": "python -c 'import os; print(list(os.walk(\".\")))'"}, "B1 review unaffected"),
    case("TB06-D-169", "test", "Bash", {"command": "echo Y2F0IGV2YWxzL2Nhc2VfYS5weQ== | base64 -d | sh"}, "B1 test unaffected by (e)"),
]


@pytest.mark.parametrize("agent,tool,tool_input,clause", OTHER_ROLES)
def test_other_roles_unaffected(tmp_path, agent, tool, tool_input, clause):
    """TB-06 B1: 'Applies only when the resolved role is implement; every other role always gets allow.'"""
    d = _run(tmp_path, "base", agent, tool, tool_input)
    _check(d, "allow", clause)


def test_main_session_implement_is_blind(tmp_path):
    """TB-06 B1 + hook-io: the main session resolves to main_session_role; if that is implement the guard applies."""
    prof = lib.profile_dict("base", main_session_role="implement")
    d = _run(tmp_path, prof, None, "Read", {"file_path": "{ROOT}/evals/case_a.py"})
    _check(d, "deny", "B1 resolved role implement")


test_main_session_implement_is_blind = pytest.mark.case("TB06-D-170", tier="diagnostic", tb=TB, reqs=list(REQS))(
    test_main_session_implement_is_blind)


# ---------------------------------------------------------------- behaviour 6: reasons and never opening a protected file

@pytest.mark.parametrize("tool,tool_input", [
    case("TB06-D-171", "Read", {"file_path": "{ROOT}/evals/case_a.py"}),
    case("TB06-D-172", "Bash", {"command": "cat evals/case_a.py"}),
    case("TB06-D-173", "Grep", {"pattern": "x", "path": "{ROOT}/tests/held_out"}),
])
def test_reason_says_protected_without_contents(tmp_path, tool, tool_input):
    """TB-06 B6: 'Deny reasons state that the path is protected without echoing eval file contents'."""
    d = _run(tmp_path, "base", "implement", tool, tool_input)
    assert d.kind == "deny"
    assert "protected" in d.reason.lower()
    assert MARKER not in d.reason


@pytest.mark.parametrize("tool,tool_input", [
    case("TB06-D-174", "Read", {"file_path": "{ROOT}/evals/case_a.py"}),
    case("TB06-D-175", "Bash", {"command": "cat evals/case_a.py tests/held_out/h.py"}),
    case("TB06-D-176", "Grep", {"pattern": "x", "path": "{ROOT}/evals"}),
    case("TB06-D-177", "Read", {"file_path": "{ROOT}/peek.py"}),
])
def test_hook_never_opens_protected_file(tmp_path, monkeypatch, tool, tool_input):
    """TB-06 B6: 'the hook never opens a protected file.' Every open of a file under a protected directory during
    the decision is recorded; there must be none."""
    root = _root(tmp_path)
    protected = [str((root / "evals").resolve()), str((root / "tests/held_out").resolve())]
    opened = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def _note(p):
        try:
            s = os.path.realpath(os.fspath(p))
        except TypeError:
            return
        if any(s == d or s.startswith(d + os.sep) for d in protected):
            opened.append(s)

    def fake_open(file, *a, **k):
        if not isinstance(file, int):
            _note(file)
        return real_open(file, *a, **k)

    def fake_io_open(file, *a, **k):
        if not isinstance(file, int):
            _note(file)
        return real_io_open(file, *a, **k)

    def fake_os_open(path, *a, **k):
        _note(path)
        return real_os_open(path, *a, **k)

    ti = {k: _sub(v, root) for k, v in tool_input.items()}
    pl = lib.payload(root, tool_name=tool, tool_input=ti, agent_type="implement")
    # load the implementation before patching so imports are not counted
    lib.need("factory.hooks.core", "parse_payload", "HookConfig")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(io, "open", fake_io_open)
    monkeypatch.setattr(os, "open", fake_os_open)
    d = lib.run_decide(HOOK, pl, root)
    monkeypatch.undo()
    assert d.kind == "deny"
    assert opened == []


# ---------------------------------------------------------------- command line

def test_cli_blindness_guard(tmp_path):
    """hook-io adapter + TB-06 B3: implement Read of an eval file via `python -m factory.hooks blindness_guard` exits 2
    with a reason on stderr that does not echo the file contents; a source read exits 0."""
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    root = _root(tmp_path)
    bad = lib.run_cli("blindness_guard", lib.payload(root, tool_name="Read",
                                                     tool_input={"file_path": str(root / "evals/case_a.py")},
                                                     agent_type="implement"), root)
    ok = lib.run_cli("blindness_guard", lib.payload(root, tool_name="Read",
                                                    tool_input={"file_path": str(root / "src/app.py")},
                                                    agent_type="implement"), root)
    assert bad.returncode == 2 and bad.stderr.strip() and MARKER not in bad.stderr + bad.stdout
    assert ok.returncode == 0 and ok.stdout.strip() == ""


test_cli_blindness_guard = pytest.mark.case("TB06-D-178", tier="diagnostic", tb=TB, reqs=list(REQS))(test_cli_blindness_guard)



# ================================================================ clarifications (docs/contracts/clarifications.md)

CLAR_BASH = [
    # [A-06-1] bare test runners
    case("TB06-D-182", "base", "pytest", None, "deny", "[A-06-1] bare pytest is denied for blind roles"),
    case("TB06-D-183", "base", "python -m pytest", None, "deny", "[A-06-1] bare python -m pytest is denied"),
    case("TB06-D-184", "base", "pytest -q -x", None, "deny", "[A-06-1] options only, no path argument"),
    case("TB06-D-185", "base", "pytest tests", None, "deny", "[A-06-1] a path that is an ancestor of a protected path"),
    case("TB06-D-186", "base", "pytest src tests/unit", None, "allow", "[A-06-1] path arguments neither protected nor ancestors"),
    # [A-06-4] $VAR rule
    case("TB06-D-187", "base", "cat $X/notes.md", None, "allow", "[A-06-4] unresolved $VAR, remainder not protected, not PWD/OLDPWD/HOME"),
    case("TB06-D-188", "base", "cat $X/evals/case_a.py", None, "deny", "[A-06-4] remainder names a protected fragment"),
    case("TB06-D-189", "base", "cat $HOME/anything.txt", None, "deny", "[A-06-4] variable is HOME"),
    case("TB06-D-190", "base", "cat $OLDPWD/anything.txt", None, "deny", "[A-06-4] variable is OLDPWD"),
    case("TB06-D-191", "base", "X=src; cat $X/app.py", None, "allow", "[A-06-4] variable assigned in the same command is expanded first"),
    case("TB06-D-192", "base", "X=tests/held_out; cat $X/h.py", None, "deny", "[A-06-4] expanded assignment lands in held_out"),
    # [A-06-3] tilde forms that do not depend on HOME
    case("TB06-D-193", "base", "cat ~-/evals/case_a.py", None, "deny", "[A-06-3] ~- unresolvable, remainder protected"),
    case("TB06-D-194", "base", "cat ~bob/evals/case_a.py", None, "deny", "[A-06-3] ~user unresolvable, remainder protected"),
    case("TB06-D-195", "base", "cat ~bob/notes.md", None, "allow", "[A-06-3] ~user with an unprotected, resolvable remainder"),
    # [A-06-5]
    case("TB06-D-196", "base", "base64 -d build/blob.b64 > build/blob.bin", None, "deny", "[A-06-5] standalone base64 -d is denied"),
    case("TB06-D-197", "base", "base64 --decode build/blob.b64", None, "deny", "[A-06-5] base64 decode (long option)"),
    # [A-06-6] git pathspec rule
    case("TB06-D-198", "base", "git status", None, "allow", "[A-06-6] git status allowed"),
    case("TB06-D-199", "base", "git diff", None, "allow", "[A-06-6] git diff allowed"),
    case("TB06-D-200", "base", "git log", None, "deny", "[A-06-6] git log without a pathspec after --"),
    case("TB06-D-201", "base", "git log -p -- src", None, "allow", "[A-06-6] git log with an unprotected pathspec after --"),
    case("TB06-D-202", "base", "git show HEAD", None, "deny", "[A-06-6] git show without a pathspec"),
    case("TB06-D-203", "base", "git show HEAD -- src/app.py", None, "allow", "[A-06-6] git show with an unprotected pathspec"),
    case("TB06-D-204", "base", "git blame src/app.py", None, "deny", "[A-06-6] git blame without -- pathspec"),
    case("TB06-D-205", "base", "git blame -- src/app.py", None, "allow", "[A-06-6] git blame with an unprotected pathspec"),
    case("TB06-D-206", "base", "git grep TODO", None, "deny", "[A-06-6] git grep without a pathspec"),
    case("TB06-D-207", "base", "git grep TODO -- src", None, "allow", "[A-06-6] git grep with an unprotected pathspec"),
    case("TB06-D-208", "base", "git ls-files", None, "deny", "[A-06-6] git ls-files"),
    case("TB06-D-209", "base", "git ls-tree -r HEAD", None, "deny", "[A-06-6] git ls-tree"),
    case("TB06-D-210", "base", "git cat-file -p HEAD:src/app.py", None, "deny", "[A-06-6] git cat-file"),
    case("TB06-D-211", "base", "git archive HEAD", None, "deny", "[A-06-6] git archive"),
    case("TB06-D-212", "base", "git log -- evals", None, "deny", "[A-06-6] pathspec after -- is protected"),
    case("TB06-D-213", "base", "git grep TODO -- tests", None, "deny", "[U-1] pathspec is an ancestor of a protected path"),
    case("TB06-D-214", "alt", "git ls-files -- qa/cases", None, "deny", "[A-06-6] protected pathspec (alt)"),
    case("TB06-D-225", "base", "git ls-files -- tests", None, "deny", "[U-1] ancestor pathspec"),
    case("TB06-D-226", "base", "git log -- src tests", None, "deny", "[U-1] every pathspec must be clean"),
    case("TB06-D-227", "base", "git log -- src docs", None, "allow", "[U-1] all pathspecs neither protected nor ancestors"),
    case("TB06-D-228", "alt", "git grep x -- qa", None, "deny", "[U-1] ancestor pathspec (alt)"),
    case("TB06-D-229", "alt", "git grep x -- tests", None, "allow", "[U-1] tests is no ancestor in alt"),
    # [U-2] unresolved $VAR prefix
    case("TB06-D-230", "base", "cat $X/case_a.py", None, "allow", "[U-2] a bare file name alone does not deny"),
    case("TB06-D-231", "base", "cat $X/held_out/h.py", None, "deny", "[U-2] remainder names a protected directory segment (held_out)"),
    case("TB06-D-232", "alt", "cat $X/qa/cases/c.py", None, "deny", "[U-2] remainder contains a protected glob match"),
    case("TB06-D-233", "base", "cat ${X}/evals", None, "deny", "[U-2] remainder names the evals segment"),
    case("TB06-D-215", "alt", "git ls-files -- evals", None, "allow", "[A-06-6] evals is not protected in alt"),
]


@pytest.mark.parametrize("profile,command,cwd_sub,expected,clause", CLAR_BASH)
def test_bash_clarified(tmp_path, profile, command, cwd_sub, expected, clause):
    """clarifications [A-06-1], [A-06-3], [A-06-4], [A-06-5], [A-06-6] for implement Bash (clause per case)."""
    d = _run(tmp_path, profile, "implement", "Bash", {"command": command}, cwd_sub)
    _check(d, expected, clause)


@pytest.mark.parametrize("file_path,expected,clause", [
    case("TB06-D-216", "{ROOT}/evals", "deny", "[A-06-2] evals/** also matches the directory evals itself"),
    case("TB06-D-217", "{ROOT}/tests/held_out", "deny", "[A-06-2] held_out glob matches its directory"),
    case("TB06-D-218", "{ROOT}/tests", "allow", "[A-06-2] an ancestor is not matched by the glob for Read"),
])
def test_read_protected_directory(tmp_path, file_path, expected, clause):
    """clarifications [A-06-2]: 'A protected glob such as evals/** also matches the directory evals itself.'"""
    _check(_run(tmp_path, "base", "implement", "Read", {"file_path": file_path}), expected, clause)


@pytest.mark.parametrize("home,command,expected,clause", [
    case("TB06-D-219", "ROOT", "cat ~/evals/case_a.py", "deny", "[A-06-3] ~ expands to $HOME (HOME = project root)"),
    case("TB06-D-220", "ELSEWHERE", "cat ~/evals/case_a.py", "allow", "[A-06-3] ~ expands to $HOME (HOME elsewhere)"),
    case("TB06-D-221", "ROOT", "ls ~/tests/held_out", "deny", "[A-06-3] ~ expands to $HOME (held_out)"),
])
def test_tilde_home(tmp_path, monkeypatch, home, command, expected, clause):
    """clarifications [A-06-3]: '~ expands to $HOME'."""
    root = _root(tmp_path)
    elsewhere = tmp_path / "home_elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("HOME", str(root) if home == "ROOT" else str(elsewhere))
    d = lib.run_decide(HOOK, lib.payload(root, tool_name="Bash", tool_input={"command": command}, agent_type="implement"), root)
    _check(d, expected, clause)


@pytest.mark.parametrize("tool,tool_input,expected,clause", [
    case("TB06-D-222", "Read", {"file_path": "{ROOT}/evals/case_a.py"}, "deny", "[A-06-7] unknown agent_type is blind"),
    case("TB06-D-223", "Bash", {"command": "grep -r TODO ."}, "deny", "[A-06-7] unknown agent_type is blind (B4b)"),
    case("TB06-D-224", "Grep", {"pattern": "x", "path": "{ROOT}/src"}, "allow", "[A-06-7] blind role may still search src"),
])
def test_unknown_agent_is_blind(tmp_path, tool, tool_input, expected, clause):
    """clarifications [A-06-7]: 'An unknown agent_type is treated as a blind role by this hook.'"""
    _check(_run(tmp_path, "base", "intruder", tool, tool_input), expected, clause)


# ---------------------------------------------------------------- R-24: published documentation

@pytest.mark.case("TB06-D-181", tier="diagnostic", tb="06", reqs=["R-24"])
def test_docs_hooks_blindness_guard_md():
    """TB-06 Acceptance: 'Document the component in the docs/hooks/ file you own, with one example payload or call
    (requirement R-24).' OWN list names docs/hooks/blindness_guard.md."""
    lib.need("factory.hooks.blindness_guard")
    doc_path = lib.REPO / "docs" / "hooks" / "blindness_guard.md"
    assert doc_path.is_file()
    text = doc_path.read_text()
    assert any(s in text for s in ("hook_event_name", "decide(", "python -m factory.hooks")), "one example payload or call"
    assert "sandbox" in text.lower(), "B7: the residual gap names the OS sandbox as the backstop"
