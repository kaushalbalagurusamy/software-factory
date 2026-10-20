"""L-08 hooks: print / install / uninstall and the `hook` subcommand."""
from __future__ import annotations

import copy
import json
import subprocess

import pytest

from .conftest import LSF, walk

# Amended after the adversarial review (docs/reviews/2026-10-20-lsf-review.md, finding 1d): a PreToolUse guard on Bash
# joins the three telemetry hooks.
EVENTS = ("SubagentStop", "Stop", "PostToolUse", "PreToolUse")


def printed(rig):
    p = rig.run("hooks", "print")
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def commands(cfg):
    """{event: [command, ...]} from a Claude Code settings object."""
    out = {}
    for ev, groups in cfg["hooks"].items():
        for g in groups:
            for h in g["hooks"]:
                out.setdefault(ev, []).append((g.get("matcher"), h["command"]))
    return out


def run_hook(rig, event, payload, cwd=None):
    cmd = commands(printed(rig))[event][0][1]
    data = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    return subprocess.run(["sh", "-c", cmd], cwd=str(cwd or rig.repo), env=rig.env, input=data,
                          capture_output=True, text=not isinstance(data, bytes), timeout=20)


def test_L08_print_has_the_three_events_and_absolute_commands(rig):
    cfg = printed(rig)
    assert set(cfg["hooks"]) == set(EVENTS)
    cmds = commands(cfg)
    for ev in EVENTS:
        assert len(cmds[ev]) == 1
        c = cmds[ev][0][1]
        assert c.startswith("python3 ")
        assert str(LSF.resolve()) in c and " hook " in c
    assert cmds["PostToolUse"][0][0] == "Bash"
    assert cmds["PreToolUse"][0][0] == "Bash" and cmds["PreToolUse"][0][1].endswith("hook guard")
    assert all(m in (None, "") for m in (cmds["Stop"][0][0], cmds["SubagentStop"][0][0]))


def test_L08_print_is_deterministic_and_writes_nothing(rig):
    a = rig.run("hooks", "print").stdout
    assert a == rig.run("hooks", "print").stdout
    assert not (rig.repo / ".claude").exists() and not (rig.repo / ".lsf").exists()


def test_L08_install_without_apply_only_shows_a_diff(rig, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    p = rig.run("hooks", "install", "--project", proj)
    assert p.returncode == 0, p.stderr
    assert "SubagentStop" in p.stdout and "settings.local.json" in p.stdout
    assert not (proj / ".claude" / "settings.local.json").exists()


def test_L08_install_apply_creates_file_and_is_idempotent(rig, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    assert rig.run("hooks", "install", "--project", proj, "--apply").returncode == 0
    f = proj / ".claude" / "settings.local.json"
    first = f.read_bytes()
    cmds = commands(json.loads(first))
    assert set(cmds) == set(EVENTS) and all(len(v) == 1 for v in cmds.values())
    assert rig.run("hooks", "install", "--project", proj, "--apply").returncode == 0
    assert f.read_bytes() == first
    assert rig.run("hooks", "install", "--project", proj).returncode == 0  # re-diff: nothing to change
    assert f.read_bytes() == first


def seed_settings(proj):
    cfg = {
        "permissions": {"allow": ["Bash(ls:*)"]},
        "env": {"FOO": "bar"},
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "echo mine-stop"}]}],
            "PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "echo mine-edit"}]}],
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine-pre"}]}],
        },
    }
    d = proj / ".claude"
    d.mkdir(parents=True)
    (d / "settings.local.json").write_text(json.dumps(cfg, indent=2))
    return cfg


def test_L08_install_merges_without_removing_existing_entries(rig, tmp_path):
    proj = tmp_path / "proj"
    orig = seed_settings(proj)
    assert rig.run("hooks", "install", "--project", proj, "--apply").returncode == 0
    got = json.loads((proj / ".claude" / "settings.local.json").read_text())
    assert got["permissions"] == orig["permissions"] and got["env"] == orig["env"]
    for entry in orig["hooks"]["PreToolUse"]:
        assert entry in got["hooks"]["PreToolUse"], "existing PreToolUse entries must be kept unchanged"
    assert any("hook guard" in c for _, c in commands(got)["PreToolUse"])
    cmds = commands(got)
    flat = [c for _, c in cmds["Stop"]]
    assert "echo mine-stop" in flat and any("lsf.py" in c for c in flat)
    assert ("Edit", "echo mine-edit") in cmds["PostToolUse"]
    assert any(m == "Bash" and "lsf.py" in c for m, c in cmds["PostToolUse"])
    assert any("lsf.py" in c for _, c in cmds["SubagentStop"])


def test_L08_uninstall_removes_only_its_own_entries(rig, tmp_path):
    proj = tmp_path / "proj"
    orig = seed_settings(proj)
    rig.run("hooks", "install", "--project", proj, "--apply")
    f = proj / ".claude" / "settings.local.json"
    before = f.read_bytes()
    assert rig.run("hooks", "uninstall", "--project", proj).returncode == 0
    assert f.read_bytes() == before, "uninstall without --apply must not write"
    assert rig.run("hooks", "uninstall", "--project", proj, "--apply").returncode == 0
    got = json.loads(f.read_text())
    got["hooks"] = {k: v for k, v in got["hooks"].items() if v}
    assert got == orig
    assert rig.run("hooks", "uninstall", "--project", proj, "--apply").returncode == 0  # idempotent
    assert json.loads(f.read_text()).get("permissions") == orig["permissions"]


def test_L08_install_refuses_malformed_settings_untouched(rig, tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    f = proj / ".claude" / "settings.local.json"
    f.write_text("{ not json")
    p = rig.run("hooks", "install", "--project", proj, "--apply")
    assert p.returncode == 1
    assert f.read_text() == "{ not json"


def test_L08_install_requires_project(rig):
    assert rig.run("hooks", "install").returncode == 2


@pytest.mark.parametrize("payload", [
    "", "not json", "{", "[]", "null", "42", '"str"', '{"hook_event_name": 5, "tool_input": "x"}',
    '{"tool_input": {"command": {"nested": 1}}}', "\xff\xfe garbage", "{" * 5000, "x" * 300000,
], ids=["empty", "text", "open-brace", "list", "null", "number", "string", "wrong-types", "nested-command",
        "latin1", "deep-braces", "huge"])
def test_L08_hook_never_fails_on_malformed_input(inited, payload):
    for event in EVENTS:
        p = run_hook(inited, event, payload)
        assert p.returncode == 0
        assert p.stdout == "" and p.stderr == ""


def test_L08_hook_survives_binary_stdin(inited):
    p = run_hook(inited, "Stop", bytes(range(256)) * 10)
    assert p.returncode == 0 and p.stdout == b"" and p.stderr == b""


def test_L08_hook_without_lsf_state_still_exits_0_quietly(rig, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    p = run_hook(rig, "Stop", {"hook_event_name": "Stop"}, cwd=bare)
    assert p.returncode == 0 and p.stdout == "" and p.stderr == ""


def test_L08_hook_survives_unwritable_events(inited):
    (inited.lsf_dir / "events.jsonl").unlink(missing_ok=True)
    (inited.lsf_dir / "events.jsonl").mkdir()
    p = run_hook(inited, "Stop", {"hook_event_name": "Stop"})
    assert p.returncode == 0 and p.stdout == ""


def test_L08_subagent_stop_records_role_and_source(inited):
    p = run_hook(inited, "SubagentStop", {"hook_event_name": "SubagentStop", "agent_type": "implement",
                                          "session_id": "s1"})
    assert p.returncode == 0 and p.stdout == ""
    e = inited.events()[-1]
    assert e["role"] == "implement" and e["source"] == "hook"


def test_L08_stop_records_an_event(inited):
    run_hook(inited, "Stop", {"hook_event_name": "Stop", "session_id": "s1"})
    assert [e["source"] for e in inited.events()] == ["hook"]


def test_L08_post_tool_use_only_records_git_commit(inited):
    other = run_hook(inited, "PostToolUse", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                             "tool_input": {"command": "ls -la"}})
    assert other.returncode == 0 and inited.events() == []
    run_hook(inited, "PostToolUse", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                     "tool_input": {"command": "git commit -m 'add thing'"}})
    evs = inited.events()
    assert len(evs) == 1 and "Bash" in json.dumps(evs[0]) and evs[0]["source"] == "hook"


def test_L08_summary_is_capped_at_200_and_redacted(inited):
    secret = "sk-" + "Qw3rTy9u" * 4
    cmd = "git commit -m " + ("x" * 500) + " " + secret
    run_hook(inited, "PostToolUse", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                     "tool_input": {"command": cmd}})
    run_hook(inited, "PostToolUse", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                     "tool_input": {"command": "git commit -m " + secret}})
    text = (inited.lsf_dir / "events.jsonl").read_text()
    assert secret not in text
    for e in inited.events():
        assert len(e["note"]) <= 200
