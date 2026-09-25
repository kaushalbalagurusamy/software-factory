"""TB-13 project settings emitter: golden and diagnostic cases.

Expectations come only from docs/prds/TB-13-settings-emitter.md, docs/contracts/hook-io.md,
docs/contracts/roles-and-generation.md (the Claude Code hooks shape `event -> [{matcher, hooks: [{type:
command, command}]}]`) and docs/contracts/profile.md.
"""
from __future__ import annotations

import builtins
import copy
import io
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from evals.agents import lib

HOOK_IDS = {"path_guard", "blindness_guard", "secrets_guard", "bash_guard", "stop_gate", "subagent_stop",
            "ledger_audit", "session_start"}
GUARD_TOOLS = {"path_guard": ["Write", "Edit"], "blindness_guard": ["Read", "Grep", "Glob", "Bash"],
               "secrets_guard": ["Write", "Edit", "Bash"], "bash_guard": ["Bash"]}
EVENT = {"path_guard": "PreToolUse", "blindness_guard": "PreToolUse", "secrets_guard": "PreToolUse",
         "bash_guard": "PreToolUse", "subagent_stop": "SubagentStop", "ledger_audit": "SubagentStop",
         "stop_gate": "SubagentStop", "session_start": "SessionStart"}
SECRET_RE = re.compile(r"(sk-(ant|or)-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                       r"|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,})")
HOME_RE = re.compile(r"(/Users/[^/\s\"]+|/home/[^/\s\"]+)")
PREFIX = "python -m factory.hooks"


def case(cid, tier, reqs=("R-18",)):
    return pytest.mark.case(cid, tier=tier, tb="13", reqs=list(reqs))


def mods():
    prof = lib.need("factory.agents.profile", "load_profile")
    roles = lib.need("factory.agents.roles", "load_roles")
    st = lib.need("factory.agents.settings", "emit_settings", "diff_settings")
    return prof, roles, st


def inputs(tmp_path, data="base", sub="p"):
    prof, roles, st = mods()
    root = lib.make_project(tmp_path / sub, data)
    return prof.load_profile(root / ".factory" / "profile.yaml"), roles.load_roles(), st


def role_hook_ids(roles):
    out = set()
    for spec in roles.values():
        out |= set(spec["hooks"] if isinstance(spec, Mapping) else getattr(spec, "hooks"))
    return out


def entries(settings, event=None):
    """(event, matcher, type, command) tuples from the hooks section."""
    out = []
    for ev, groups in (settings.get("hooks") or {}).items():
        if event and ev != event:
            continue
        for g in groups or []:
            for h in g.get("hooks", []) or []:
                out.append((ev, g.get("matcher"), h.get("type"), h.get("command")))
    return out


def matches(matcher, tool):
    if matcher in (None, "", "*"):
        return True
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return tool in str(matcher).split("|")


FOREIGN = {
    "model": "user-chosen-model",
    "env": {"SOME_FLAG": "1"},
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(./private/**)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./scripts/my-own-hook.sh"}]}],
        "Notification": [{"matcher": "", "hooks": [{"type": "command", "command": "notify-send done"}]}],
    },
}


# ---------------------------------------------------------------- golden

@case("TB13-G-001", "golden")
def test_g001_guards_registered_pretooluse(tmp_path):
    """Behaviour 1: each guard hook id the roles use is registered under PreToolUse as
    `python -m factory.hooks <id>`."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    cmds = {c for _, _, _, c in entries(s, "PreToolUse")}
    for hid in role_hook_ids(roles) & set(GUARD_TOOLS):
        assert f"{PREFIX} {hid}" in cmds, hid


@case("TB13-G-002", "golden")
def test_g002_stop_and_session_events(tmp_path):
    """Behaviour 1: subagent_stop, ledger_audit and stop_gate under SubagentStop; session_start under
    SessionStart."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    for hid in role_hook_ids(roles) & {"subagent_stop", "ledger_audit", "stop_gate", "session_start"}:
        assert f"{PREFIX} {hid}" in {c for _, _, _, c in entries(s, EVENT[hid])}, hid


@case("TB13-G-003", "golden")
def test_g003_idempotent(tmp_path):
    """Behaviour 2: emitting twice, or emitting over its own output, gives an equal result."""
    p, roles, st = inputs(tmp_path)
    first = st.emit_settings(p, roles)
    assert st.emit_settings(p, roles) == first
    assert st.emit_settings(p, roles, existing=copy.deepcopy(first)) == first


@case("TB13-G-004", "golden")
def test_g004_preserves_foreign_entries(tmp_path):
    """Behaviour 3: keys and hooks in existing that this tool did not create are preserved."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert s["model"] == "user-chosen-model"
    assert s["env"] == {"SOME_FLAG": "1"}
    assert "Bash(ls:*)" in s["permissions"]["allow"]
    cmds = {c for _, _, _, c in entries(s)}
    assert "./scripts/my-own-hook.sh" in cmds and "notify-send done" in cmds


@case("TB13-G-005", "golden", reqs=("R-18", "R-11"))
def test_g005_no_deny_rules_for_eval_paths(tmp_path):
    """Behaviour 4: never adds permissions.deny rules for the eval paths (blindness is a hook, R-11)."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    deny = (s.get("permissions") or {}).get("deny") or []
    assert not [r for r in deny if "evals" in r]


@case("TB13-G-006", "golden")
def test_g006_diff_empty_when_equal(tmp_path):
    """Behaviour 5: diff_settings(old, new) is empty when equal."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    assert st.diff_settings(s, copy.deepcopy(s)) == ""


@case("TB13-G-007", "golden")
def test_g007_stale_factory_entry_removed(tmp_path):
    """Behaviour 3: entries this tool created (commands starting `python -m factory.hooks`) are replaced or
    removed to match the profile: a stale one for an unknown hook id disappears."""
    p, roles, st = inputs(tmp_path)
    existing = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f"{PREFIX} retired_hook"}]}]}}
    s = st.emit_settings(p, roles, existing=existing)
    assert f"{PREFIX} retired_hook" not in {c for _, _, _, c in entries(s)}


# ---------------------------------------------------------------- diagnostic

@case("TB13-D-001", "diagnostic")
def test_d001_guard_matchers(tmp_path):
    """Behaviour 1 'under its event and matcher': each guard's PreToolUse matcher covers the tools it inspects
    (path_guard Write/Edit; blindness_guard Read/Grep/Glob/Bash; secrets_guard Write/Edit/Bash; bash_guard
    Bash)."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    for hid in role_hook_ids(roles) & set(GUARD_TOOLS):
        ms = [m for _, m, _, c in entries(s, "PreToolUse") if c == f"{PREFIX} {hid}"]
        for tool in GUARD_TOOLS[hid]:
            assert any(matches(m, tool) for m in ms), (hid, tool)


@case("TB13-D-002", "diagnostic")
def test_d002_every_role_hook_registered(tmp_path):
    """Behaviour 1: every hook id the role specs use is registered, and only under its event."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles)
    got = {}
    for ev, _, _, c in entries(s):
        if c and c.startswith(PREFIX + " "):
            got.setdefault(c.split()[-1], set()).add(ev)
    for hid in role_hook_ids(roles):
        assert got.get(hid) == {EVENT[hid]}, hid


@case("TB13-D-003", "diagnostic")
def test_d003_only_known_hook_ids(tmp_path):
    """Behaviour 1 + hook-io.md: every factory command is `python -m factory.hooks <id>` with a published id,
    with hook type command."""
    p, roles, st = inputs(tmp_path)
    for ev, _, t, c in entries(st.emit_settings(p, roles)):
        assert c.startswith(PREFIX + " ")
        assert c.split()[-1] in HOOK_IDS and len(c.split()) == 4, c
        assert t == "command"


@case("TB13-D-004", "diagnostic")
def test_d004_no_duplicates_over_own_output(tmp_path):
    """Behaviour 2 + 3: emitting over its own output replaces factory entries; no factory command appears twice
    under the same event and matcher."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles, existing=st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN)))
    fac = [(e, m, c) for e, m, _, c in entries(s) if c.startswith(PREFIX)]
    assert len(fac) == len(set(fac))


@case("TB13-D-005", "diagnostic")
def test_d005_existing_none_equals_empty(tmp_path):
    """Behaviour 3: with nothing foreign to preserve, existing={} gives the same result as existing=None."""
    p, roles, st = inputs(tmp_path)
    assert st.emit_settings(p, roles, existing={}) == st.emit_settings(p, roles)


@case("TB13-D-006", "diagnostic")
def test_d006_foreign_deny_rule_preserved(tmp_path):
    """Behaviour 3: an existing permissions.deny rule the tool did not create is preserved."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert "Read(./private/**)" in s["permissions"]["deny"]


@case("TB13-D-007", "diagnostic")
def test_d007_factory_entry_under_wrong_event_removed(tmp_path):
    """Behaviour 3: a factory-created entry under an event the profile does not call for is removed."""
    p, roles, st = inputs(tmp_path)
    existing = {"hooks": {"PostToolUse": [{"matcher": "Write", "hooks": [
        {"type": "command", "command": f"{PREFIX} bash_guard"}]}]}}
    s = st.emit_settings(p, roles, existing=existing)
    assert f"{PREFIX} bash_guard" not in {c for _, _, _, c in entries(s, "PostToolUse")}


@case("TB13-D-008", "diagnostic")
def test_d008_foreign_hook_same_event_kept_with_factory(tmp_path):
    """Behaviour 3: a foreign PreToolUse hook survives alongside the factory guards, and emitting again over the
    merged result keeps it exactly once."""
    p, roles, st = inputs(tmp_path)
    once = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    twice = st.emit_settings(p, roles, existing=copy.deepcopy(once))
    assert twice == once
    assert [c for _, _, _, c in entries(twice, "PreToolUse")].count("./scripts/my-own-hook.sh") == 1


@case("TB13-D-009", "diagnostic")
def test_d009_diff_nonempty_unified(tmp_path):
    """Behaviour 5: diff_settings returns unified-diff text, non-empty when the settings differ, showing the
    change."""
    p, roles, st = inputs(tmp_path)
    new = st.emit_settings(p, roles)
    d = st.diff_settings({}, new)
    assert d.strip()
    assert "@@" in d
    assert any(line.startswith("+") and "factory.hooks" in line for line in d.splitlines())


@case("TB13-D-010", "diagnostic")
def test_d010_diff_stable(tmp_path):
    """Behaviour 5: the diff text is stable (same inputs, same text)."""
    p, roles, st = inputs(tmp_path)
    new = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert st.diff_settings(FOREIGN, new) == st.diff_settings(copy.deepcopy(FOREIGN), copy.deepcopy(new))


@case("TB13-D-011", "diagnostic")
def test_d011_diff_shows_removal(tmp_path):
    """Behaviour 5: removing a stale factory entry shows as a '-' line in the diff."""
    p, roles, st = inputs(tmp_path)
    old = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f"{PREFIX} retired_hook"}]}]}}
    new = st.emit_settings(p, roles, existing=copy.deepcopy(old))
    d = st.diff_settings(old, new)
    assert any(line.startswith("-") and "retired_hook" in line for line in d.splitlines())


@pytest.mark.parametrize("fixture", [
    pytest.param("base", marks=case("TB13-D-012", "diagnostic", reqs=("R-18", "R-23")), id="base"),
    pytest.param("alt", marks=case("TB13-D-013", "diagnostic", reqs=("R-18", "R-23")), id="alt"),
])
def test_d012_no_secret_or_home_path(tmp_path, fixture):
    """Behaviour 6 + R-23: the output contains no secret-shaped value and no absolute home path."""
    p, roles, st = inputs(tmp_path, fixture)
    text = json.dumps(st.emit_settings(p, roles))
    assert not SECRET_RE.search(text)
    assert not HOME_RE.search(text)
    assert str(Path.home()) not in text


@case("TB13-D-014", "diagnostic")
def test_d014_no_file_io(tmp_path, monkeypatch):
    """Behaviour 6: it never reads or writes any file (the caller does)."""
    p, roles, st = inputs(tmp_path)

    def refuse(*a, **k):
        raise AssertionError("file access attempted")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(io, "open", refuse)
    monkeypatch.setattr(os, "open", refuse)
    s = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    st.diff_settings(FOREIGN, s)


@case("TB13-D-015", "diagnostic", reqs=("R-18", "R-11"))
def test_d015_alt_no_deny_for_eval_or_held_out(tmp_path):
    """Behaviour 4 on the alt fixture: no deny rule names its eval or held-out paths."""
    p, roles, st = inputs(tmp_path, "alt")
    s = st.emit_settings(p, roles)
    deny = (s.get("permissions") or {}).get("deny") or []
    assert not [r for r in deny if "qa/" in r]


@case("TB13-D-016", "diagnostic", reqs=("R-18", "R-11"))
def test_d016_no_new_deny_when_merging(tmp_path):
    """Behaviour 4: merging over existing settings adds no deny rule (existing deny rules are kept as they are)."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert list(s["permissions"]["deny"]) == FOREIGN["permissions"]["deny"]


@case("TB13-D-017", "diagnostic", reqs=("R-18", "R-01"))
def test_d017_generality_no_cross_profile_values(tmp_path):
    """Generality: output changes only through the profile; the base output carries nothing only alt supplies,
    and vice versa."""
    pb, roles, st = inputs(tmp_path, "base", "a")
    pa, _, _ = inputs(tmp_path, "alt", "b")
    tb, ta = json.dumps(st.emit_settings(pb, roles)), json.dumps(st.emit_settings(pa, roles))
    for v in ["fixture-beta", "qa/", "cloudctl", "db-reset", "FIXTURE-KEY"]:
        assert v not in tb, v
    for v in ["fixture-alpha", "deployctl", "docsrv", "tests/held_out"]:
        assert v not in ta, v


@case("TB13-D-018", "diagnostic")
def test_d018_json_serialisable(tmp_path):
    """Behaviour 1: the settings object is a plain dict that round-trips through JSON (a settings.json)."""
    p, roles, st = inputs(tmp_path)
    s = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert isinstance(s, dict) and json.loads(json.dumps(s)) == s


@case("TB13-D-019", "diagnostic")
def test_d019_idempotent_with_foreign(tmp_path):
    """Behaviour 2: emitting over its own merged output is a fixed point."""
    p, roles, st = inputs(tmp_path)
    once = st.emit_settings(p, roles, existing=copy.deepcopy(FOREIGN))
    assert st.emit_settings(p, roles, existing=copy.deepcopy(once)) == once
    assert st.diff_settings(once, st.emit_settings(p, roles, existing=copy.deepcopy(once))) == ""


@case("TB13-D-020", "diagnostic")
def test_d020_stale_entry_replaced_in_mixed_group(tmp_path):
    """Behaviour 3: in a group holding both a foreign and a stale factory command, the foreign one survives and
    the stale one is removed."""
    p, roles, st = inputs(tmp_path)
    existing = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "./keep-me.sh"},
        {"type": "command", "command": f"{PREFIX} retired_hook"}]}]}}
    cmds = {c for _, _, _, c in entries(st.emit_settings(p, roles, existing=existing))}
    assert "./keep-me.sh" in cmds and f"{PREFIX} retired_hook" not in cmds
