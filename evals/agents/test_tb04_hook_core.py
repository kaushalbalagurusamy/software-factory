"""TB-04 hook core evals: payload parsing, decision adapter, fail-closed behaviour, registry and command line.

Sources (the only sources of expectations): docs/prds/TB-04-hook-core.md (behaviours 1 to 8) and
docs/contracts/hook-io.md (payload fields, Python API, protocol adapter table, command line). R-09 from
docs/factory/requirements.md. Implementation is imported lazily through lib.need so a missing producer is BLOCKED.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import socket
import subprocess
import sys

import pytest

from evals.agents import lib

TB = "04"


def case(cid: str, *values, reqs=("R-09",)):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.param(*values, marks=pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs)), id=cid)


def mark(cid: str, reqs=("R-09",)):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs))


# ---------------------------------------------------------------- helpers

def _core(*attrs):
    return lib.need("factory.hooks.core", *attrs)


def _cfg(tmp_path, profile="base"):
    core = _core("HookConfig")
    prof = lib.need("factory.agents.profile", "load_profile")
    root = lib.make_project(tmp_path, profile)
    return root, core.HookConfig.from_profile(prof.load_profile(root / ".factory" / "profile.yaml"), root)


def _need_cli(*hook_modules):
    _core("run_hook", "parse_payload", "HookConfig")
    lib.need("factory.agents.profile", "load_profile")
    if importlib.util.find_spec("factory.hooks.__main__") is None:
        pytest.skip("BLOCKED: factory.hooks.__main__ not available")
    for m in hook_modules:
        lib.need(m, "decide")


def _env(extra=None):
    e = {k: v for k, v in os.environ.items() if k != "FACTORY_PROFILE"}
    e["PYTHONPATH"] = str(lib.REPO) + os.pathsep + e.get("PYTHONPATH", "")
    e.update(extra or {})
    return e


def _cli_raw(hook_id: str, stdin_text: str, cwd, env=None):
    return subprocess.run([sys.executable, "-m", "factory.hooks", hook_id], input=stdin_text, text=True,
                          capture_output=True, cwd=str(cwd), env=_env(env), timeout=60)


_PRELUDE = r'''
import importlib.abc, json, runpy, sys, types
cfg = json.loads(sys.argv[1])
blocked = set(cfg["blocked"])
class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name in blocked:
            raise ModuleNotFoundError("No module named %r" % name, name=name)
        return None
sys.meta_path.insert(0, _Block())
import factory.hooks as _pkg
for name in blocked:
    sys.modules.pop(name, None)
    short = name.rsplit(".", 1)[1]
    if short in _pkg.__dict__:
        delattr(_pkg, short)
for name, src in cfg["fakes"].items():
    m = types.ModuleType(name)
    exec(src, m.__dict__)
    sys.modules[name] = m
    setattr(_pkg, name.rsplit(".", 1)[1], m)
sys.argv = ["factory.hooks", cfg["hook_id"]]
runpy.run_module("factory.hooks", run_name="__main__", alter_sys=True)
'''


def _cli_patched(hook_id: str, pl: dict, cwd, blocked=(), fakes=None):
    """Run the real command line with some hook modules made unimportable or replaced by a fake.

    Grounded in TB-04 behaviour 8 and the OWN lists of TB-05..TB-11: hook id <id> lives in module factory.hooks.<id>.
    """
    arg = json.dumps({"blocked": list(blocked), "fakes": fakes or {}, "hook_id": hook_id})
    return subprocess.run([sys.executable, "-c", _PRELUDE, arg], input=json.dumps(pl), text=True,
                          capture_output=True, cwd=str(cwd), env=_env(), timeout=60)


def _fake(decide_body: str, extra: str = "") -> str:
    return ("from factory.hooks.core import Decision\n"
            f"def decide(payload, cfg):\n    {decide_body}\n" + extra)


PRE = {"session_id": "s1", "cwd": "/tmp/x", "hook_event_name": "PreToolUse", "permission_mode": "default",
       "tool_name": "Read", "tool_input": {"file_path": "/tmp/x/src/app.py"}}
STOP = {"session_id": "s1", "cwd": "/tmp/x", "hook_event_name": "Stop", "permission_mode": "default",
        "last_assistant_message": "done", "stop_hook_active": False}
SUBSTOP = {"session_id": "s1", "cwd": "/tmp/x", "hook_event_name": "SubagentStop", "permission_mode": "default",
           "agent_id": "a7", "agent_type": "research", "agent_transcript_path": "/tmp/x/t.jsonl",
           "last_assistant_message": "report", "stop_hook_active": False}
POST = {**PRE, "hook_event_name": "PostToolUse", "tool_response": {"ok": True}}
START = {"session_id": "s1", "cwd": "/tmp/x", "hook_event_name": "SessionStart", "permission_mode": "default"}


def _with_cwd(pl, root):
    return {**pl, "cwd": str(root)}


def _raise(payload, cfg):
    raise RuntimeError("decide exploded")


def _const(kind, reason=""):
    core = _core("Decision")

    def decide(payload, cfg):
        return core.Decision(kind=kind, reason=reason)
    return decide


# ---------------------------------------------------------------- behaviour 1: parse_payload

@mark("TB04-G-001")
def test_parse_pretooluse_fields():
    """B1 / hook-io Payload: parse_payload returns a Payload for valid PreToolUse JSON; event=hook_event_name,
    tool_name, tool_input, cwd, raw = full parsed JSON; agent_type/agent_id absent in the main session."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(PRE))
    assert p.event == "PreToolUse"
    assert p.tool_name == "Read"
    assert p.tool_input == {"file_path": "/tmp/x/src/app.py"}
    assert p.cwd == "/tmp/x"
    assert p.agent_type is None and p.agent_id is None
    assert p.raw == PRE


@mark("TB04-G-002")
def test_parse_subagentstop_fields():
    """B1: 'including sub-agent fields when present'; SubagentStop carries agent_id, agent_type,
    agent_transcript_path, last_assistant_message."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(SUBSTOP))
    assert p.event == "SubagentStop"
    assert p.agent_id == "a7" and p.agent_type == "research"
    assert p.agent_transcript_path == "/tmp/x/t.jsonl"
    assert p.last_assistant_message == "report"
    assert p.raw == SUBSTOP


@mark("TB04-G-003")
def test_parse_invalid_json_raises():
    """B1: parse_payload 'raises PayloadError for invalid JSON'."""
    core = _core("parse_payload", "PayloadError")
    with pytest.raises(core.PayloadError):
        core.parse_payload("{not json")


@mark("TB04-D-001")
def test_parse_posttooluse():
    """B1 / hook-io: PostToolUse is 'as PreToolUse plus tool_response'; the full JSON is kept in raw."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(POST))
    assert p.event == "PostToolUse" and p.tool_name == "Read"
    assert p.tool_input == PRE["tool_input"]
    assert p.raw["tool_response"] == {"ok": True}


@mark("TB04-D-002")
def test_parse_stop():
    """B1 / hook-io: Stop carries last_assistant_message."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(STOP))
    assert p.event == "Stop" and p.last_assistant_message == "done"
    assert p.tool_name is None and p.tool_input == {}


@mark("TB04-D-003")
def test_parse_sessionstart():
    """B1 / hook-io Payload: tool_input is '{} when absent'; SessionStart has only common fields."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(START))
    assert p.event == "SessionStart"
    assert p.tool_name is None and p.tool_input == {}
    assert p.agent_type is None


@mark("TB04-D-004")
def test_parse_subagent_pretooluse_agent_fields():
    """B1 / hook-io: optional agent_id and agent_type are present only inside a sub-agent and are parsed."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps({**PRE, "agent_id": "a9", "agent_type": "implement"}))
    assert p.agent_type == "implement" and p.agent_id == "a9"


@pytest.mark.parametrize("text", [
    case("TB04-D-005", "[1, 2]"),
    case("TB04-D-006", "42"),
    case("TB04-D-007", '"a string"'),
    case("TB04-D-008", "null"),
    case("TB04-D-009", ""),
])
def test_parse_non_object_raises(text):
    """B1: PayloadError for 'invalid JSON, a non-object'."""
    core = _core("parse_payload", "PayloadError")
    with pytest.raises(core.PayloadError):
        core.parse_payload(text)


@mark("TB04-D-010")
def test_parse_missing_event_raises():
    """B1: PayloadError for 'a missing hook_event_name'."""
    core = _core("parse_payload", "PayloadError")
    bad = {k: v for k, v in PRE.items() if k != "hook_event_name"}
    with pytest.raises(core.PayloadError):
        core.parse_payload(json.dumps(bad))


@mark("TB04-D-011")
def test_payload_is_frozen():
    """hook-io: Payload is '@dataclass(frozen=True)'."""
    core = _core("parse_payload")
    p = core.parse_payload(json.dumps(PRE))
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.event = "Stop"


@mark("TB04-D-012")
def test_decision_is_frozen():
    """hook-io: Decision is '@dataclass(frozen=True)'."""
    core = _core("Decision")
    d = core.Decision(kind="deny", reason="r")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.kind = "allow"


# ---------------------------------------------------------------- behaviour 2: run_hook mapping

@mark("TB04-G-004")
def test_run_hook_allow(tmp_path):
    """B2 / adapter table: allow -> exit 0, empty stdout (PreToolUse)."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("allow"), json.dumps(_with_cwd(PRE, root)), cfg)
    assert r.exit_code == 0 and r.stdout == ""


@mark("TB04-G-005")
def test_run_hook_deny(tmp_path):
    """B2 / adapter table: deny (PreToolUse) -> exit 2, reason on stderr."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("deny", "denied-because-7731"), json.dumps(_with_cwd(PRE, root)), cfg)
    assert r.exit_code == 2
    assert "denied-because-7731" in r.stderr


@mark("TB04-G-006")
def test_run_hook_ask(tmp_path):
    """B2 / adapter table: ask (PreToolUse) -> exit 0, stdout {"hookSpecificOutput":{"hookEventName":"PreToolUse",
    "permissionDecision":"ask","permissionDecisionReason":"<reason>"}}."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("ask", "approve deploy"), json.dumps(_with_cwd(PRE, root)), cfg)
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                           "permissionDecisionReason": "approve deploy"}}


@mark("TB04-G-007")
def test_run_hook_block_stop(tmp_path):
    """B2 / adapter table: block (Stop) -> exit 0, stdout {"decision":"block","reason":"<reason>"}."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("block", "no evidence"), json.dumps(_with_cwd(STOP, root)), cfg)
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {"decision": "block", "reason": "no evidence"}


@mark("TB04-D-013")
def test_run_hook_block_subagentstop(tmp_path):
    """B2 / adapter table: block (SubagentStop) -> exit 0, stdout {"decision":"block","reason":"<reason>"}."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("block", "missing sources"), json.dumps(_with_cwd(SUBSTOP, root)), cfg)
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {"decision": "block", "reason": "missing sources"}


@mark("TB04-D-014")
def test_run_hook_allow_stop(tmp_path):
    """B2 / adapter table: allow (Stop and SubagentStop) -> exit 0, empty stdout."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    for pl in (STOP, SUBSTOP):
        r = core.run_hook(_const("allow"), json.dumps(_with_cwd(pl, root)), cfg)
        assert r.exit_code == 0 and r.stdout == ""


@mark("TB04-D-015")
def test_run_hook_exit_codes_only_0_or_2(tmp_path):
    """B2: run_hook 'never raises and never returns an exit code other than 0 or 2' (all used table cells plus
    malformed input and a raising decide)."""
    core = _core("run_hook", "Decision")
    root, cfg = _cfg(tmp_path)
    combos = [(PRE, k) for k in ("allow", "deny", "ask")] + [(p, k) for p in (STOP, SUBSTOP) for k in ("allow", "block")]
    for pl, kind in combos:
        r = core.run_hook(_const(kind, "r"), json.dumps(_with_cwd(pl, root)), cfg)
        assert r.exit_code in (0, 2)
    for text in ("", "{", "[]", json.dumps({"cwd": str(root)})):
        assert core.run_hook(_const("allow"), text, cfg).exit_code in (0, 2)
    for pl in (PRE, POST, STOP, SUBSTOP, START):
        assert core.run_hook(_raise, json.dumps(_with_cwd(pl, root)), cfg).exit_code in (0, 2)


# ---------------------------------------------------------------- behaviour 3: fail closed

@mark("TB04-G-008")
def test_run_hook_decide_raises_pretooluse(tmp_path):
    """B3 / adapter 'Fail closed': an exception inside decide gives a deny (PreToolUse) whose reason starts
    'hook error:' (deny = exit 2, reason on stderr)."""
    core = _core("run_hook")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_raise, json.dumps(_with_cwd(PRE, root)), cfg)
    assert r.exit_code == 2
    assert r.stderr.lstrip().startswith("hook error:")


@pytest.mark.parametrize("pl", [case("TB04-D-016", STOP), case("TB04-D-017", SUBSTOP)])
def test_run_hook_decide_raises_stop(tmp_path, pl):
    """B3: an exception inside decide gives a block (Stop, SubagentStop) whose reason starts 'hook error:'
    (block = exit 0, stdout {"decision":"block","reason":...})."""
    core = _core("run_hook")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_raise, json.dumps(_with_cwd(pl, root)), cfg)
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["decision"] == "block"
    assert out["reason"].startswith("hook error:")


@pytest.mark.parametrize("pl", [case("TB04-D-018", POST), case("TB04-D-019", START)])
def test_run_hook_decide_raises_non_guard_events(tmp_path, pl):
    """B3: 'for SessionStart and PostToolUse it gives exit 0 with the error on stderr'."""
    core = _core("run_hook")
    root, cfg = _cfg(tmp_path)
    r = core.run_hook(_raise, json.dumps(_with_cwd(pl, root)), cfg)
    assert r.exit_code == 0
    assert r.stderr.strip() != ""


def _assert_failed_closed(r_exit, r_stdout, r_stderr):
    """Event unknown (see ambiguities-B A-04-1): either a deny (exit 2, reason on stderr starting 'hook error:')
    or a block (exit 0, stdout block JSON whose reason starts 'hook error:'). Never a silent allow."""
    assert r_exit in (0, 2)
    if r_exit == 2:
        assert "hook error:" in r_stderr
    else:
        out = json.loads(r_stdout)
        assert out["decision"] == "block" and out["reason"].startswith("hook error:")


@pytest.mark.parametrize("text", [
    case("TB04-D-020", "{this is not json"),
    case("TB04-D-021", json.dumps({"session_id": "s1", "tool_name": "Read", "tool_input": {}})),
])
def test_run_hook_malformed_fails_closed(tmp_path, text):
    """B3 / adapter: 'if the stdin text is not valid JSON, lacks hook_event_name ... run_hook returns a deny ... or
    block ... whose reason begins hook error:'; never an allow."""
    core = _core("run_hook", "Decision")
    _root, cfg = _cfg(tmp_path)
    r = core.run_hook(_const("allow"), text, cfg)
    _assert_failed_closed(r.exit_code, r.stdout, r.stderr)


# ---------------------------------------------------------------- behaviour 4: HookConfig

@pytest.mark.parametrize("prof", [case("TB04-D-022", "base"), case("TB04-D-023", "alt")])
def test_hookconfig_from_profile(tmp_path, prof):
    """B4 / hook-io: HookConfig.from_profile(profile, project_root) -> HookConfig for a valid profile."""
    core = _core("HookConfig")
    _root, cfg = _cfg(tmp_path, prof)
    assert isinstance(cfg, core.HookConfig)


@pytest.mark.parametrize("main_role,expected", [
    case("TB04-D-024", "implement", "deny"),
    case("TB04-D-025", None, "allow"),
])
def test_main_session_role_mapping(tmp_path, main_role, expected):
    """B4 / hook-io: 'a payload with no agent_type resolves to the profile's main_session_role' (default
    orchestrator). Observed through the blindness guard (TB-06 B1: applies only when the resolved role is implement)."""
    prof = lib.profile_dict("base") if main_role is None else lib.profile_dict("base", main_session_role=main_role)
    root = lib.make_project(tmp_path, prof, files={"evals/case_a.py": "x = 1\n"})
    d = lib.run_decide("factory.hooks.blindness_guard",
                       lib.payload(root, tool_name="Read", tool_input={"file_path": str(root / "evals/case_a.py")}), root)
    assert d.kind == expected


# ---------------------------------------------------------------- behaviours 5, 6, 8: registry and command line

@mark("TB04-G-009")
def test_cli_unknown_hook(tmp_path):
    """B5: 'an unknown id causes the command line to exit 2 with unknown hook'."""
    _need_cli()
    root = lib.make_project(tmp_path)
    r = lib.run_cli("no_such_hook_zz", lib.payload(root, tool_name="Read", tool_input={"file_path": "a"}), root)
    assert r.returncode == 2
    assert "unknown hook" in (r.stdout + r.stderr)


@mark("TB04-G-010")
def test_cli_missing_profile_fails_closed(tmp_path):
    """B6: 'a missing or invalid profile is a fail-closed result, not a traceback' (PreToolUse fail closed = exit 2)."""
    _need_cli("factory.hooks.path_guard")
    root = tmp_path / "noprof"
    root.mkdir()
    r = lib.run_cli("path_guard", lib.payload(root, tool_name="Write",
                                              tool_input={"file_path": str(root / "a.txt"), "content": "x"}), root)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr


@mark("TB04-D-026")
def test_cli_invalid_profile_fails_closed(tmp_path):
    """B6: an invalid profile (schema_version 2, rejected per profile contract) is fail closed, not a traceback."""
    _need_cli("factory.hooks.path_guard")
    root = lib.make_project(tmp_path, lib.profile_dict("base", schema_version=2))
    r = lib.run_cli("path_guard", lib.payload(root, tool_name="Write",
                                              tool_input={"file_path": str(root / "src/a.py"), "content": "x"},
                                              agent_type="implement"), root)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr


@mark("TB04-D-027")
def test_cli_factory_profile_env(tmp_path):
    """B6 / hook-io command line: loads the profile from $FACTORY_PROFILE (here the alt profile, no
    .factory/profile.yaml under cwd). Under alt, qa/cases/** is protected and evals/** is not (TB-06 B2)."""
    _need_cli("factory.hooks.blindness_guard")
    root = tmp_path / "envproj"
    (root / "qa/cases").mkdir(parents=True)
    (root / "qa/cases/c.py").write_text("x = 1\n")
    (root / "evals").mkdir()
    (root / "evals/e.py").write_text("x = 1\n")
    env = {"FACTORY_PROFILE": str(lib.PROFILES / "alt.yaml")}
    pl_deny = lib.payload(root, tool_name="Read", tool_input={"file_path": str(root / "qa/cases/c.py")}, agent_type="implement")
    pl_allow = lib.payload(root, tool_name="Read", tool_input={"file_path": str(root / "evals/e.py")}, agent_type="implement")
    r1 = lib.run_cli("blindness_guard", pl_deny, root, env=env)
    r2 = lib.run_cli("blindness_guard", pl_allow, root, env=env)
    assert r1.returncode == 2
    assert r2.returncode == 0 and r2.stdout.strip() == ""


@mark("TB04-D-028")
def test_cli_malformed_stdin_fails_closed(tmp_path):
    """B6 + B3: the command line runs through run_hook, so non-JSON stdin fails closed (deny or block with
    'hook error:'), never an allow and never a traceback."""
    _need_cli("factory.hooks.path_guard")
    root = lib.make_project(tmp_path)
    r = _cli_raw("path_guard", "{oops", root)
    assert "Traceback" not in r.stderr
    _assert_failed_closed(r.returncode, r.stdout, r.stderr)


@pytest.mark.parametrize("hook_id", [
    case("TB04-D-029", "path_guard"),
    case("TB04-D-030", "blindness_guard"),
    case("TB04-D-031", "secrets_guard"),
    case("TB04-D-032", "bash_guard"),
])
def test_cli_stub_for_missing_module_pretooluse(tmp_path, hook_id):
    """B8: 'Hooks modules that do not exist yet make their id resolve to a stub that fails closed with
    hook not implemented' (PreToolUse fail closed = exit 2, reason on stderr)."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Bash", tool_input={"command": "ls"}, agent_type="implement")
    r = _cli_patched(hook_id, pl, root, blocked=[f"factory.hooks.{hook_id}"])
    assert r.returncode == 2
    assert "hook not implemented" in r.stderr


@mark("TB04-D-033")
def test_cli_stub_for_missing_module_stop(tmp_path):
    """B8 + adapter: the stub fails closed with 'hook not implemented'; for Stop, fail closed is a block
    (exit 0, stdout {"decision":"block",...})."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, event="Stop", last_assistant_message="done", stop_hook_active=False)
    r = _cli_patched("stop_gate", pl, root, blocked=["factory.hooks.stop_gate"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "hook not implemented" in out["reason"]


@mark("TB04-D-034")
def test_cli_allow_via_fake(tmp_path):
    """B6 + adapter: allow -> exit 0 and nothing but whitespace on stdout."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root, fakes={"factory.hooks.path_guard": _fake('return Decision(kind="allow")')})
    assert r.returncode == 0 and r.stdout.strip() == ""


@mark("TB04-D-035")
def test_cli_deny_via_fake(tmp_path):
    """B6 + adapter: deny -> exit 2 with the reason on stderr."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root,
                     fakes={"factory.hooks.path_guard": _fake('return Decision(kind="deny", reason="fake-deny-3310")')})
    assert r.returncode == 2 and "fake-deny-3310" in r.stderr


@mark("TB04-D-036")
def test_cli_ask_via_fake(tmp_path):
    """B6 + adapter: ask -> exit 0, stdout is exactly the hookSpecificOutput JSON."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Bash", tool_input={"command": "x"})
    r = _cli_patched("bash_guard", pl, root,
                     fakes={"factory.hooks.bash_guard": _fake('return Decision(kind="ask", reason="approve x")')})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                           "permissionDecisionReason": "approve x"}}


@mark("TB04-D-037")
def test_cli_decide_raises_via_fake(tmp_path):
    """B3 + B6: an exception inside decide through the command line is a deny whose reason starts 'hook error:'."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root, fakes={"factory.hooks.path_guard": _fake('raise RuntimeError("x")')})
    assert r.returncode == 2
    assert r.stderr.lstrip().startswith("hook error:")


# ---------------------------------------------------------------- behaviour 7: record and emit

_RECORD_RAISES = "def record(payload, cfg):\n    raise RuntimeError('record-boom-4821')\n"


@mark("TB04-D-038")
def test_cli_record_error_keeps_allow(tmp_path):
    """B7 / hook-io: 'an exception in record is reported on stderr and never changes the exit code' (allow = 0)."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root,
                     fakes={"factory.hooks.path_guard": _fake('return Decision(kind="allow")', _RECORD_RAISES)})
    assert r.returncode == 0
    assert r.stderr.strip() != ""


@mark("TB04-D-039")
def test_cli_record_error_keeps_deny(tmp_path):
    """B7: a record exception never changes the exit code (deny stays exit 2)."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root, fakes={"factory.hooks.path_guard": _fake(
        'return Decision(kind="deny", reason="d")', _RECORD_RAISES)})
    assert r.returncode == 2


@mark("TB04-D-040")
def test_cli_emit_on_sessionstart(tmp_path):
    """B7 / hook-io: for SessionStart, emit(payload, cfg) text is printed on stdout as added context, exit 0."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, event="SessionStart")
    r = _cli_patched("session_start", pl, root, fakes={"factory.hooks.session_start": _fake(
        'return Decision(kind="allow")', "def emit(payload, cfg):\n    return 'CTX-MARKER-5531'\n")})
    assert r.returncode == 0
    assert "CTX-MARKER-5531" in r.stdout


@mark("TB04-D-041")
def test_cli_emit_not_for_pretooluse(tmp_path):
    """B7: 'emit output goes to stdout only for SessionStart'; a PreToolUse allow keeps stdout empty."""
    _need_cli()
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Read", tool_input={"file_path": "a"})
    r = _cli_patched("path_guard", pl, root, fakes={"factory.hooks.path_guard": _fake(
        'return Decision(kind="allow")', "def emit(payload, cfg):\n    return 'CTX-MARKER-9902'\n")})
    assert r.returncode == 0
    assert "CTX-MARKER-9902" not in r.stdout


# ---------------------------------------------------------------- R-09: no network call

@pytest.mark.parametrize("module,tool,tool_input,agent", [
    case("TB04-D-042", "factory.hooks.path_guard", "Write", {"file_path": "src/a.py", "content": "x"}, "implement"),
    case("TB04-D-043", "factory.hooks.blindness_guard", "Bash", {"command": "cat evals/case_a.py"}, "implement"),
    case("TB04-D-044", "factory.hooks.secrets_guard", "Write", {"file_path": "src/a.py", "content": "x = 1"}, "implement"),
    case("TB04-D-045", "factory.hooks.bash_guard", "Bash", {"command": "git push --force"}, "orchestrator"),
])
def test_hooks_make_no_network_call(tmp_path, monkeypatch, module, tool, tool_input, agent):
    """R-09: 'Hooks make no network call and no model call.' Sockets are made to fail loudly; decide must still
    return a Decision without trying to connect."""
    root = lib.make_project(tmp_path, files={"evals/case_a.py": "x = 1\n", "src/a.py": "y = 2\n"})
    attempts = []

    def trap(*a, **k):
        attempts.append(a)
        raise OSError("network disabled by eval")
    monkeypatch.setattr(socket.socket, "connect", trap)
    monkeypatch.setattr(socket.socket, "connect_ex", trap)
    monkeypatch.setattr(socket, "create_connection", trap)
    monkeypatch.setattr(socket, "getaddrinfo", trap)
    ti = {k: (str(root / v) if k == "file_path" else v) for k, v in tool_input.items()}
    d = lib.run_decide(module, lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent), root)
    assert d.kind in ("allow", "deny", "ask")
    assert attempts == []


# ---------------------------------------------------------------- R-24: published documentation

@pytest.mark.case("TB04-D-046", tier="diagnostic", tb="04", reqs=["R-24"])
def test_docs_hooks_core_md():
    """TB-04 Acceptance: 'Document the component in the docs/hooks/ file you own, with one example payload or call
    (requirement R-24).' OWN list names docs/hooks/core.md."""
    lib.need("factory.hooks.core")
    doc_path = lib.REPO / "docs" / "hooks" / "core.md"
    assert doc_path.is_file()
    text = doc_path.read_text()
    assert any(s in text for s in ("hook_event_name", "decide(", "python -m factory.hooks")), "one example payload or call"
