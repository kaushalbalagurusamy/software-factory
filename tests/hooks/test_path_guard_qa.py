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


QA_OK = ["qa-notes.md", "docs/qa-notes.md", "slices/s1/qa-feedback/t1.md", "qa-feedback/x.md", ".sf/qa/attempts.json"]
QA_NO = ["src/app.py", "tests/test_x.py", "qa-notes.md.bak", "qa-notes.md/x.py", "evals/qa-notes.md",
         "evals/qa-feedback/x.md", "held/qa-feedback/x.md", "tests/frozen_a.py", ".factory/qa-feedback/x.md",
         ".claude/qa-notes.md", ".sf/other.json", "../outside/qa-notes.md"]


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
    (root / "qa-notes.md").symlink_to(root / "src/app.py")
    assert decide(root, "qa", "Write", file_path=str(root / "qa-notes.md")) == "deny"


def test_qa_malformed_target_denied(root):
    assert decide(root, "qa", "Write", file_path=None) == "deny"


@pytest.mark.parametrize("path", ["qa-notes.md", "x/qa-feedback/a.md", ".sf/qa/a.json"])
def test_implement_denied_qa_paths(root, path):
    assert decide(root, "implement", "Write", file_path=str(root / path)) == "deny"


def test_implement_still_writes_app_code(root):
    assert decide(root, "implement", "Write", file_path=str(root / "src/app.py")) == "allow"


def test_qa_globs_from_config_override(root):
    cfg = HookConfig.from_profile(parse_profile(PROFILE), root)
    object.__setattr__(cfg, "qa_paths", ("notes/**",))
    assert decide(root, "qa", "Write", cfg, file_path=str(root / "notes/a.md")) == "allow"
    assert decide(root, "qa", "Write", cfg, file_path=str(root / "qa-notes.md")) == "deny"
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
