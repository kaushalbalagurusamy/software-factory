"""Unit tests for the secrets guard (TB-07). Unit coverage, not the acceptance gate.

R-23: no key-shaped literal appears in this file; synthetic keys are built from fragments.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import secrets_guard
from factory.hooks.core import Decision, HookConfig, parse_payload, run_hook
from factory.hooks.registry import get_hook

ALNUM = "Qw3rTy7uIo9pAs5dFg1hJk8lZx2cVb4n"  # 32 mixed alphanumerics, not a key shape on its own


def cfg(tmp_path, **extra):
    data = {"schema_version": 1, "project": {"name": "demo"}, "paths": {"eval": ["evals/**"]}}
    data.update(extra)
    return HookConfig.from_profile(parse_profile(data), tmp_path)


def payload(tool, **tool_input):
    return parse_payload(json.dumps({
        "session_id": "s", "cwd": "/x", "hook_event_name": "PreToolUse", "permission_mode": "default",
        "tool_name": tool, "tool_input": tool_input}))


def write(text, **kw):
    return payload("Write", file_path="a.txt", content=text, **kw)


def run(tmp_path, p, **extra):
    return secrets_guard.decide(p, cfg(tmp_path, **extra))


SHAPES = {
    "openrouter": "sk-" + "or-v1-" + "0123456789abcdef0123",
    "anthropic": "sk-" + "ant-" + "Ab3_-Ab3_-Ab3_-Ab3_-Ab3",
    "openai": "sk-" + ALNUM,
    "ghp": "gh" + "p_" + "Ab3_Ab3_Ab3_Ab3_Ab3_",
    "gho": "gh" + "o_" + "Ab3Ab3Ab3Ab3Ab3Ab3Ab",
    "ghs": "gh" + "s_" + "Ab3Ab3Ab3Ab3Ab3Ab3Ab",
    "github_pat": "github" + "_pat_" + "Ab3_Ab3_Ab3_Ab3_Ab3_",
    "glpat": "gl" + "pat-" + "Ab3-Ab3_Ab3-Ab3_Ab3-",
    "aws": "AK" + "IA" + "Q7ZP4MNB2XLC9RTD",
    "slack": "xo" + "xb-" + "1234567890",
    "google": "AI" + "za" + "Ab3_-Ab3_-Ab3_-Ab3_-Ab3_-Ab3_-Ab3_-",
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_key_shapes_denied_in_write(tmp_path, name):
    d = run(tmp_path, write("a\nb = " + SHAPES[name] + "\n"))
    assert d.kind == "deny"
    assert "line 2" in d.reason
    assert SHAPES[name] not in d.reason


def test_slack_variants(tmp_path):
    for letter in "baprs":
        assert run(tmp_path, write("xo" + "x" + letter + "-" + "1234567890")).kind == "deny"
    assert run(tmp_path, write("xo" + "xz-" + "1234567890")).kind == "allow"


def test_minimum_lengths(tmp_path):
    assert run(tmp_path, write("sk-" + ALNUM[:31])).kind == "allow"
    assert run(tmp_path, write("sk-" + ALNUM)).kind == "deny"
    assert run(tmp_path, write("AK" + "IA" + "Q7ZP4MNB2XLC9RT")).kind == "allow"
    assert run(tmp_path, write("AK" + "IA" + "q7zp4mnb2xlc9rtd")).kind == "allow"  # lowercase
    assert run(tmp_path, write("gh" + "p_" + "Ab3Ab3Ab3Ab3Ab3Ab3A")).kind == "allow"  # 19
    assert run(tmp_path, write("sk-" + "or-v1-" + "0123456789abcdef012")).kind == "allow"  # 19 hex
    assert run(tmp_path, write("sk-" + "or-v1-" + "0123456789abcdefghij")).kind == "allow"  # not hex
    assert run(tmp_path, write("AI" + "za" + "Ab3_-" * 7)).kind == "deny"  # 35
    assert run(tmp_path, write("AI" + "za" + "Ab3_-" * 6)).kind == "allow"  # 30


def test_pem_header(tmp_path):
    for kind in ("RSA ", "EC ", "OPENSSH ", ""):
        text = "-----BEGIN " + kind + "PRIVATE KEY-----\nabc"
        d = run(tmp_path, write(text))
        assert d.kind == "deny" and "line 1" in d.reason
    assert run(tmp_path, write("-----BEGIN " + "PUBLIC KEY-----")).kind == "allow"
    assert run(tmp_path, write("a PEM header looks like BEGIN ... PRIVATE KEY")).kind == "allow"


@pytest.mark.parametrize("name", ["api_key", "API_KEY", "apikey", "my_secret", "auth_token", "DB_PASSWORD"])
def test_assignment_denied(tmp_path, name):
    value = "Zq8!mN2#vB5%kL9&"
    assert len(value) == 16
    for text in (f'{name} = "{value}"', f"{name}='{value}'", f'"{name}": "{value}"', f'{name}: "{value}"',
                 f'export {name}="{value}"', f'cmd --{name}="{value}"'):
        d = run(tmp_path, write("x\n" + text))
        assert d.kind == "deny", text
        assert "line 2" in d.reason and value not in d.reason


def test_assignment_too_short_or_not_quoted(tmp_path):
    assert run(tmp_path, write('password = "Zq8!mN2#vB5%kL9"')).kind == "allow"  # 15
    assert run(tmp_path, write("password = Zq8!mN2#vB5%kL9&xx")).kind == "allow"
    assert run(tmp_path, write('username = "Zq8!mN2#vB5%kL9&xx"')).kind == "allow"


def test_variable_references_allowed(tmp_path):
    texts = [
        "echo $OPENROUTER_API_KEY",
        'curl -H "Authorization: Bearer ${GITHUB_TOKEN}"',
        'key = os.environ["OPENROUTER_API_KEY"]',
        "const k = process.env.OPENROUTER_API_KEY",
        'api_key = "${OPENROUTER_API_KEY}"',
        'token: "$OPENROUTER_API_KEY_LONGER"',
        'export API_KEY="$OPENROUTER_API_KEY"',
    ]
    for t in texts:
        assert run(tmp_path, payload("Bash", command=t)).kind == "allow", t


def test_bare_mentions_allowed(tmp_path):
    for t in ("keys start with sk-ant- and ghp_", "the format is sk-or-v1-<hex>", "set the password and secret"):
        assert run(tmp_path, write(t)).kind == "allow", t


def test_placeholders_allowed(tmp_path):
    cases = [
        "sk-" + "0" * 40,
        "sk-" + ALNUM + "...",
        "AK" + "IA" + "X" * 16,
        "gh" + "p_" + "EXAMPLE" + "Ab3" * 6,
        "sk-" + "ant-" + "your" + "Ab3" * 10,
        "sk-" + "ant-" + "PlaceHolder" + "Ab3" * 10,
        "sk-" + "ant-" + "changeme" + "Ab3" * 10,
        "sk-" + "ant-" + "Ab3" * 10 + "XXXX",
        "sk-" + "ant-<" + "Ab3" * 10 + ">",
        'api_key = "your-api-key-goes-here"',
        'api_key = "' + "a" * 20 + '"',
        'api_key = "' + "abcdefghijklmnop" + '..."',
        'secret = "<insert secret value>"',
        'password = "ChangeMe-please-now!"',
    ]
    for t in cases:
        assert run(tmp_path, write(t)).kind == "allow", t


def test_placeholder_token_is_whitespace_or_quote_delimited(tmp_path):
    real = "sk-" + ALNUM
    assert run(tmp_path, write(f"{real} # your key")).kind == "deny"
    assert run(tmp_path, write(f'"{real}" example')).kind == "deny"
    assert run(tmp_path, write(f"key={real}")).kind == "deny"


def test_two_matches_one_placeholder(tmp_path):
    text = "sk-" + "0" * 40 + "\nline2 " + "sk-" + ALNUM
    d = run(tmp_path, write(text))
    assert d.kind == "deny" and "line 2" in d.reason and "line 1" not in d.reason


def test_profile_allow_patterns(tmp_path):
    key = "sk-" + ALNUM
    assert run(tmp_path, write(key)).kind == "deny"
    assert run(tmp_path, write(key), secret_allow_patterns=["^sk-Qw3r"]).kind == "allow"
    assert run(tmp_path, write(key), secret_allow_patterns=["^nomatch"]).kind == "deny"
    assert run(tmp_path, write('password = "Zq8!mN2#vB5%kL9&"'),
               secret_allow_patterns=["Zq8!mN2"]).kind == "allow"


def test_tools_and_fields(tmp_path):
    key = "sk-" + ALNUM
    assert run(tmp_path, payload("Edit", file_path="a", old_string=key, new_string="x")).kind == "allow"
    assert run(tmp_path, payload("Edit", file_path="a", old_string="x", new_string=key)).kind == "deny"
    assert run(tmp_path, payload("Bash", command=f"echo {key}")).kind == "deny"
    assert run(tmp_path, payload("Write", file_path=key, content="ok")).kind == "allow"
    assert run(tmp_path, payload("Read", file_path="a", content=key)).kind == "allow"
    assert run(tmp_path, payload("Grep", pattern=key)).kind == "allow"
    assert run(tmp_path, payload("Write", file_path="a")).kind == "allow"
    assert run(tmp_path, parse_payload(json.dumps({"hook_event_name": "PreToolUse"}))).kind == "allow"


@pytest.mark.parametrize("role", [None, "implement", "orchestrator", "review", "unknown-role"])
def test_every_role(tmp_path, role):
    raw = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/x",
           "tool_input": {"command": "echo sk-" + ALNUM}}
    if role:
        raw["agent_type"] = role
    assert run(tmp_path, parse_payload(json.dumps(raw))).kind == "deny"


def test_non_string_field_fails_closed(tmp_path):
    for p in (payload("Write", file_path="a", content=["x"]), payload("Bash", command=5),
              payload("Edit", file_path="a", new_string={"a": 1})):
        assert run(tmp_path, p).kind == "deny"


def test_reason_never_contains_value_and_names_kind(tmp_path):
    key = "sk-" + "ant-" + "Ab3_-Ab3_-Ab3_-Ab3_-Ab3"
    d = run(tmp_path, write("\n\n" + key))
    assert key not in d.reason and "Ab3_-Ab3" not in d.reason
    assert "line 3" in d.reason and "anthropic" in d.reason.lower()


def test_multiple_findings_listed(tmp_path):
    d = run(tmp_path, write("sk-" + ALNUM + "\n\n" + "AK" + "IA" + "Q7ZP4MNB2XLC9RTD"))
    assert "line 1" in d.reason and "line 3" in d.reason


def test_crlf_line_numbers(tmp_path):
    assert "line 3" in run(tmp_path, write("a\r\nb\r\nsk-" + ALNUM)).reason


def test_deterministic_and_no_side_effects(tmp_path):
    p = write("sk-" + ALNUM)
    before = sorted(tmp_path.rglob("*"))
    assert run(tmp_path, p) == run(tmp_path, p)
    assert sorted(tmp_path.rglob("*")) == before
    assert not hasattr(secrets_guard, "record")


def test_registry_and_run_hook(tmp_path):
    hook = get_hook("secrets_guard")
    assert hook.implemented and hook.decide is secrets_guard.decide
    c = cfg(tmp_path)
    ok = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "echo $OPENROUTER_API_KEY"}}
    assert run_hook(secrets_guard.decide, json.dumps(ok), c).exit_code == 0
    bad = dict(ok, tool_input={"command": "echo sk-" + ALNUM})
    r = run_hook(secrets_guard.decide, json.dumps(bad), c)
    assert r.exit_code == 2 and "sk-" + ALNUM not in r.stderr and "line 1" in r.stderr
    r = run_hook(secrets_guard.decide, "not json", c)
    assert r.exit_code == 2 and r.stderr.startswith("hook error:")
