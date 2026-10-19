"""Unit coverage for the agent file generator (TB-03). Not the acceptance gate."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from factory.agents.generate import GenerationError, generate_agents
from factory.agents.profile import AgentOverride, FrozenMap, parse_profile
from factory.agents.roles import ROLE_IDS, load_roles

GOLDEN = Path(__file__).resolve().parent / "golden"
ALLOWED = ["name", "description", "model", "tools", "disallowedTools", "skills", "hooks"]


def base(**over):
    d = {
        "schema_version": 1,
        "project": {"name": "Zorblax"},
        "paths": {"eval": ["evals/**"]},
        "git_host": "github",
        "deploy": {"route": "ci", "platform_server": "hostsrv", "checklist": "docs/deploy.md"},
        "mcp_servers": {
            "github": {"read_tools": ["get_pr", "list_prs"]},
            "hostsrv": {"read_tools": ["get_logs"]},
            "deepwiki": {"read_tools": ["ask"]},
            "playwright": {"read_tools": ["navigate"]},
            "extra": {"read_tools": ["peek"]},
        },
    }
    d.update(over)
    return d


@pytest.fixture(scope="module")
def roles():
    return load_roles()


@pytest.fixture(scope="module")
def profile():
    return parse_profile(base())


def split(text):
    assert text.startswith("---\n")
    fm, body = text[4:].split("\n---\n", 1)
    return yaml.safe_load(fm), fm, body


def test_seven_entries_keys_and_determinism(profile, roles):
    a = generate_agents(profile, roles)
    b = generate_agents(profile, roles)
    assert list(a) == [f".claude/agents/{r}.md" for r in ROLE_IDS]
    assert a == b


def test_frontmatter_fields_and_order(profile, roles):
    for path, text in generate_agents(profile, roles).items():
        data, fm, _ = split(text)
        keys = list(data)
        assert keys == [k for k in ALLOWED if k in keys]
        assert set(keys) >= {"name", "description", "model", "tools"}
        top = [ln.split(":")[0] for ln in fm.splitlines() if re.match(r"^[A-Za-z]", ln)]
        assert top == keys
        assert data["name"] == path.split("/")[-1][:-3]
        role = roles[data["name"]]
        assert data["description"] == role.description
        assert data["model"] == role.model


def test_empty_optional_fields_omitted(profile, roles):
    out = generate_agents(profile, roles)
    d, _, _ = split(out[".claude/agents/design.md"])
    assert "disallowedTools" not in d
    d, _, _ = split(out[".claude/agents/orchestrator.md"])
    assert d["disallowedTools"] == "Write, Edit"
    d, _, _ = split(out[".claude/agents/test.md"])
    assert "disallowedTools" not in d
    assert "hooks" in d


def test_tools_built_from_core_then_mcp(profile, roles):
    out = generate_agents(profile, roles)
    d, _, _ = split(out[".claude/agents/research.md"])
    tools = d["tools"].split(", ")
    core = list(roles["research"].core_tools)
    assert tools[: len(core)] == core
    assert tools[len(core):] == ["mcp__deepwiki__ask", "mcp__github__get_pr", "mcp__github__list_prs"]
    d, _, _ = split(out[".claude/agents/test.md"])
    assert "mcp__playwright__navigate" in d["tools"] and "mcp__hostsrv__get_logs" in d["tools"]
    d, _, _ = split(out[".claude/agents/orchestrator.md"])
    assert "Agent(research, design, audit, implement, test, review)" in d["tools"]
    assert "mcp__hostsrv__get_logs" in d["tools"]


def test_missing_servers_contribute_nothing(roles):
    p = parse_profile({k: v for k, v in base().items() if k not in ("mcp_servers", "deploy", "git_host")})
    out = generate_agents(p, roles)
    for path, text in out.items():
        d, _, _ = split(text)
        assert "mcp__" not in d["tools"], path
        assert d["tools"] == ", ".join(roles[d["name"]].core_tools)


def test_write_access_lists_whole_server(profile, roles):
    spec = dataclasses.replace(roles["research"], mcp=(type(roles["research"].mcp[0])("deepwiki", "write"),))
    r = dict(roles, research=spec)
    d, _, _ = split(generate_agents(profile, r)[".claude/agents/research.md"])
    tools = d["tools"].split(", ")
    assert "mcp__deepwiki" in tools and "mcp__deepwiki__ask" not in tools


def test_overrides_model_skills_servers(roles):
    p = parse_profile(base(agents={"implement": {"model": "opus", "extra_skills": ["eval-gate-triage"],
                                                  "mcp_servers": ["extra"]}}))
    d, _, _ = split(generate_agents(p, roles)[".claude/agents/implement.md"])
    assert d["model"] == "opus"
    assert d["skills"] == list(roles["implement"].skills) + ["eval-gate-triage"]
    assert d["tools"].split(", ")[-1] == "mcp__extra__peek"


def test_override_cannot_add_write_or_change_writes(roles):
    p = parse_profile(base())
    bad = dataclasses.make_dataclass("Bad", [("writes", str, "app")], bases=(AgentOverride,), frozen=True)()
    p2 = dataclasses.replace(p, agents=FrozenMap({"research": bad}))
    with pytest.raises(GenerationError):
        generate_agents(p2, roles)
    ns = SimpleNamespace(model=None, extra_skills=(), mcp_servers=(), access="write")
    with pytest.raises(GenerationError):
        generate_agents(dataclasses.replace(p, agents=FrozenMap({"research": ns})), roles)


def test_override_server_not_declared(roles):
    p = parse_profile(base())
    o = AgentOverride(mcp_servers=("nope",))
    with pytest.raises(GenerationError):
        generate_agents(dataclasses.replace(p, agents=FrozenMap({"research": o})), roles)


def test_max_tools_exceeded(roles):
    tools = [f"t{i}" for i in range(19)]
    p = parse_profile(base(mcp_servers={"deepwiki": {"read_tools": tools}}))
    with pytest.raises(GenerationError):
        generate_agents(p, roles)


def test_max_tools_boundary_ok(roles):
    n = 20 - len(roles["research"].core_tools)
    p = parse_profile(base(mcp_servers={"deepwiki": {"read_tools": [f"t{i}" for i in range(n)]}}))
    d, _, _ = split(generate_agents(p, roles)[".claude/agents/research.md"])
    assert len(d["tools"].split(", ")) == 20


EXPECTED_HOOKS = {
    "path_guard": ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash"),
    "secrets_guard": ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash"),
    "blindness_guard": ("PreToolUse", "Read|Grep|Glob|Bash"),
    "bash_guard": ("PreToolUse", "Bash"),
    "stop_gate": ("Stop", None),
    "subagent_stop": ("SubagentStop", None),
    "ledger_audit": ("SubagentStop", None),
    "session_start": ("SessionStart", None),
}


def test_hooks_event_matcher_command(profile, roles):
    out = generate_agents(profile, roles)
    for role in ROLE_IDS:
        d, _, _ = split(out[f".claude/agents/{role}.md"])
        seen = {}
        for event, entries in d["hooks"].items():
            for e in entries:
                assert set(e) <= {"matcher", "hooks"}
                for h in e["hooks"]:
                    assert h["type"] == "command"
                    hid = h["command"].removeprefix("python -m factory.hooks ")
                    assert h["command"] == f"python -m factory.hooks {hid}"
                    seen[hid] = (event, e.get("matcher"))
        assert seen == {h: EXPECTED_HOOKS[h] for h in roles[role].hooks}, role


def test_project_name_never_leaks(roles):
    a = generate_agents(parse_profile(base(project={"name": "Alpha"}, mcp_servers={})), roles)
    b = generate_agents(parse_profile(base(project={"name": "Omega Station"}, mcp_servers={})), roles)
    assert a == b


def test_project_name_in_role_body_raises(profile, roles):
    for name in ("Purpose", "never", "SKILLS"):
        with pytest.raises(GenerationError):
            generate_agents(parse_profile(base(project={"name": name})), roles)
    spec = dataclasses.replace(roles["audit"], description="Audits the zorblax code base.")
    with pytest.raises(GenerationError):
        generate_agents(profile, dict(roles, audit=spec))


def test_project_name_substring_is_not_whole_word(roles):
    out = generate_agents(parse_profile(base(project={"name": "mple"})), roles)
    assert len(out) == 7


def test_body_sections_order_and_skills(profile, roles):
    p = parse_profile(base(agents={"design": {"extra_skills": ["local-skill"]}}))
    for role, text in generate_agents(p, roles).items():
        d, _, body = split(text)
        heads = re.findall(r"^## .*$", body, re.M)
        assert heads == ["## Purpose", "## You may write", "## You must never", "## Skills"]
        skills_part = body.split("## Skills", 1)[1]
        for s in d.get("skills", []):
            assert s in skills_part
    d, _, body = split(generate_agents(p, roles)[".claude/agents/design.md"])
    assert "local-skill" in body


def test_no_secrets_or_home_paths(profile, roles):
    for text in generate_agents(profile, roles).values():
        assert not re.search(r"/home/|/Users/|~/|sk-[A-Za-z0-9]{10}|ghp_|BEGIN .*PRIVATE", text)


def test_secret_or_home_path_in_input_rejected(roles):
    p = parse_profile(base(mcp_servers={"deepwiki": {"read_tools": ["sk-" + "a" * 40]}}))
    with pytest.raises(GenerationError):
        generate_agents(p, roles)
    spec = dataclasses.replace(roles["audit"], description="Reads /home/someone/project files.")
    with pytest.raises(GenerationError):
        generate_agents(parse_profile(base()), dict(roles, audit=spec))


def test_no_platform_or_host_named_in_body(profile, roles):
    for text in generate_agents(profile, roles).values():
        _, _, body = split(text)
        assert not re.search(r"github|gitlab|railway|vercel|supabase", body, re.I)


def test_incomplete_roles_rejected(profile, roles):
    r = dict(roles)
    del r["audit"]
    with pytest.raises(GenerationError):
        generate_agents(profile, r)


def test_golden(profile, roles):
    out = generate_agents(profile, roles)
    for path, text in out.items():
        assert (GOLDEN / Path(path).name).read_text(encoding="utf-8") == text, path
