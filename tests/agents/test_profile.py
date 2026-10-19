"""Unit coverage for factory.agents.profile (TB-01). Not the acceptance gate."""
import copy
import dataclasses
import textwrap

import pytest

from factory.agents.profile import Profile, ProfileError, load_profile, parse_profile

BASE = {
    "schema_version": 1,
    "project": {"name": "demo"},
    "paths": {"eval": ["evals/**"]},
}


def make(**over):
    d = copy.deepcopy(BASE)
    d.update(over)
    return d


def field_of(data):
    with pytest.raises(ProfileError) as exc:
        parse_profile(data)
    assert exc.value.message
    return exc.value.field


def test_minimal_defaults():
    p = parse_profile(BASE)
    assert p.schema_version == 1 and p.project.name == "demo"
    assert p.main_session_role == "orchestrator"
    assert p.paths.eval == ("evals/**",)
    assert p.paths.held_out == () and p.paths.frozen_tests == () and p.paths.baseline_update == ()
    assert p.paths.research_dir == "research"
    assert p.paths.design_dirs == ("docs/prd", "docs/spec", "docs/adr")
    assert p.paths.audit_dir == "docs/audit"
    assert p.paths.ledger_dir == ".factory/ledger"
    assert len(p.agents) == 0 and len(p.mcp_servers) == 0
    assert p.graph is None and p.deploy is None and p.checks is None
    assert p.git_host == "none" and p.tracker == "none"
    assert p.one_way_door_patterns == () and p.secret_allow_patterns == ()


def test_full_profile_and_load_from_file(tmp_path):
    f = tmp_path / "profile.yaml"
    f.write_text(textwrap.dedent("""
        schema_version: 1
        project: {name: demo}
        main_session_role: design
        paths: {eval: [evals/**], held_out: [h/*], research_dir: r}
        mcp_servers: {pg: {read_tools: [q]}}
        agents: {test: {model: m, extra_skills: [s], mcp_servers: [pg]}}
        graph:
          stages: [{id: a, role: research}, {id: b, role: test, gate: true}]
          edges: [[a, b]]
          loops: [[b, a]]
          subsets: {fast: [research]}
        deploy: {route: r, platform_server: null, checklist: docs/c.md}
        git_host: github
        tracker: linear
        checks: {test: pytest}
        one_way_door_patterns: ['^rm ']
        secret_allow_patterns: ['x+']
    """))
    p = load_profile(f)
    assert p == load_profile(f) and hash(p) == hash(load_profile(f))
    assert p.main_session_role == "design" and p.paths.research_dir == "r"
    assert p.agents["test"].mcp_servers == ("pg",)
    assert p.mcp_servers["pg"].read_tools == ("q",)
    assert p.graph.stages[1].gate is True and p.graph.stages[0].gate is False
    assert p.graph.edges == (("a", "b"),) and p.graph.subsets["fast"] == ("research",)
    assert p.deploy.platform_server is None and p.checks.test == "pytest" and p.checks.lint is None
    d = p.to_dict()
    assert d["project"] == {"name": "demo"} and d["paths"]["eval"] == ["evals/**"]


@pytest.mark.parametrize("bad", [0, 2, "1", True, None, 1.0])
def test_schema_version_must_be_int_one(bad):
    assert field_of(make(schema_version=bad)) == "schema_version"


def test_missing_schema_version():
    d = make(); del d["schema_version"]
    assert field_of(d) == "schema_version"


def test_project_fields():
    d = make(); del d["project"]
    assert field_of(d) == "project"
    assert field_of(make(project={})) == "project.name"
    assert field_of(make(project={"name": ""})) == "project.name"


def test_main_session_role():
    assert field_of(make(main_session_role="boss")) == "main_session_role"
    assert parse_profile(make(main_session_role="review")).main_session_role == "review"


def test_paths_rules():
    assert field_of(make(paths={"eval": []})) == "paths.eval"
    assert field_of(make(paths={})) == "paths.eval"
    assert field_of(make(paths={"eval": ["/abs"]})) == "paths.eval[0]"
    assert field_of(make(paths={"eval": ["ok", "a/../b"]})) == "paths.eval[1]"
    assert field_of(make(paths={"eval": ["ok"], "held_out": ["x?"]})) == "paths.held_out[0]"
    assert field_of(make(paths={"eval": ["ok"], "research_dir": "../r"})) == "paths.research_dir"
    assert field_of(make(paths={"eval": ["a[bc]"]})) == "paths.eval[0]"
    assert parse_profile(make(paths={"eval": ["a..b/**/*.py"]})).paths.eval == ("a..b/**/*.py",)


def test_agents_rules():
    assert field_of(make(agents={"boss": {}})) == "agents.boss"
    assert field_of(make(agents={"test": {"tools": []}})) == "agents.test.tools"
    assert field_of(make(agents={"test": {"mcp_servers": ["pg"]}})) == "agents.test.mcp_servers"
    assert field_of(make(agents={"test": {"model": 3}})) == "agents.test.model"
    ok = parse_profile(make(agents={"test": {"mcp_servers": ["pg"]}}, mcp_servers={"pg": {}}))
    assert ok.agents["test"].mcp_servers == ("pg",)


def test_mcp_servers_shape():
    assert field_of(make(mcp_servers=[])) == "mcp_servers"
    assert field_of(make(mcp_servers={"pg": {"read_tools": "q"}})) == "mcp_servers.pg.read_tools"


def test_graph_shape():
    assert field_of(make(graph=[])) == "graph"
    assert field_of(make(graph={"stages": []})) == "graph.stages"
    assert field_of(make(graph={"stages": [{"id": "a"}]})) == "graph.stages[0].role"
    st = [{"id": "a", "role": "test"}]
    assert field_of(make(graph={"stages": st, "edges": [["a"]]})) == "graph.edges[0]"
    assert field_of(make(graph={"stages": st, "loops": [["a", 1]]})) == "graph.loops[0]"
    assert field_of(make(graph={"stages": st, "subsets": {"s": ["nope"]}})) == "graph.subsets.s[0]"
    assert field_of(make(graph={"stages": [{"id": "a", "role": "test", "gate": "y"}]})) == "graph.stages[0].gate"


def test_enums_and_wrong_types():
    assert field_of(make(git_host="svn")) == "git_host"
    assert field_of(make(tracker="jira")) == "tracker"
    assert field_of(make(deploy="x")) == "deploy"
    assert field_of(make(deploy={"route": 1})) == "deploy.route"
    assert field_of(make(checks={"test": ["a"]})) == "checks.test"
    assert field_of(make(checks=[])) == "checks"


def test_regex_fields_report_index():
    assert field_of(make(one_way_door_patterns=["ok", "("])) == "one_way_door_patterns[1]"
    assert field_of(make(secret_allow_patterns=["["])) == "secret_allow_patterns[0]"
    assert field_of(make(one_way_door_patterns=[3])) == "one_way_door_patterns[0]"


def test_unknown_top_level_key():
    assert field_of(make(surprise=1)) == "surprise"


def test_fixed_check_order():
    # git_host (later) and agents (earlier) both bad: agents wins
    assert field_of(make(git_host="x", agents={"boss": {}})) == "agents.boss"
    # unknown key is checked last
    assert field_of(make(surprise=1, one_way_door_patterns=["("])) == "one_way_door_patterns[0]"
    # schema_version before project
    d = make(schema_version=2); del d["project"]
    assert field_of(d) == "schema_version"
    # paths before graph
    assert field_of(make(paths={"eval": []}, graph=[])) == "paths.eval"
    # checks before regex
    assert field_of(make(checks=[], one_way_door_patterns=["("])) == "checks"


def test_not_a_mapping():
    with pytest.raises(ProfileError):
        parse_profile([1])


def test_immutable():
    p = parse_profile(make(agents={"test": {}}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.git_host = "github"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.paths.eval = ()
    with pytest.raises(TypeError):
        p.agents["test"] = None
    with pytest.raises((AttributeError, TypeError)):
        p.paths.eval.append("x")
    assert isinstance(hash(p), int)


def test_deterministic_and_input_not_mutated():
    d = make(agents={"test": {"extra_skills": ["s"]}})
    before = copy.deepcopy(d)
    assert parse_profile(d) == parse_profile(d) and d == before
    assert isinstance(parse_profile(d), Profile)


def test_yaml_error_is_profile_error(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("a: [unclosed")
    with pytest.raises(ProfileError):
        load_profile(f)
