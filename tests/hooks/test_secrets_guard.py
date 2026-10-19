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
    # C-39.1: only whole-value placeholder forms exempt a match
    cases = [
        "sk-" + "0" * 40,
        "AK" + "IA" + "X" * 16,
        "sk-" + "ant-<" + "Ab3" * 10 + ">",
        'api_key = "' + "a" * 20 + '"',
        'secret = "<insert secret value>"',
        'secret = "<' + "Ab3" * 10 + '>"',
        'password = "${SOME_LONG_VARIABLE_NAME}"',
        'password = "$SOME_LONG_VARIABLE_NAME"',
    ]
    for t in cases:
        assert run(tmp_path, write(t)).kind == "allow", t


def test_placeholder_words_no_longer_exempt(tmp_path):
    # C-39.1 supersedes A-07-3 / PRD TB-07 behaviour 4 (words, ellipsis, partial markers)
    cases = [
        "sk-" + ALNUM + "...",
        "gh" + "p_" + "EXAMPLE" + "Ab3" * 6,
        "sk-" + "ant-" + "your" + "Ab3" * 10,
        "sk-" + "ant-" + "PlaceHolder" + "Ab3" * 10,
        "sk-" + "ant-" + "changeme" + "Ab3" * 10,
        "sk-" + "ant-" + "Ab3" * 10 + "XXXX",
        'api_key = "your-api-key-goes-here"',
        'api_key = "' + "abcdefghijklmnop" + '..."',
        'password = "ChangeMe-please-now!"',
        "your_key=sk-" + ALNUM,
        'secret = "<a>' + "Zq8!mN2#vB5%kL9&xx" + '<b>"',
        'secret = "<' + "Zq8!mN2#vB5" + '> ' + "kL9&xxZq8!mN2" + '"',
        'secret = "$HOME' + "Zq8!mN2#vB5%kL9&xx" + '"',
        'secret = "' + "a" * 16 + 'b"',
        "export example_key=sk-" + ALNUM,
        "your key: sk-" + ALNUM,
    ]
    for t in cases:
        assert run(tmp_path, write(t)).kind == "deny", t


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


# ---- C-38.4: MultiEdit and NotebookEdit ------------------------------------------------------
def test_multiedit_scans_every_new_string(tmp_path):
    key = "sk-" + ALNUM
    ok = {"old_string": "a", "new_string": "fine"}
    p = payload("MultiEdit", file_path="a", edits=[ok, {"old_string": key, "new_string": "x"}])
    assert run(tmp_path, p).kind == "allow"  # only new_string is inspected
    p = payload("MultiEdit", file_path="a", edits=[ok, {"old_string": "a", "new_string": "\n" + key}])
    d = run(tmp_path, p)
    assert d.kind == "deny" and key not in d.reason and "line 2" in d.reason
    p = payload("MultiEdit", file_path="a", edits=[{"old_string": "a", "new_string": key}, ok])
    assert run(tmp_path, p).kind == "deny"
    assert run(tmp_path, payload("MultiEdit", file_path="a", edits=[ok, ok])).kind == "allow"
    assert run(tmp_path, payload("MultiEdit", file_path="a", edits=[])).kind == "allow"


@pytest.mark.parametrize("edits", ["x", {"new_string": "a"}, [5], [{"new_string": 5}], [{"new_string": ["a"]}],
                                   [None]])
def test_multiedit_malformed_fails_closed(tmp_path, edits):
    assert run(tmp_path, payload("MultiEdit", file_path="a", edits=edits)).kind == "deny"


def test_notebookedit_scans_new_source(tmp_path):
    key = "sk-" + ALNUM
    assert run(tmp_path, payload("NotebookEdit", notebook_path="a", new_source="x = '" + key + "'")).kind == "deny"
    assert run(tmp_path, payload("NotebookEdit", notebook_path="a", new_source="print(1)")).kind == "allow"
    assert run(tmp_path, payload("NotebookEdit", notebook_path="a", edit_mode="delete")).kind == "allow"
    assert run(tmp_path, payload("NotebookEdit", notebook_path="a", new_source=5)).kind == "deny"
    assert run(tmp_path, payload("NotebookEdit", notebook_path=key, new_source="ok")).kind == "allow"


def test_multiedit_size_cap_applies_to_total(tmp_path):
    half = "a" * 1_000_001
    p = payload("MultiEdit", file_path="a", edits=[{"new_string": half}, {"new_string": half}])
    d = run(tmp_path, p)
    assert d.kind == "deny" and "too large to scan" in d.reason


# ---- C-39.2: bounded scanning ----------------------------------------------------------------
def test_size_cap_boundary(tmp_path):
    assert run(tmp_path, write("a" * 2_000_000)).kind == "allow"
    for p in (write("a" * 2_000_001), payload("Bash", command="a" * 2_000_001),
              payload("Edit", file_path="a", new_string="a" * 2_000_001)):
        d = run(tmp_path, p)
        assert d.kind == "deny" and "too large to scan" in d.reason


def test_size_cap_does_not_hide_a_key_and_does_not_leak(tmp_path):
    key = "sk-" + ALNUM
    d = run(tmp_path, write(key + "a" * 2_000_000))
    assert d.kind == "deny" and "too large to scan" in d.reason and key not in d.reason


HOSTILE_N = 1_900_000


def _hostile_inputs():
    n = HOSTILE_N
    yield "a" * n
    yield "password" * (n // 8)
    yield "token " * (n // 6)
    yield "token_" * (n // 6)
    yield "api_key = " + " " * n
    yield 'password = "' + "a" * n
    yield "secret=" * (n // 7)
    yield 'secret="' * (n // 8)
    yield "password" + "a" * n + "="
    yield "sk-" * (n // 3)
    yield "sk-ant-" * (n // 7)
    yield ("sk-" + "a" * 31 + " ") * (n // 35)
    yield ("ghp_" + "a" * 19 + " ") * (n // 24)
    yield ("AIza" + "a" * 34 + " ") * (n // 39)
    yield "\\" * n
    yield "'" * n
    yield '"x" ' * (n // 4)
    yield "$'" * (n // 2)


@pytest.mark.parametrize("idx", range(18))
def test_hostile_input_is_scanned_in_linear_time(tmp_path, idx):
    import time
    text = list(_hostile_inputs())[idx]
    assert len(text) <= 2_000_000
    for p in (write(text), payload("Bash", command=text)):
        t0 = time.monotonic()
        run(tmp_path, p)
        assert time.monotonic() - t0 < 5.0, idx


def test_many_findings_scan_fast(tmp_path):
    import time
    text = ("sk-" + ALNUM + " ") * (HOSTILE_N // 36)
    t0 = time.monotonic()
    d = run(tmp_path, write(text))
    assert d.kind == "deny" and time.monotonic() - t0 < 5.0


def test_long_name_still_denied(tmp_path):
    # the bounded rewrite must not turn an old deny into an allow
    name = "password" + "_x" * 200
    assert run(tmp_path, write(name + ' = "' + "Zq8!mN2#vB5%kL9&xx" + '"')).kind == "deny"
    assert run(tmp_path, write("a" * 5000 + "token" + "b" * 5000 + ' = "' + "Zq8!mN2#vB5%kL9&xx" + '"')).kind == "deny"
    assert run(tmp_path, write("TOKENtoken = '" + "Zq8!mN2#vB5%kL9&xx" + "'")).kind == "deny"


# ---- C-39.3: quoting does not hide a key -----------------------------------------------------
def bash(cmd):
    return payload("Bash", command=cmd)


def test_quote_split_key_denied_in_bash(tmp_path):
    key = "sk-" + "ant-" + "Ab3_-Ab3_-Ab3_-Ab3_-Ab3"
    cmds = [
        'echo "sk-""ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3"',
        "echo 'sk-''ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        "echo sk-\\ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3",
        "echo s\\k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3",
        'echo s""k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3',
        "echo $'sk-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        "echo $'\\x73k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        "echo $'\\163k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        "echo $'\\u0073k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        "echo $'s''k-ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3'",
        'echo "s"\'k\'-"ant-"Ab3_-Ab3_-Ab3_-Ab3_-Ab3',
        'curl -H "Authorization: Bearer "g"hp_Ab3_Ab3_Ab3_Ab3_Ab3_"',
        'x=AK""IAQ7ZP4MNB2XLC9RTD',
        'x=A\\KIAQ7ZP4MNB2XLC9RTD',
    ]
    for c in cmds:
        d = run(tmp_path, bash(c))
        assert d.kind == "deny", c
        assert "Ab3_-Ab3" not in d.reason
    assert key  # fragments only; the literal above is split by shell quoting


def test_dequote_does_not_flag_clean_commands(tmp_path):
    for c in ('echo "hello" \'world\'', "echo $'a\\tb'", "grep -rn 'sk-ant-' .", 'echo "$OPENROUTER_API_KEY"',
              "git commit -m \"fix the token parser\""):
        assert run(tmp_path, bash(c)).kind == "allow", c


def test_dequote_applies_to_bash_only_and_keeps_original_scan(tmp_path):
    key = "sk-" + ALNUM
    assert run(tmp_path, bash(f"echo {key}")).kind == "deny"
    assert run(tmp_path, bash(f'echo "{key}"')).kind == "deny"
    # a Write is scanned as written: shell quoting means nothing in file content
    assert run(tmp_path, write('"sk-""' + "ant-Ab3_-Ab3_-Ab3_-Ab3_-Ab3" + '"')).kind == "allow"


def test_profile_allow_pattern_matches_value_only(tmp_path):
    key = "sk-" + ALNUM
    # the pattern must match the matched value, not the surrounding text
    assert run(tmp_path, write("ALLOWME " + key), secret_allow_patterns=["ALLOWME"]).kind == "deny"
    assert run(tmp_path, write('password = "Zq8!mN2#vB5%kL9&xx"'), secret_allow_patterns=["^password"]).kind == "deny"
