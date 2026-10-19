"""Unit tests for the hook core (TB-04). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

import factory.hooks as hooks_pkg
from factory.agents.profile import parse_profile
from factory.hooks import core, registry
from factory.hooks.core import (
    Decision, HookConfig, HookResult, Payload, PayloadError, parse_payload, run_hook,
)

ROOT = Path(__file__).resolve().parents[2]


def profile(**extra):
    data = {"schema_version": 1, "project": {"name": "demo"}, "paths": {"eval": ["evals/**"]}}
    data.update(extra)
    return parse_profile(data)


def cfg(tmp_path, **extra):
    return HookConfig.from_profile(profile(**extra), tmp_path)


def pj(event, **kw):
    d = {"session_id": "s", "cwd": "/x", "hook_event_name": event, "permission_mode": "default"}
    d.update(kw)
    return json.dumps(d)


PRE = pj("PreToolUse", tool_name="Write", tool_input={"file_path": "a"})


# ---- parse_payload -------------------------------------------------------------------------
def test_parse_pretooluse():
    p = parse_payload(PRE)
    assert isinstance(p, Payload)
    assert (p.event, p.tool_name, p.tool_input, p.cwd) == ("PreToolUse", "Write", {"file_path": "a"}, "/x")
    assert p.agent_type is None and p.agent_id is None
    assert p.last_assistant_message is None and p.agent_transcript_path is None
    assert p.raw["session_id"] == "s"


def test_parse_posttooluse_keeps_response_in_raw():
    p = parse_payload(pj("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response={"x": 1}))
    assert p.raw["tool_response"] == {"x": 1}


def test_parse_subagent_stop_fields():
    p = parse_payload(pj("SubagentStop", agent_id="i", agent_type="test", agent_transcript_path="/t",
                         last_assistant_message="done", stop_hook_active=False))
    assert (p.agent_id, p.agent_type, p.agent_transcript_path, p.last_assistant_message) == (
        "i", "test", "/t", "done")
    assert p.tool_input == {}


def test_parse_stop_and_session_start():
    assert parse_payload(pj("Stop", last_assistant_message="m")).last_assistant_message == "m"
    assert parse_payload(pj("SessionStart")).event == "SessionStart"


def test_parse_subagent_fields_on_pretooluse():
    p = parse_payload(pj("PreToolUse", tool_name="Read", tool_input={}, agent_type="implement", agent_id="a1"))
    assert p.agent_type == "implement" and p.agent_id == "a1"


@pytest.mark.parametrize("text", ["", "not json", "[1]", '"s"', "null", "{}", '{"hook_event_name": ""}',
                                  '{"hook_event_name": 3}', '{"hook_event_name": "Stop", "tool_input": []}'])
def test_parse_errors(text):
    with pytest.raises(PayloadError):
        parse_payload(text)


# ---- Decision ------------------------------------------------------------------------------
def test_decision_validation():
    assert Decision("allow").reason == ""
    with pytest.raises(ValueError):
        Decision("maybe", "x")
    for kind in ("deny", "ask", "block"):
        with pytest.raises(ValueError):
            Decision(kind)
        with pytest.raises(ValueError):
            Decision(kind, "")
        assert Decision(kind, "r").kind == kind


# ---- run_hook mapping ----------------------------------------------------------------------
def run(decision_or_fn, text, tmp_path):
    fn = decision_or_fn if callable(decision_or_fn) else (lambda p, c: decision_or_fn)
    return run_hook(fn, text, cfg(tmp_path))


def test_pre_allow(tmp_path):
    assert run(Decision("allow"), PRE, tmp_path) == HookResult(0, "", "")


def test_pre_deny(tmp_path):
    r = run(Decision("deny", "no"), PRE, tmp_path)
    assert (r.exit_code, r.stdout, r.stderr) == (2, "", "no")


def test_pre_ask(tmp_path):
    r = run(Decision("ask", "sure?"), PRE, tmp_path)
    assert r.exit_code == 0 and r.stderr == ""
    assert json.loads(r.stdout) == {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "sure?"}}


def test_pre_block_is_deny(tmp_path):
    r = run(Decision("block", "b"), PRE, tmp_path)
    assert (r.exit_code, r.stderr) == (2, "b")


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_stop_mapping(tmp_path, event):
    text = pj(event)
    assert run(Decision("allow"), text, tmp_path) == HookResult(0, "", "")
    for kind in ("block", "deny", "ask"):
        r = run(Decision(kind, "why"), text, tmp_path)
        assert r.exit_code == 0 and r.stderr == ""
        assert json.loads(r.stdout) == {"decision": "block", "reason": "why"}


@pytest.mark.parametrize("event", ["PostToolUse", "SessionStart"])
def test_passive_events(tmp_path, event):
    text = pj(event, tool_name="Bash", tool_input={})
    assert run(Decision("allow"), text, tmp_path) == HookResult(0, "", "")
    for kind in ("deny", "ask", "block"):
        r = run(Decision(kind, "note"), text, tmp_path)
        assert (r.exit_code, r.stdout, r.stderr) == (0, "", "note")


# ---- fail closed ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["", "garbage", "[]", "{}", pj("Bogus")])
def test_malformed_or_unknown_event_denies(tmp_path, text):
    called = []
    r = run(lambda p, c: called.append(1) or Decision("allow"), text, tmp_path)
    assert r.exit_code == 2 and r.stderr.startswith("hook error:") and not called


def boom(p, c):
    raise RuntimeError("kaboom")


def test_exception_pre_denies(tmp_path):
    r = run(boom, PRE, tmp_path)
    assert r.exit_code == 2 and r.stderr.startswith("hook error:") and "kaboom" in r.stderr


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_exception_stop_blocks(tmp_path, event):
    r = run(boom, pj(event), tmp_path)
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and out["reason"].startswith("hook error:")


@pytest.mark.parametrize("event", ["PostToolUse", "SessionStart"])
def test_exception_passive_exit0(tmp_path, event):
    r = run(boom, pj(event), tmp_path)
    assert r.exit_code == 0 and r.stdout == "" and r.stderr.startswith("hook error:")


def test_non_decision_return_fails_closed(tmp_path):
    r = run(lambda p, c: "allow", PRE, tmp_path)
    assert r.exit_code == 2 and r.stderr.startswith("hook error:")
    r = run(lambda p, c: None, pj("Stop"), tmp_path)
    assert json.loads(r.stdout)["reason"].startswith("hook error:")


def test_base_exception_subclass_exit_never_other(tmp_path):
    for fn in (boom, lambda p, c: Decision("allow"), lambda p, c: Decision("deny", "x")):
        for text in (PRE, pj("Stop"), pj("PostToolUse"), pj("SessionStart"), "bad"):
            assert run(fn, text, tmp_path).exit_code in (0, 2)


# ---- HookConfig ----------------------------------------------------------------------------
def test_config_resolves(tmp_path):
    c = cfg(tmp_path, main_session_role="review", checks={"test": "pytest"},
            one_way_door_patterns=["x"], secret_allow_patterns=["y"],
            paths={"eval": ["evals/**"], "held_out": ["h/**"], "frozen_tests": ["t/**"],
                   "baseline_update": ["b/**"], "ledger_dir": "led"})
    assert c.project_root == tmp_path
    assert c.eval_globs == ("evals/**",) and c.held_out == ("h/**",)
    assert c.frozen_tests == ("t/**",) and c.baseline_update == ("b/**",)
    assert c.ledger_dir == tmp_path / "led"
    assert c.main_session_role == "review"
    assert c.checks.test == "pytest"
    assert c.one_way_door_patterns == ("x",) and c.secret_allow_patterns == ("y",)
    assert c.profile.project.name == "demo"


def test_config_role_mapping(tmp_path):
    c = cfg(tmp_path)
    assert c.role_for(parse_payload(PRE)) == "orchestrator"
    assert c.role_for(parse_payload(pj("PreToolUse", agent_type="implement"))) == "implement"
    c2 = cfg(tmp_path, main_session_role="design")
    assert c2.role_for(parse_payload(PRE)) == "design"
    assert c2.role_for(parse_payload(pj("Stop", agent_type="weird"))) == "weird"


def test_config_frozen_and_root_type(tmp_path):
    c = HookConfig.from_profile(profile(), str(tmp_path))
    assert isinstance(c.project_root, Path)
    with pytest.raises(Exception):
        c.project_root = tmp_path  # type: ignore[misc]


def test_reexports():
    for name in ("Payload", "Decision", "HookResult", "HookConfig", "PayloadError", "parse_payload", "run_hook"):
        assert getattr(hooks_pkg, name) is getattr(core, name)


# ---- registry ------------------------------------------------------------------------------
EIGHT = {"path_guard", "blindness_guard", "secrets_guard", "bash_guard", "stop_gate", "subagent_stop",
         "ledger_audit", "session_start"}


def test_hook_ids():
    assert set(registry.HOOK_IDS) == EIGHT and len(registry.HOOK_IDS) == 8


def test_unknown_id():
    with pytest.raises(registry.UnknownHook):
        registry.get_hook("nope")


def test_missing_module_gives_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_cache", {})
    monkeypatch.setattr(registry.importlib, "import_module",
                        lambda n: (_ for _ in ()).throw(ModuleNotFoundError(name=n)))
    h = registry.get_hook("path_guard")
    r = run_hook(h.decide, PRE, cfg(tmp_path))
    assert r.exit_code == 2 and "hook not implemented" in r.stderr
    r = run_hook(h.decide, pj("Stop"), cfg(tmp_path))
    assert "hook not implemented" in json.loads(r.stdout)["reason"]


def test_module_discovery_without_editing_registry(monkeypatch):
    mod = types.ModuleType("factory.hooks.bash_guard")
    mod.decide = lambda p, c: Decision("allow")
    mod.record = lambda p, c: None
    monkeypatch.setattr(registry, "_cache", {})
    monkeypatch.setattr(registry.importlib, "import_module", lambda n: mod)
    h = registry.get_hook("bash_guard")
    assert h.decide is mod.decide and h.record is mod.record and h.emit is None


def test_module_without_decide_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_cache", {})
    monkeypatch.setattr(registry.importlib, "import_module", lambda n: types.ModuleType(n))
    r = run_hook(registry.get_hook("stop_gate").decide, pj("Stop"), cfg(tmp_path))
    assert json.loads(r.stdout)["reason"].startswith("hook error:")


def test_import_error_inside_module_is_not_stubbed(monkeypatch):
    def bad(n):
        raise ImportError("broken dep", name="other_dep")
    monkeypatch.setattr(registry, "_cache", {})
    monkeypatch.setattr(registry.importlib, "import_module", bad)
    with pytest.raises(ImportError):
        registry.get_hook("secrets_guard")


def test_register_explicit(monkeypatch):
    monkeypatch.setattr(registry, "_cache", {})
    d = lambda p, c: Decision("allow")  # noqa: E731
    registry.register("session_start", d, emit=lambda p, c: "ctx")
    assert registry.get_hook("session_start").decide is d
    with pytest.raises(registry.UnknownHook):
        registry.register("zzz", d)


def test_registry_is_lazy():
    code = ("import sys, factory.hooks, factory.hooks.registry as r;"
            "assert not any(m.startswith('factory.hooks.') and m.rsplit('.',1)[1] in r.HOOK_IDS "
            "for m in sys.modules)")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


# ---- command line --------------------------------------------------------------------------
PROFILE_YAML = "schema_version: 1\nproject: {name: demo}\npaths: {eval: ['evals/**']}\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text(PROFILE_YAML)
    return tmp_path


def invoke(hook_id, stdin, monkeypatch, capsys, env=None, cwd=None):
    from factory.hooks import __main__ as m
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    monkeypatch.delenv("FACTORY_PROFILE", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    argv = [hook_id] if hook_id is not None else []
    code = m.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def install(monkeypatch, hook_id, decide, record=None, emit=None):
    cache = dict(registry._cache)
    monkeypatch.setattr(registry, "_cache", cache)
    registry.register(hook_id, decide, record, emit)


def test_cli_unknown_hook(monkeypatch, capsys):
    code, out, err = invoke("nope", PRE, monkeypatch, capsys)
    assert code == 2 and "unknown hook" in err
    code, out, err = invoke(None, PRE, monkeypatch, capsys)
    assert code == 2 and "unknown hook" in err


def test_cli_deny_and_profile_default(project, monkeypatch, capsys):
    seen = {}
    def d(p, c):
        seen["root"] = c.project_root
        return Decision("deny", "blocked!")
    install(monkeypatch, "path_guard", d)
    code, out, err = invoke("path_guard", pj("PreToolUse", cwd=str(project), tool_name="Write"),
                            monkeypatch, capsys)
    assert code == 2 and "blocked!" in err and out == "" and seen["root"] == project


def test_cli_factory_profile_wins(project, tmp_path_factory, monkeypatch, capsys):
    other = tmp_path_factory.mktemp("o") / "p.yaml"
    other.write_text(PROFILE_YAML.replace("demo", "other"))
    seen = {}
    install(monkeypatch, "path_guard", lambda p, c: seen.setdefault("n", c.profile.project.name) and Decision("allow"))
    code, *_ = invoke("path_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys,
                      env={"FACTORY_PROFILE": str(other)})
    assert code == 0 and seen["n"] == "other"


def test_cli_missing_profile_fails_closed(tmp_path, monkeypatch, capsys):
    install(monkeypatch, "path_guard", lambda p, c: Decision("allow"))
    code, out, err = invoke("path_guard", pj("PreToolUse", cwd=str(tmp_path)), monkeypatch, capsys)
    assert code == 2 and err.startswith("hook error:") and "Traceback" not in err
    install(monkeypatch, "stop_gate", lambda p, c: Decision("allow"))
    code, out, err = invoke("stop_gate", pj("Stop", cwd=str(tmp_path)), monkeypatch, capsys)
    assert code == 0 and json.loads(out)["reason"].startswith("hook error:")
    code, out, err = invoke("session_start", pj("SessionStart", cwd=str(tmp_path)), monkeypatch, capsys)
    assert code == 0 and err.startswith("hook error:")


def test_cli_invalid_profile_fails_closed(project, monkeypatch, capsys):
    (project / ".factory" / "profile.yaml").write_text("schema_version: 2\n")
    code, out, err = invoke("bash_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys)
    assert code == 2 and err.startswith("hook error:")
    (project / ".factory" / "profile.yaml").write_text(": : [")
    code, out, err = invoke("bash_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys)
    assert code == 2 and err.startswith("hook error:")


def test_cli_bad_stdin(monkeypatch, capsys):
    code, out, err = invoke("path_guard", "not json", monkeypatch, capsys)
    assert code == 2 and err.startswith("hook error:")


def test_cli_record_runs_and_errors_do_not_change_exit(project, monkeypatch, capsys):
    calls = []
    install(monkeypatch, "ledger_audit", lambda p, c: Decision("allow"),
            record=lambda p, c: calls.append(p.event))
    code, *_ = invoke("ledger_audit", pj("SubagentStop", cwd=str(project)), monkeypatch, capsys)
    assert code == 0 and calls == ["SubagentStop"]

    def bad(p, c):
        raise OSError("disk")
    install(monkeypatch, "ledger_audit", lambda p, c: Decision("block", "no"), record=bad)
    code, out, err = invoke("ledger_audit", pj("SubagentStop", cwd=str(project)), monkeypatch, capsys)
    assert code == 0 and json.loads(out)["reason"] == "no" and "disk" in err
    install(monkeypatch, "path_guard", lambda p, c: Decision("deny", "d"), record=bad)
    code, out, err = invoke("path_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys)
    assert code == 2 and "d" in err and "disk" in err


def test_cli_emit_only_for_session_start(project, monkeypatch, capsys):
    install(monkeypatch, "session_start", lambda p, c: Decision("allow"), emit=lambda p, c: "CONTEXT")
    code, out, err = invoke("session_start", pj("SessionStart", cwd=str(project)), monkeypatch, capsys)
    assert code == 0 and out == "CONTEXT"
    install(monkeypatch, "path_guard", lambda p, c: Decision("allow"), emit=lambda p, c: "CONTEXT")
    code, out, err = invoke("path_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys)
    assert code == 0 and out == ""

    def bad(p, c):
        raise ValueError("emit broke")
    install(monkeypatch, "session_start", lambda p, c: Decision("allow"), emit=bad)
    code, out, err = invoke("session_start", pj("SessionStart", cwd=str(project)), monkeypatch, capsys)
    assert code == 0 and out == "" and "emit broke" in err


def test_cli_stub_hook_not_implemented(project, monkeypatch, capsys):
    monkeypatch.setattr(registry, "_cache", {})
    monkeypatch.setattr(registry.importlib, "import_module",
                        lambda n: (_ for _ in ()).throw(ModuleNotFoundError(name=n)))
    code, out, err = invoke("path_guard", pj("PreToolUse", cwd=str(project)), monkeypatch, capsys)
    assert code == 2 and "hook not implemented" in err


def test_cli_subprocess_end_to_end(project):
    proc = subprocess.run([sys.executable, "-m", "factory.hooks", "nope"], input=PRE, text=True,
                          capture_output=True, cwd=ROOT)
    assert proc.returncode == 2 and "unknown hook" in proc.stderr
    proc = subprocess.run([sys.executable, "-m", "factory.hooks", "path_guard"],
                          input=pj("PreToolUse", cwd=str(project), tool_name="Write"),
                          text=True, capture_output=True, cwd=ROOT)
    assert proc.returncode in (0, 2) and "Traceback" not in proc.stderr
