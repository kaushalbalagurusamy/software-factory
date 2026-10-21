"""SFN-02b: path_guard enforces the qa_paths writes class and QA git restrictions (C-41.2, C-41.3)."""
from __future__ import annotations

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import path_guard
from factory.hooks.core import HookConfig, Payload

PROFILE = {"schema_version": 1, "project": {"name": "demo"},
           "paths": {"eval": ["evals/**"], "held_out": ["held/**"], "frozen_tests": ["tests/frozen_*.py"]}}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    return r


def decide(root, role, tool, cfg=None, **tool_input):
    cfg = cfg or HookConfig.from_profile(parse_profile(PROFILE), root)
    p = Payload(event="PreToolUse", tool_name=tool, tool_input=tool_input, agent_type=role, agent_id="a1",
                cwd=str(root), last_assistant_message=None, agent_transcript_path=None, raw={})
    return path_guard.decide(p, cfg).kind


QA_OK = ["docs/slices/s1/qa-notes.md", "docs/slices/s1/qa-feedback/t1.md", ".sf/slices/s1/attempts.jsonl",
         ".sf/slices/s1/failures.json", ".sf/slices/s1/notes.txt", ".sf/slices/s1/x.tsv"]
QA_NO = ["src/app.py", "tests/test_x.py", "qa-notes.md", "docs/qa-notes.md", "docs/slices/s1/qa-notes.md.bak",
         "docs/slices/s1/qa-feedback/t1.py", "docs/slices/s1/qa-feedback/sub/t1.md",
         "tests/qa-feedback/conftest.py", "src/qa-feedback/conftest.py", "scripts/qa-feedback/run.sh",
         "docs/slices/s1/qa-feedback/conftest.py", ".sf/slices/s1/run.sh", ".sf/slices/s1/a.py",
         ".sf/slices/s1/tests/a.md", ".sf/slices/tests/x.md", "docs/slices/tests/qa-notes.md",
         "evals/qa-notes.md", "held/a.md", "tests/frozen_a.py", ".factory/x.md", ".claude/x.md", ".git/x.md",
         ".sf/qa/a.json", ".sf/other.json", ".sf/slices", "../outside/qa-notes.md"]


@pytest.mark.parametrize("path", QA_OK)
@pytest.mark.parametrize("tool,field", [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path")])
def test_qa_may_write_only_qa_paths(root, path, tool, field):
    assert decide(root, "qa", tool, **{field: str(root / path)}) == "allow"


@pytest.mark.parametrize("path", QA_NO)
def test_qa_denied_elsewhere(root, path):
    assert decide(root, "qa", "Write", file_path=str(root / path)) == "deny"


def test_qa_symlink_cannot_reach_app_code(root):
    (root / "src").mkdir()
    (root / "src/app.py").write_text("x")
    (root / "docs/slices/s1").mkdir(parents=True)
    (root / "docs/slices/s1/qa-notes.md").symlink_to(root / "src/app.py")
    assert decide(root, "qa", "Write", file_path=str(root / "docs/slices/s1/qa-notes.md")) == "deny"


def test_qa_malformed_target_denied(root):
    assert decide(root, "qa", "Write", file_path=None) == "deny"


@pytest.mark.parametrize("path", ["docs/slices/s1/qa-notes.md", "docs/slices/s1/qa-feedback/a.md", ".sf/slices/s1/a.json"])
def test_implement_denied_qa_paths(root, path):
    assert decide(root, "implement", "Write", file_path=str(root / path)) == "deny"


def test_implement_still_writes_app_code(root):
    assert decide(root, "implement", "Write", file_path=str(root / "src/app.py")) == "allow"


def test_qa_globs_from_config_override(root):
    cfg = HookConfig.from_profile(parse_profile(PROFILE), root)
    object.__setattr__(cfg, "qa_paths", ("notes/**",))
    assert decide(root, "qa", "Write", cfg, file_path=str(root / "notes/a.md")) == "allow"
    assert decide(root, "qa", "Write", cfg, file_path=str(root / "docs/slices/s1/qa-notes.md")) == "deny"
    assert decide(root, "implement", "Write", cfg, file_path=str(root / "notes/a.md")) == "deny"


@pytest.mark.parametrize("cmd", ["pytest -q", "git status", "git diff HEAD", "git log --oneline",
                                 "python -m factory.qa status"])
def test_qa_bash_runs_suites_and_reads_git(root, cmd):
    assert decide(root, "qa", "Bash", command=cmd) == "allow"


@pytest.mark.parametrize("cmd", [
    "git add -A", "git add .", "git add src/a.py", "git commit -m x", "git checkout evals/a.py",
    "git restore evals/a.py", "git reset --hard", "git stash", "git push", "git merge x",
    "pytest && git commit -m x", "bash -c 'git add -A'", "git commit --amend", "git rebase main",
    "echo 'unterminated"])
def test_qa_bash_git_restrictions(root, cmd):
    assert decide(root, "qa", "Bash", command=cmd) == "deny"


def test_qa_bash_malformed_command_denied(root):
    assert decide(root, "qa", "Bash", command=None) == "deny"
    assert decide(root, "qa", "Bash", command=["git", "add"]) == "deny"


NOTES = "docs/slices/s1/qa-notes.md"


@pytest.mark.parametrize("cmd", [
    f"echo x > {NOTES}", f"echo x >> {NOTES}", f"pytest -q > .sf/slices/s1/out.txt 2>&1",
    "pytest -q 2>&1 | tee .sf/slices/s1/run.txt", "pytest -q > /dev/null 2>&1", "pytest -q 2>/dev/null",
    f"sed -i s/a/b/ {NOTES}", f"cp /etc/hostname {NOTES}", f"mv .sf/slices/s1/a.json .sf/slices/s1/b.json",
    f"rm .sf/slices/s1/a.json", "dd if=/dev/zero of=.sf/slices/s1/z.txt count=1",
    "python -c \"print(open('data.json').read())\"", "python -m pytest -p no:cacheprovider -q",
    f"bash -c 'echo x > {NOTES}'"])
def test_qa_bash_allowed_writes(root, cmd):
    assert decide(root, "qa", "Bash", command=cmd) == "allow"


@pytest.mark.parametrize("cmd", [
    "echo x > src/app.py", "echo x >> src/app.py", "echo x >src/app.py", "echo x 1>src/app.py",
    "echo x &> src/app.py", "echo x > evals/golden.txt", "pytest -q | tee src/a.py", "tee -a tests/t.py",
    "sed -i s/a/b/ src/app.py", "sed -i.bak s/a/b/ src/app.py", "sed -ni 1p src/app.py",
    "sed --in-place s/a/b/ src/app.py", "cp /etc/hostname src/a", "cp -t src /etc/hostname",
    "mv src/a.py src/b.py", "mv x.md src/x.md", "rm src/app.py", "rm -rf tests", "touch tests/t.py",
    "dd if=/dev/zero of=src/a count=1", "python -c \"open('src/a','w').write('x')\"",
    "python3 -c 'from pathlib import Path; Path(\"a\").write_text(\"x\")'",
    "bash -c 'echo x > src/a'", "sh -c \"rm src/a\"", "echo x > $HOME/a", "echo x > ~/a", "echo x >",
    "cat y > docs/slices/s1/qa-feedback/c.py"])
def test_qa_bash_denied_writes(root, cmd):
    assert decide(root, "qa", "Bash", command=cmd) == "deny"


def test_other_full_bash_roles_are_not_inspected(root):
    assert decide(root, "implement", "Bash", command="echo x > src/app.py") == "allow"
