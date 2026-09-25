"""TB-02 seven role specs and loader: golden and diagnostic cases.

Expectations come only from docs/contracts/roles-and-generation.md, docs/contracts/hook-io.md (hook ids),
docs/prds/TB-02-role-specs.md and section 3 of docs/plans/2026-09-24-agent-capability-map.md.
RoleSpec field access (attribute or key) is not specified, so `get()` accepts either (ambiguities A-01).
"""
from __future__ import annotations

import shutil
from collections.abc import Mapping

import pytest
import yaml

from evals.agents import lib

ROLES = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]
FIELDS = ["id", "description", "model", "core_tools", "disallowed_tools", "skills", "mcp", "spawns",
          "writes", "bash", "blind", "hooks", "max_tools"]
HOOK_IDS = {"path_guard", "blindness_guard", "secrets_guard", "bash_guard", "stop_gate", "subagent_stop",
            "ledger_audit", "session_start"}
WRITES = {"none", "app", "research_dir", "design_dirs", "audit_dir", "eval_paths"}
REVIEWERS = {"pr-review-toolkit:silent-failure-hunter", "pr-review-toolkit:pr-test-analyzer",
             "feature-dev:code-reviewer"}
ROLE_DIR = lib.REPO / "factory" / "agents" / "roles"


def case(cid, tier, reqs=("R-04",)):
    return pytest.mark.case(cid, tier=tier, tb="02", reqs=list(reqs))


def mod():
    return lib.need("factory.agents.roles", "load_roles")


def get(obj, name):
    if isinstance(obj, Mapping):
        return obj[name]
    if hasattr(obj, name):
        return getattr(obj, name)
    return obj[name]


def roles():
    return mod().load_roles()


def role_copy(tmp_path, role=None, mutate=None):
    """Copy the shipped role files to tmp and optionally mutate one role's YAML mapping."""
    dst = tmp_path / "roles"
    dst.mkdir()
    for f in ROLE_DIR.glob("*.yaml"):
        shutil.copy(f, dst / f.name)
    if role:
        path = dst / f"{role}.yaml"
        data = yaml.safe_load(path.read_text())
        mutate(data)
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    return dst


def rejects(tmp_path, role, mutate):
    m = mod()
    d = role_copy(tmp_path, role, mutate)
    with pytest.raises(Exception) as info:
        m.load_roles(d)
    return str(info.value)


def agent_names(tools):
    """Names inside Agent(...) entries, and whether a bare Agent entry exists."""
    names, bare = set(), False
    for t in tools:
        t = str(t).strip()
        if t == "Agent":
            bare = True
        elif t.startswith("Agent(") and t.endswith(")"):
            names |= {x.strip() for x in t[6:-1].split(",") if x.strip()}
    return names, bare


# ---------------------------------------------------------------- golden

@case("TB02-G-001", "golden")
def test_g001_exactly_seven_roles():
    """Behaviour 1: load_roles() returns exactly seven RoleSpecs keyed by the seven role ids."""
    assert set(roles()) == set(ROLES) and len(roles()) == 7


@case("TB02-G-002", "golden", reqs=("R-04", "R-05", "R-08"))
def test_g002_all_fields_and_max_tools():
    """Behaviour 2: every spec has all contract fields and max_tools <= 20 (integer)."""
    for rid, spec in roles().items():
        for f in FIELDS:
            get(spec, f)
        mt = get(spec, "max_tools")
        assert isinstance(mt, int) and not isinstance(mt, bool) and mt <= 20, rid


@case("TB02-G-003", "golden", reqs=("R-06",))
def test_g003_writes_per_role():
    """Behaviour 3: implement writes app; orchestrator and review none; research research_dir; design
    design_dirs; audit audit_dir; test eval_paths."""
    expected = {"implement": "app", "orchestrator": "none", "review": "none", "research": "research_dir",
                "design": "design_dirs", "audit": "audit_dir", "test": "eval_paths"}
    assert {r: get(s, "writes") for r, s in roles().items()} == expected


@case("TB02-G-004", "golden", reqs=("R-06",))
def test_g004_only_implement_blind():
    """Behaviour 3 + contract: blind is true only for implement."""
    assert {r for r, s in roles().items() if get(s, "blind") is True} == {"implement"}


@case("TB02-G-005", "golden", reqs=("R-07",))
def test_g005_orchestrator_and_implement_spawns():
    """Behaviour 4: orchestrator spawns exactly the other six role ids; implement spawns none."""
    rs = roles()
    assert sorted(get(rs["orchestrator"], "spawns")) == sorted(r for r in ROLES if r != "orchestrator")
    assert list(get(rs["implement"], "spawns")) == []


@case("TB02-G-006", "golden", reqs=("R-07",))
def test_g006_review_spawns_reviewers_only():
    """Behaviour 4: review spawns only the three named plugin reviewer agents."""
    assert set(get(roles()["review"], "spawns")) == REVIEWERS


@case("TB02-G-007", "golden", reqs=("R-04",))
def test_g007_common_hooks_and_known_ids():
    """Behaviour 6: hook ids come only from hook-io.md; every role lists secrets_guard and bash_guard."""
    for rid, spec in roles().items():
        hooks = set(get(spec, "hooks"))
        assert hooks <= HOOK_IDS, rid
        assert {"secrets_guard", "bash_guard"} <= hooks, rid


@case("TB02-G-008", "golden", reqs=("R-05",))
def test_g008_rejects_max_tools_over_20(tmp_path):
    """Behaviour 9: load_roles rejects max_tools > 20 with an error naming the role and the field."""
    msg = rejects(tmp_path, "research", lambda d: d.__setitem__("max_tools", 21))
    assert "research" in msg and "max_tools" in msg


# ---------------------------------------------------------------- diagnostic

@case("TB02-D-001", "diagnostic")
def test_d001_id_matches_key():
    """Contract: id is one of the seven role ids; the dict is keyed by it."""
    for rid, spec in roles().items():
        assert get(spec, "id") == rid


@case("TB02-D-002", "diagnostic", reqs=("R-05",))
def test_d002_core_tools_within_max():
    """Behaviour 2: len(core_tools) (+ read-tool placeholders) never exceeds max_tools as shipped."""
    for rid, spec in roles().items():
        assert len(list(get(spec, "core_tools"))) <= get(spec, "max_tools"), rid


@case("TB02-D-003", "diagnostic", reqs=("R-07",))
def test_d003_implement_has_no_agent_tool():
    """Behaviour 4: implement has no Agent tool."""
    tools = [str(t) for t in get(roles()["implement"], "core_tools")]
    assert not any(t == "Agent" or t.startswith("Agent(") for t in tools)


@case("TB02-D-004", "diagnostic", reqs=("R-04",))
def test_d004_bash_modes():
    """Behaviour 5: research, audit, design, review readonly; orchestrator, implement, test full."""
    expected = {"research": "readonly", "audit": "readonly", "design": "readonly", "review": "readonly",
                "orchestrator": "full", "implement": "full", "test": "full"}
    assert {r: get(s, "bash") for r, s in roles().items()} == expected


@case("TB02-D-005", "diagnostic", reqs=("R-04",))
def test_d005_implement_hooks():
    """Behaviour 6: implement lists blindness_guard and stop_gate."""
    assert {"blindness_guard", "stop_gate"} <= set(get(roles()["implement"], "hooks"))


@case("TB02-D-006", "diagnostic", reqs=("R-04", "R-06"))
def test_d006_path_guard_on_folder_writers():
    """Behaviour 6 + map 3.2-3.4: research, design and audit (write-restricted to their folder) list path_guard."""
    rs = roles()
    for r in ["research", "design", "audit"]:
        assert "path_guard" in set(get(rs[r], "hooks")), r


@case("TB02-D-007", "diagnostic", reqs=("R-04",))
def test_d007_subagent_stop_roles():
    """Behaviour 6: research, design, audit, review list subagent_stop."""
    rs = roles()
    for r in ["research", "design", "audit", "review"]:
        assert "subagent_stop" in set(get(rs[r], "hooks")), r


@case("TB02-D-008", "diagnostic", reqs=("R-04",))
def test_d008_orchestrator_hooks():
    """Behaviour 6: orchestrator lists session_start and ledger_audit."""
    assert {"session_start", "ledger_audit"} <= set(get(roles()["orchestrator"], "hooks"))


SKILLS = {
    "orchestrator": {"orchestration", "plan-adherence", "session-handoff", "away-mode", "deploy-verify", "one-way-door"},
    "research": {"grounded-research", "deep-research", "brownfield-explorer"},
    "design": {"prd-designer", "axiomatic-spec", "one-way-door"},
    "audit": {"legacy-audit", "brownfield-explorer"},
    "test": {"eval-designer", "deploy-verify"},
    "review": {"implementation-review"},
}


@pytest.mark.parametrize("role", [
    pytest.param(r, marks=case(f"TB02-D-{9 + i:03d}", "diagnostic"), id=r) for i, r in enumerate(SKILLS)
])
def test_d009_skills_per_role(role):
    """Behaviour 7: skills per role match the consolidated names in capability map section 3."""
    assert SKILLS[role] <= set(get(roles()[role], "skills"))


@case("TB02-D-015", "diagnostic")
def test_d015_implement_skills():
    """Behaviour 7 + map 3.5: implement loads the superpowers test-driven-development and systematic-debugging
    skills (plugin prefix form not fixed by the map, so matched by name)."""
    skills = [str(s) for s in get(roles()["implement"], "skills")]
    assert any(s.endswith("test-driven-development") for s in skills)
    assert any(s.endswith("systematic-debugging") for s in skills)


@case("TB02-D-016", "diagnostic", reqs=("R-05",))
def test_d016_mcp_entries_read_only():
    """Behaviour 8: mcp entries are {server, access}; access is read for every role (the map grants no writes)."""
    for rid, spec in roles().items():
        for e in get(spec, "mcp"):
            assert isinstance(get(e, "server"), str) and get(e, "server"), rid
            assert get(e, "access") == "read", rid


@case("TB02-D-017", "diagnostic", reqs=("R-01", "R-05"))
def test_d017_no_specific_deploy_platform():
    """Behaviour 8 + map 5: no role names a specific project deploy platform as an MCP server."""
    for rid, spec in roles().items():
        servers = {str(get(e, "server")).lower() for e in get(spec, "mcp")}
        assert not servers & {"railway", "vercel", "supabase"}, rid


@case("TB02-D-018", "diagnostic", reqs=("R-01",))
def test_d018_role_files_name_no_project():
    """R-01 + TB-02 purpose 'stripped of anything project-specific': role data names no specific project
    or platform (for example the project the map was drafted on, or a deploy platform)."""
    mod()
    for f in ROLE_DIR.glob("*.yaml"):
        text = f.read_text().lower()
        for word in ["openemr", "railway", "vercel", "supabase", "gauntlet", "/users/", "/home/"]:
            assert word not in text, (f.name, word)


@case("TB02-D-019", "diagnostic", reqs=("R-05",))
def test_d019_roles_without_mcp():
    """Map 3.3-3.5: design ('none by default'), audit ('none. No network.') and implement ('none by default')
    have no MCP entries."""
    rs = roles()
    for r in ["design", "audit", "implement"]:
        assert list(get(rs[r], "mcp")) == [], r


@case("TB02-D-020", "diagnostic", reqs=("R-06",))
def test_d020_write_edit_tools():
    """R-06: orchestrator and review have neither Write nor Edit; implement has both."""
    rs = roles()
    for r in ["orchestrator", "review"]:
        assert not {"Write", "Edit"} & {str(t) for t in get(rs[r], "core_tools")}, r
    assert {"Write", "Edit"} <= {str(t) for t in get(rs["implement"], "core_tools")}


@case("TB02-D-021", "diagnostic", reqs=("R-06",))
def test_d021_no_edit_for_research_audit():
    """Map 3.2 and 3.4 'Never: Edit': research and audit have no Edit tool."""
    rs = roles()
    for r in ["research", "audit"]:
        assert "Edit" not in {str(t) for t in get(rs[r], "core_tools")}, r


@case("TB02-D-022", "diagnostic", reqs=("R-07",))
def test_d022_agent_tool_matches_spawn_allowlist():
    """R-07 / map 3.1 and 3.7: any Agent(...) entry in core_tools names only allowed spawns; orchestrator and
    review have no unrestricted bare Agent entry."""
    rs = roles()
    for r, allowed in [("orchestrator", set(ROLES) - {"orchestrator"}), ("review", REVIEWERS)]:
        names, bare = agent_names(get(rs[r], "core_tools"))
        assert not bare, r
        assert names <= allowed, r


@case("TB02-D-023", "diagnostic")
def test_d023_enum_values_valid():
    """Contract: writes in {none, app, research_dir, design_dirs, audit_dir, eval_paths}; bash in
    {none, readonly, full}; blind boolean; description and model non-empty strings."""
    for rid, spec in roles().items():
        assert get(spec, "writes") in WRITES, rid
        assert get(spec, "bash") in {"none", "readonly", "full"}, rid
        assert isinstance(get(spec, "blind"), bool), rid
        assert isinstance(get(spec, "description"), str) and get(spec, "description").strip(), rid
        assert isinstance(get(spec, "model"), str) and get(spec, "model").strip(), rid


@case("TB02-D-024", "diagnostic")
def test_d024_rejects_unknown_hook(tmp_path):
    """Behaviour 9: an unknown hook id is rejected with an error naming the role and the field."""
    msg = rejects(tmp_path, "review", lambda d: d["hooks"].append("made_up_hook"))
    assert "review" in msg and "hooks" in msg


@case("TB02-D-025", "diagnostic", reqs=("R-06",))
def test_d025_rejects_unknown_writes(tmp_path):
    """Behaviour 9: an unknown writes value is rejected with an error naming the role and the field."""
    msg = rejects(tmp_path, "audit", lambda d: d.__setitem__("writes", "everywhere"))
    assert "audit" in msg and "writes" in msg


@pytest.mark.parametrize("field", [
    pytest.param("description", marks=case("TB02-D-026", "diagnostic"), id="description"),
    pytest.param("writes", marks=case("TB02-D-027", "diagnostic"), id="writes"),
    pytest.param("max_tools", marks=case("TB02-D-028", "diagnostic"), id="max_tools"),
    pytest.param("hooks", marks=case("TB02-D-029", "diagnostic"), id="hooks"),
])
def test_d026_rejects_missing_field(tmp_path, field):
    """Behaviour 9: a missing field is rejected with an error naming the role and the field."""
    msg = rejects(tmp_path, "design", lambda d: d.pop(field))
    assert "design" in msg and field in msg


@case("TB02-D-030", "diagnostic", reqs=("R-05",))
def test_d030_max_tools_20_accepted(tmp_path):
    """Negative control / boundary for behaviour 9: max_tools of exactly 20 is accepted."""
    m = mod()
    d = role_copy(tmp_path, "review", lambda x: x.__setitem__("max_tools", 20))
    assert get(m.load_roles(d)["review"], "max_tools") == 20


@case("TB02-D-031", "diagnostic")
def test_d031_explicit_dir_equals_default(tmp_path):
    """Contract load_roles(dir=default): an unmodified copy of the shipped files loads to the same specs."""
    m = mod()
    a, b = m.load_roles(), m.load_roles(role_copy(tmp_path))
    assert set(a) == set(b)
    for r in a:
        for f in FIELDS:
            va, vb = get(a[r], f), get(b[r], f)
            assert (list(va) if isinstance(va, (list, tuple)) else va) == \
                   (list(vb) if isinstance(vb, (list, tuple)) else vb), (r, f)


@case("TB02-D-032", "diagnostic")
def test_d032_one_file_per_role():
    """Contract: role data lives in factory/agents/roles/<role>.yaml, one file per role (seven files)."""
    mod()
    assert sorted(f.stem for f in ROLE_DIR.glob("*.yaml")) == sorted(ROLES)


@case("TB02-D-033", "diagnostic", reqs=("R-07",))
def test_d033_spawns_are_known():
    """Contract: spawns are role ids (or plugin agent names for review); no role spawns orchestrator."""
    for rid, spec in roles().items():
        sp = set(get(spec, "spawns"))
        assert "orchestrator" not in sp, rid
        if rid != "review":
            assert sp <= set(ROLES), rid
