"""Unit coverage for the role specs and loader (TB-02). Not the acceptance gate."""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
import yaml

from factory.agents.roles import RoleError, RoleSpec, load_roles

ROLE_IDS = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]
HOOK_IDS = {
    "path_guard", "blindness_guard", "secrets_guard", "bash_guard",
    "stop_gate", "subagent_stop", "ledger_audit", "session_start",
}
SHIPPED = Path(__file__).resolve().parents[2] / "factory" / "agents" / "roles"


@pytest.fixture(scope="module")
def roles():
    return load_roles()


@pytest.fixture
def role_dir(tmp_path):
    dest = tmp_path / "roles"
    shutil.copytree(SHIPPED, dest)
    return dest


def _mutate(role_dir, role, fn):
    path = role_dir / f"{role}.yaml"
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data))


def test_seven_roles_in_order(roles):
    assert list(roles) == ROLE_IDS
    assert all(isinstance(r, RoleSpec) for r in roles.values())
    assert all(r.id == k for k, r in roles.items())


def test_frozen_and_to_dict(roles):
    r = roles["research"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.model = "x"
    d = r.to_dict()
    assert d["id"] == "research"
    assert set(d) == {
        "id", "description", "model", "core_tools", "disallowed_tools", "skills", "mcp",
        "spawns", "writes", "bash", "blind", "hooks", "max_tools",
    }
    assert all(set(m) == {"server", "access"} for m in d["mcp"])


def test_max_tools_bound(roles):
    for r in roles.values():
        assert r.max_tools <= 20
        assert len(r.core_tools) + len(r.mcp) <= r.max_tools


def test_writes_and_blind(roles):
    assert {k: r.writes for k, r in roles.items()} == {
        "orchestrator": "none", "research": "research_dir", "design": "design_dirs",
        "audit": "audit_dir", "implement": "app", "test": "eval_paths", "review": "none",
    }
    assert [k for k, r in roles.items() if r.blind] == ["implement"]


def test_spawns(roles):
    assert set(roles["orchestrator"].spawns) == set(ROLE_IDS) - {"orchestrator"}
    assert len(roles["orchestrator"].spawns) == 6
    assert roles["implement"].spawns == ()
    assert not any(t.startswith("Agent") for t in roles["implement"].core_tools)
    assert set(roles["review"].spawns) == {
        "pr-review-toolkit:silent-failure-hunter",
        "pr-review-toolkit:pr-test-analyzer",
        "feature-dev:code-reviewer",
    }
    for k in ("research", "design", "audit", "test"):
        assert roles[k].spawns == ()


def test_agent_tools_match_spawns(roles):
    for r in roles.values():
        agents = [t for t in r.core_tools if t == "Agent" or t.startswith("Agent(")]
        if not r.spawns:
            assert agents == []
        else:
            assert len(agents) == 1
            inner = agents[0][len("Agent("):-1].split(",")
            assert [s.strip() for s in inner] == list(r.spawns)


def test_bash_modes(roles):
    assert {k: r.bash for k, r in roles.items()} == {
        "orchestrator": "full", "research": "readonly", "design": "readonly",
        "audit": "readonly", "implement": "full", "test": "full", "review": "readonly",
    }


def test_hooks(roles):
    for r in roles.values():
        assert set(r.hooks) <= HOOK_IDS
        assert {"secrets_guard", "bash_guard", "path_guard"} <= set(r.hooks)
        assert len(set(r.hooks)) == len(r.hooks)
    assert {"blindness_guard", "stop_gate"} <= set(roles["implement"].hooks)
    for k in ROLE_IDS:
        if k != "implement":
            assert "blindness_guard" not in roles[k].hooks
            assert "stop_gate" not in roles[k].hooks
    for k in ("research", "design", "audit", "review"):
        assert "subagent_stop" in roles[k].hooks
    assert {"session_start", "ledger_audit"} <= set(roles["orchestrator"].hooks)
    for k in ROLE_IDS:
        if k != "orchestrator":
            assert "session_start" not in roles[k].hooks
            assert "ledger_audit" not in roles[k].hooks


def test_skills_exact(roles):
    expect = {
        "orchestrator": ["orchestration", "plan-adherence", "session-handoff", "away-mode",
                         "deploy-verify", "one-way-door",
                         "superpowers:dispatching-parallel-agents"],
        "research": ["grounded-research", "deep-research", "brownfield-explorer"],
        "design": ["prd-designer", "axiomatic-spec", "one-way-door",
                   "superpowers:brainstorming", "superpowers:writing-plans"],
        "audit": ["legacy-audit", "brownfield-explorer", "claude-security:scan"],
        "implement": ["superpowers:test-driven-development", "superpowers:systematic-debugging",
                      "claude-api", "frontend-design:frontend-design"],
        "test": ["eval-designer", "deploy-verify",
                 "superpowers:verification-before-completion", "langfuse"],
        "review": ["implementation-review", "code-review:code-review"],
    }
    assert {k: list(r.skills) for k, r in roles.items()} == expect


def test_mcp_entries(roles):
    platforms = ("railway", "vercel", "supabase", "github", "gitlab")
    for r in roles.values():
        for m in r.mcp:
            assert m.access == "read"
            assert not any(p == m.server for p in platforms)
    servers = {k: [m.server for m in r.mcp] for k, r in roles.items()}
    assert "$deploy" in servers["orchestrator"] and "$git_host" in servers["orchestrator"]
    assert {"$git_host", "deepwiki", "alphaXiv", "firecrawl"} <= set(servers["research"])
    assert {"$deploy", "playwright"} <= set(servers["test"])
    assert {"$deploy", "$git_host"} <= set(servers["review"])
    assert servers["implement"] == [] and servers["audit"] == [] and servers["design"] == []


def test_no_project_specifics(roles):
    blob = yaml.safe_dump([r.to_dict() for r in roles.values()]).lower()
    for word in ("openemr", "clinical", "qrypt", "unity"):
        assert word not in blob


def test_write_roles_do_not_get_write_tools(roles):
    for k in ("orchestrator", "review"):
        for t in ("Write", "Edit"):
            assert t not in roles[k].core_tools
    assert "Write" in roles["implement"].core_tools and "Edit" in roles["implement"].core_tools


def test_round_trips_through_yaml_files():
    files = sorted(p.stem for p in SHIPPED.glob("*.yaml"))
    assert sorted(ROLE_IDS) == files


@pytest.mark.parametrize("bad", ["not_a_hook", ""])
def test_unknown_hook_rejected(role_dir, bad):
    _mutate(role_dir, "audit", lambda d: d["hooks"].append(bad))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "audit"
    assert e.value.field == f"hooks[{len(yaml.safe_load((role_dir / 'audit.yaml').read_text())['hooks']) - 1}]"
    assert "audit" in str(e.value) and "hooks" in str(e.value)


def test_unknown_writes_rejected(role_dir):
    _mutate(role_dir, "design", lambda d: d.update(writes="everywhere"))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("design", "writes")


def test_max_tools_over_20_rejected(role_dir):
    _mutate(role_dir, "test", lambda d: d.update(max_tools=21))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("test", "max_tools")


def test_core_tools_over_max_rejected(role_dir):
    _mutate(role_dir, "test", lambda d: d.update(max_tools=2))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("test", "core_tools")


@pytest.mark.parametrize("field", [
    "description", "model", "core_tools", "disallowed_tools", "skills", "mcp", "spawns",
    "writes", "bash", "blind", "hooks", "max_tools",
])
def test_missing_field_rejected(role_dir, field):
    _mutate(role_dir, "research", lambda d: d.pop(field))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("research", field)
    assert "research" in str(e.value) and field in str(e.value)


def test_bad_bash_and_mcp_access_and_types(role_dir):
    _mutate(role_dir, "review", lambda d: d.update(bash="sudo"))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("review", "bash")


def test_mcp_write_access_value_checked(role_dir):
    _mutate(role_dir, "review", lambda d: d["mcp"].append({"server": "x", "access": "admin"}))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "review" and e.value.field.startswith("mcp[")


def test_blind_must_be_bool(role_dir):
    _mutate(role_dir, "implement", lambda d: d.update(blind="yes"))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("implement", "blind")


def test_max_tools_must_be_int_not_bool(role_dir):
    _mutate(role_dir, "implement", lambda d: d.update(max_tools=True))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.field == "max_tools"


def test_unknown_key_rejected(role_dir):
    _mutate(role_dir, "implement", lambda d: d.update(extra=1))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("implement", "extra")


def test_id_must_match_file(role_dir):
    _mutate(role_dir, "implement", lambda d: d.update(id="review"))
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert (e.value.role, e.value.field) == ("implement", "id")


def test_missing_role_file_rejected(role_dir):
    (role_dir / "test.yaml").unlink()
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "test"


def test_extra_role_file_rejected(role_dir):
    shutil.copy(role_dir / "audit.yaml", role_dir / "bogus.yaml")
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "bogus"


def test_non_mapping_file_rejected(role_dir):
    (role_dir / "audit.yaml").write_text("- a\n- b\n")
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "audit"


def test_invalid_yaml_rejected(role_dir):
    (role_dir / "audit.yaml").write_text("a: [unclosed\n")
    with pytest.raises(RoleError) as e:
        load_roles(role_dir)
    assert e.value.role == "audit"


def test_string_dir_accepted():
    assert len(load_roles(str(SHIPPED))) == 7


def test_deterministic():
    assert load_roles() == load_roles()
