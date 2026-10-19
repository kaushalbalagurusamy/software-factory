"""Unit tests for the path guard (TB-05). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import path_guard
from factory.hooks.core import HookConfig, Payload, run_hook

PROFILE = {
    "schema_version": 1,
    "project": {"name": "demo"},
    "paths": {
        "eval": ["evals/**"],
        "held_out": ["held/**"],
        "frozen_tests": ["tests/frozen_*.py"],
        "baseline_update": ["baselines/**"],
    },
}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    return r


def make_cfg(root, **extra):
    data = dict(PROFILE)
    data.update(extra)
    return HookConfig.from_profile(parse_profile(data), root)


def payload(root, tool, role="implement", cwd=None, **tool_input):
    d = {"session_id": "s", "cwd": str(cwd or root), "hook_event_name": "PreToolUse",
         "permission_mode": "default", "tool_name": tool, "tool_input": tool_input}
    if role:
        d["agent_type"] = role
        d["agent_id"] = "a1"
    return Payload(event="PreToolUse", tool_name=tool, tool_input=tool_input, agent_type=role,
                   agent_id="a1" if role else None, cwd=str(cwd or root), last_assistant_message=None,
                   agent_transcript_path=None, raw=d)


def write(root, role, path, tool="Write", cfg=None, cwd=None):
    cfg = cfg or make_cfg(root)
    return path_guard.decide(payload(root, tool, role, cwd, file_path=str(path)), cfg)


def bash(root, role, command, cfg=None):
    cfg = cfg or make_cfg(root)
    return path_guard.decide(payload(root, "Bash", role, command=command), cfg)


# ---- Write / Edit by role --------------------------------------------------------------------
@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_research_only_research_dir(root, tool):
    assert write(root, "research", root / "research" / "n.md", tool).kind == "allow"
    d = write(root, "research", root / "src" / "a.py", tool)
    assert d.kind == "deny"
    assert "research" in d.reason and str(root / "src" / "a.py") in d.reason


def test_design_dirs(root):
    for p in ("docs/prd/a.md", "docs/spec/b.md", "docs/adr/c.md"):
        assert write(root, "design", root / p).kind == "allow"
    assert write(root, "design", root / "docs" / "other.md").kind == "deny"


def test_audit_dir(root):
    assert write(root, "audit", root / "docs/audit/x.md").kind == "allow"
    assert write(root, "audit", root / "docs/audit").kind == "deny"
    assert write(root, "audit", root / "docs/auditor/x.md").kind == "deny"


def test_custom_dirs_from_profile(root):
    cfg = make_cfg(root, paths={**PROFILE["paths"], "research_dir": "notes"})
    assert write(root, "research", root / "notes/a.md", cfg=cfg).kind == "allow"
    assert write(root, "research", root / "research/a.md", cfg=cfg).kind == "deny"


def test_test_role_eval_before_freeze(root):
    assert write(root, "test", root / "evals/golden/a.json").kind == "allow"
    d = write(root, "test", root / "src/a.py")
    assert d.kind == "deny" and "test" in d.reason and "evals/**" in d.reason
    assert write(root, "test", root / "baselines/h.json").kind == "deny"


def test_freeze(root):
    (root / ".factory").mkdir()
    (root / ".factory" / "frozen").write_text("")
    d = write(root, "test", root / "evals/golden/a.json")
    assert d.kind == "deny" and "frozen" in d.reason and "baselines/**" in d.reason
    assert write(root, "test", root / "baselines/h.json").kind == "allow"
    # the freeze does not restrict other roles
    assert write(root, "implement", root / "src/a.py").kind == "allow"


@pytest.mark.parametrize("role", ["orchestrator", "review"])
def test_no_write_roles(root, role):
    d = write(root, role, root / "src/a.py")
    assert d.kind == "deny" and f"no write access for role {role}" in d.reason
    assert write(root, role, root / "research/a.md", "Edit").kind == "deny"


def test_implement_protected(root):
    assert write(root, "implement", root / "src/a.py").kind == "allow"
    for p in ("evals/a.json", "evals", "held/x/y.py", "tests/frozen_a.py", ".factory/profile.yaml",
              ".claude/settings.json", ".claude/agents/x.md", ".factory/ledger/l.md"):
        d = write(root, "implement", root / p)
        assert d.kind == "deny", p
        assert "implement" in d.reason and "Allowed folders" in d.reason
    assert write(root, "implement", root / "tests/test_a.py").kind == "allow"
    assert write(root, "implement", root / ".factorybad/a").kind == "allow"
    assert ".claude" in write(root, "implement", root / ".claude/x").reason


def test_main_session_role(root):
    cfg = make_cfg(root)
    p = payload(root, "Write", role=None, file_path=str(root / "src/a.py"))
    d = path_guard.decide(p, cfg)
    assert d.kind == "deny" and "orchestrator" in d.reason
    cfg2 = make_cfg(root, main_session_role="implement")
    assert path_guard.decide(p, cfg2).kind == "allow"


def test_unknown_agent_type(root):
    for tool, kw in (("Write", {"file_path": str(root / "a")}), ("Edit", {"file_path": str(root / "a")}),
                     ("Bash", {"command": "ls"})):
        d = path_guard.decide(payload(root, tool, "mystery", **kw), make_cfg(root))
        assert d.kind == "deny" and "unknown agent type mystery" in d.reason
    for tool in ("Read", "Grep", "Glob"):
        assert path_guard.decide(payload(root, tool, "mystery", file_path="x"), make_cfg(root)).kind == "allow"


# ---- path resolution -------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["implement", "research", "design", "audit", "test", "orchestrator", "review"])
def test_outside_root_denied_for_all(root, role, tmp_path):
    d = write(root, role, tmp_path / "elsewhere.txt")
    assert d.kind == "deny" and "outside the project root" in d.reason


def test_relative_and_dotdot(root):
    assert write(root, "implement", "src/a.py").kind == "allow"
    assert write(root, "implement", "../escape.py").kind == "deny"
    assert write(root, "implement", "src/../evals/a.json").kind == "deny"
    assert write(root, "implement", "../a.py", cwd=root / "src").kind == "allow"
    assert write(root, "research", "a.md", cwd=root / "research").kind == "allow"
    assert write(root, "research", "../src/a.md", cwd=root / "research").kind == "deny"


def test_sibling_prefix_not_inside(root):
    sib = Path(str(root) + "-other")
    sib.mkdir()
    assert write(root, "implement", sib / "a.py").kind == "deny"


def test_symlink_escape_and_alias(root, tmp_path):
    out = tmp_path / "outside"
    out.mkdir()
    (root / "link").symlink_to(out)
    assert write(root, "implement", root / "link/new.py").kind == "deny"
    (root / "evals").mkdir()
    (root / "alias").symlink_to(root / "evals")
    d = write(root, "implement", root / "alias/new.json")
    assert d.kind == "deny"
    (root / ".factory").mkdir()
    (root / "fl").symlink_to(root / ".factory")
    assert write(root, "implement", root / "fl/frozen").kind == "deny"
    (root / "research").mkdir()
    (root / "r2").symlink_to(root / "src_dir_missing")
    assert write(root, "research", root / "research/ok.md").kind == "allow"


def test_symlink_inside_allowed_folder_pointing_out(root, tmp_path):
    (root / "research").mkdir()
    (root / "research" / "x").symlink_to(tmp_path)
    assert write(root, "research", root / "research/x/f.md").kind == "deny"


def test_dotdot_after_symlink_uses_physical_parent(root, tmp_path):
    out = tmp_path / "outside" / "deep"
    out.mkdir(parents=True)
    (root / "link").symlink_to(out)
    # link/.. is outside/, not root
    assert write(root, "implement", root / "link" / ".." / "f.py").kind == "deny"


def test_nonexistent_path_resolves_ancestor(root, tmp_path):
    out = tmp_path / "outside"
    out.mkdir()
    (root / "link").symlink_to(out)
    assert write(root, "implement", root / "link/a/b/c.py").kind == "deny"
    assert write(root, "implement", root / "new/a/b/c.py").kind == "allow"


@pytest.mark.parametrize("bad", [None, "", 5, "a\x00b", "  "])
def test_malformed_file_path_denied(root, bad):
    d = path_guard.decide(payload(root, "Write", "implement", file_path=bad), make_cfg(root))
    assert d.kind == "deny"
    d = path_guard.decide(payload(root, "Write", "implement"), make_cfg(root))
    assert d.kind == "deny"


def test_glob_semantics(root):
    cfg = make_cfg(root, paths={**PROFILE["paths"], "eval": ["a/**/golden/*.json", "x*"]})
    assert write(root, "implement", root / "a/golden/c.json", cfg=cfg).kind == "deny"
    assert write(root, "implement", root / "a/b/c/golden/c.json", cfg=cfg).kind == "deny"
    assert write(root, "implement", root / "a/b/golden/sub/c.json", cfg=cfg).kind == "allow"
    assert write(root, "implement", root / "xyz/k.py", cfg=cfg).kind == "deny"
    assert write(root, "implement", root / "y/xyz", cfg=cfg).kind == "allow"


# ---- read tools ------------------------------------------------------------------------------
@pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Agent", "WebFetch"])
@pytest.mark.parametrize("role", ["orchestrator", "implement", "review"])
def test_other_tools_allowed(root, tool, role):
    assert path_guard.decide(payload(root, tool, role, file_path="evals/x"), make_cfg(root)).kind == "allow"


def test_non_pretooluse_allowed_and_missing_tool_denied(root):
    p = Payload("SessionStart", None, {}, None, None, str(root), None, None, {})
    assert path_guard.decide(p, make_cfg(root)).kind == "allow"
    p = Payload("PreToolUse", None, {}, "implement", None, str(root), None, None, {})
    assert path_guard.decide(p, make_cfg(root)).kind == "deny"


# ---- Bash ------------------------------------------------------------------------------------
ALLOWED_CMDS = [
    "git log --oneline", "git diff HEAD~1", "git show HEAD", "git status", "git blame f.py",
    "ls -la", "cat a.txt", "head -n 3 a", "tail -f a", "wc -l a", "grep -rn foo .", "rg foo",
    "find . -name '*.py'", "tree", "sf audit", "sed -n '1,5p' a", "awk '{print $1}' a",
    "git log | head -5", "git status && ls", "ls; cat a", "cat a | grep x | wc -l",
    "grep 'a > b' f", "grep \"a > b\" f", "grep '$(x)' f", "cat 'a|b'",
    "awk '$1 > 3' f", "grep tee f", "cat a\\>b",
]


@pytest.mark.parametrize("cmd", ALLOWED_CMDS)
@pytest.mark.parametrize("role", ["research", "design", "audit", "review"])
def test_readonly_allowed(root, role, cmd):
    assert bash(root, role, cmd).kind == "allow", cmd


DENIED_CMDS = [
    "rm -rf x", "mv a b", "cp a b", "chmod +x a", "tee out", "ls > out", "ls >> out", "cat a > b",
    "echo hi", "python x.py", "touch f", "mkdir d", "ls | tee f", "ls | rm x", "ls && rm x",
    "ls; rm x", "ls\nrm x", "ls & rm x", "ls || rm x",
    "find . -delete", "find . -exec rm {} ;", "find . -name x -exec cat {} +",
    "cat $(whoami)", "cat `whoami`", "cat \"$(whoami)\"", "cat \"`x`\"", "ls <(x)",
    "awk '{print}' a > b", "git commit -m x", "git push", "git checkout x", "git -C d log",
    "lsof", "catx a", "sed -i s/a/b/ f", "sed -n -i p f", "sed 's/a/b/' f", "git diff --output=f",
    "git log --output f", "tree -o f", "rg --pre x foo", "FOO=1 ls", "(ls)", "", "   ",
    "cat 'unterminated", "ls 2>&1", "ls >/dev/null", "git", "sed",
]


@pytest.mark.parametrize("cmd", DENIED_CMDS)
def test_readonly_denied(root, cmd):
    d = bash(root, "research", cmd)
    assert d.kind == "deny", cmd
    assert "research" in d.reason
    assert "Allowed folders" in d.reason


def test_bash_reason_names_command(root):
    d = bash(root, "audit", "rm -rf build")
    assert "rm -rf build" in d.reason and "docs/audit" in d.reason


def test_single_quotes_exempt_substitution_double_do_not(root):
    assert bash(root, "audit", "grep '$(x)' f").kind == "allow"
    assert bash(root, "audit", "grep \"$(x)\" f").kind == "deny"
    assert bash(root, "audit", "grep \\$\\(x f").kind == "allow"


@pytest.mark.parametrize("role", ["orchestrator", "implement", "test"])
def test_full_bash_not_inspected(root, role):
    assert bash(root, role, "rm -rf x > y").kind == "allow"


@pytest.mark.parametrize("bad", [None, 5, ["ls"]])
def test_bash_malformed_command(root, bad):
    assert bash(root, "research", bad).kind == "deny"


# ---- through the adapter ---------------------------------------------------------------------
def test_run_hook_roundtrip_and_recorded_example(root):
    text = json.dumps({
        "session_id": "s1", "cwd": str(root), "hook_event_name": "PreToolUse",
        "permission_mode": "default", "agent_type": "research", "agent_id": "a1",
        "tool_name": "Write", "tool_input": {"file_path": "src/app.py", "content": "x"}})
    res = run_hook(path_guard.decide, text, make_cfg(root))
    assert res.exit_code == 2 and res.stdout == ""
    assert "role research" in res.stderr and "src/app.py" in res.stderr and "research" in res.stderr
    ok = text.replace("src/app.py", "research/notes.md")
    assert run_hook(path_guard.decide, ok, make_cfg(root)).exit_code == 0


def test_registry_finds_module():
    from factory.hooks import registry
    assert registry.get_hook("path_guard").decide is path_guard.decide
