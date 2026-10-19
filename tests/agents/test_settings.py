"""Unit coverage for the settings emitter (TB-13). Not the acceptance gate."""
from __future__ import annotations

import copy
import json

import pytest

from factory.agents.profile import parse_profile
from factory.agents.roles import load_roles
from factory.agents.settings import SettingsError, diff_settings, emit_settings

PREFIX = "python -m factory.hooks"


@pytest.fixture(scope="module")
def roles():
    return load_roles()


@pytest.fixture(scope="module")
def profile():
    return parse_profile({"schema_version": 1, "project": {"name": "Zorblax"},
                          "paths": {"eval": ["evals/**"]}})


def flat(settings):
    out = []
    for event, entries in settings["hooks"].items():
        for e in entries:
            for h in e["hooks"]:
                out.append((event, e.get("matcher"), h["command"]))
    return out


def test_registers_all_eight(profile, roles):
    got = flat(emit_settings(profile, roles))
    assert sorted(c for _, _, c in got) == sorted(f"{PREFIX} {h}" for h in [
        "path_guard", "blindness_guard", "secrets_guard", "bash_guard",
        "stop_gate", "subagent_stop", "ledger_audit", "session_start"])
    by = {c.split()[-1]: (ev, m) for ev, m, c in got}
    assert by["path_guard"] == ("PreToolUse", "Write|Edit|Bash")
    assert by["secrets_guard"] == ("PreToolUse", "Write|Edit|Bash")
    assert by["blindness_guard"] == ("PreToolUse", "Read|Grep|Glob|Bash")
    assert by["bash_guard"] == ("PreToolUse", "Bash")
    assert by["stop_gate"] == ("SubagentStop", None)
    assert by["subagent_stop"] == ("SubagentStop", None)
    assert by["ledger_audit"] == ("SubagentStop", None)
    assert by["session_start"] == ("SessionStart", None)


def test_shape(profile, roles):
    s = emit_settings(profile, roles)
    for entries in s["hooks"].values():
        for e in entries:
            assert set(e) <= {"matcher", "hooks"}
            assert all(h["type"] == "command" for h in e["hooks"])
            if "matcher" in e:
                assert e["matcher"]


def test_idempotent(profile, roles):
    a = emit_settings(profile, roles)
    assert emit_settings(profile, roles) == a
    assert emit_settings(profile, roles, a) == a
    assert diff_settings(a, emit_settings(profile, roles, a)) == ""


def test_deterministic_json(profile, roles):
    a = json.dumps(emit_settings(profile, roles))
    assert a == json.dumps(emit_settings(profile, roles))


def test_preserves_foreign(profile, roles):
    existing = {
        "model": "opus", "env": {"A": "1"},
        "permissions": {"allow": ["Bash(ls)"]},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./mine.sh"}]}],
            "Notification": [{"hooks": [{"type": "command", "command": "notify"}]}],
        },
    }
    snap = copy.deepcopy(existing)
    out = emit_settings(profile, roles, existing)
    assert existing == snap  # A-35
    assert out["model"] == "opus" and out["env"] == {"A": "1"}
    assert out["permissions"] == {"allow": ["Bash(ls)"]}
    assert out["hooks"]["Notification"] == snap["hooks"]["Notification"]
    assert ("PreToolUse", "Bash", "./mine.sh") in flat(out)
    assert len([1 for _, _, c in flat(out) if c.startswith(PREFIX)]) == 8


def test_replaces_stale_own_entries(profile, roles):
    existing = {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": f"{PREFIX} old_hook"},
            {"type": "command", "command": "./mine.sh"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": f"{PREFIX} stop_gate"}]}],
    }}
    out = emit_settings(profile, roles, existing)
    cmds = [c for _, _, c in flat(out)]
    assert f"{PREFIX} old_hook" not in cmds
    assert "./mine.sh" in cmds
    assert "Stop" not in out["hooks"]
    assert cmds.count(f"{PREFIX} stop_gate") == 1


def test_removes_when_no_roles(profile):
    existing = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": f"{PREFIX} session_start"}]}]}}
    out = emit_settings(profile, {}, existing)
    assert flat(out) == []


def test_no_permissions_deny(profile, roles):
    s = emit_settings(profile, roles)
    assert "permissions" not in s
    assert "deny" not in json.dumps(s)


def test_clean_output(profile, roles):
    text = json.dumps(emit_settings(profile, roles))
    assert "/home/" not in text and "sk-" not in text


def test_refuses_secret_or_home(profile, roles):
    with pytest.raises(SettingsError):
        emit_settings(profile, roles, {"env": {"K": "sk-" + "a1" * 20}})
    with pytest.raises(SettingsError):
        emit_settings(profile, roles, {"x": "/home/someone/proj"})


def test_bad_existing(profile, roles):
    with pytest.raises(SettingsError):
        emit_settings(profile, roles, {"hooks": []})
    with pytest.raises(SettingsError):
        emit_settings(profile, roles, [])


def test_diff(profile, roles):
    a = emit_settings(profile, roles)
    assert diff_settings(a, a) == ""
    assert diff_settings(None, {}) == ""
    d = diff_settings({}, a)
    assert d.startswith("---") and "+++" in d and "python -m factory.hooks" in d
    assert d == diff_settings({}, a)
    assert diff_settings({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ""
