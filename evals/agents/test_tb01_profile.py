"""TB-01 project profile loader: golden and diagnostic cases.

Expectations come only from docs/contracts/profile.md, docs/prds/TB-01-profile-loader.md and the binding
docs/contracts/clarifications.md (bracketed ids such as [A-01] cite it). Profile and its nested values are
frozen dataclasses read by attribute [A-01]; user-named keys (agents.<role>, mcp_servers.<name>) are mapping keys.
"""
from __future__ import annotations

import copy
import dataclasses
import os
import re
import socket
from collections.abc import Mapping

import pytest

from evals.agents import lib

ROLES = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]


def case(cid, tier, reqs=("R-02",)):
    return pytest.mark.case(cid, tier=tier, tb="01", reqs=list(reqs))


def mod():
    return lib.need("factory.agents.profile", "load_profile", "ProfileError")


def get(obj, dotted):
    """Attribute access [A-01]; a part written as `[key]` indexes a mapping (user-named keys)."""
    for part in re.findall(r"\[([^\]]+)\]|([^.\[]+)", dotted):
        key, name = part
        obj = obj[key] if key else getattr(obj, name)
    return obj


def load(tmp_path, data, sub="p"):
    m = mod()
    root = lib.make_project(tmp_path / sub, data)
    return m.load_profile(root / ".factory" / "profile.yaml")


def load_error(tmp_path, data, sub="p"):
    m = mod()
    root = lib.make_project(tmp_path / sub, data)
    with pytest.raises(m.ProfileError) as info:
        m.load_profile(root / ".factory" / "profile.yaml")
    return info.value


def field_is(field, name):
    """Exact dotted field, or a dotted/indexed descendant of it."""
    return field == name or field.startswith(name + ".") or field.startswith(name + "[")


def minimal():
    return {"schema_version": 1, "project": {"name": "mini"}, "paths": {"eval": ["ev/**"]}}


def base():
    return lib.profile_dict("base")


# One invalid value per checked top-level field, in the PRD's fixed order ([A-02]: the loader checks graph shape).
def _m_schema(d): d["schema_version"] = 2
def _m_project(d): d["project"] = {}
def _m_msr(d): d["main_session_role"] = "wizard"
def _m_paths(d): d["paths"]["eval"] = []
def _m_agents(d): d["agents"] = {"wizard": {"model": "m"}}
def _m_mcp(d): d["mcp_servers"] = {"docsrv": "not-a-mapping"}
def _m_graph(d): d["graph"] = "not-a-mapping"
def _m_deploy(d): d["deploy"] = "not-a-mapping"
def _m_git(d): d["git_host"] = "bitbucket"
def _m_tracker(d): d["tracker"] = "jira"
def _m_checks(d): d["checks"] = ["pytest"]
def _m_owd(d): d["one_way_door_patterns"] = ["(unclosed"]
def _m_sap(d): d["secret_allow_patterns"] = ["[bad"]
def _m_unknown(d): d["zzz_unknown_key"] = 1


ORDER = [
    ("schema_version", _m_schema), ("project", _m_project), ("main_session_role", _m_msr),
    ("paths", _m_paths), ("agents", _m_agents), ("mcp_servers", _m_mcp), ("deploy", _m_deploy),
    ("git_host", _m_git), ("tracker", _m_tracker), ("checks", _m_checks),
    ("one_way_door_patterns", _m_owd), ("secret_allow_patterns", _m_sap), ("zzz_unknown_key", _m_unknown),
]


# ---------------------------------------------------------------- golden

@case("TB01-G-001", "golden")
def test_g001_valid_profile_loads(tmp_path):
    """Behaviour 1: load_profile(path) returns a Profile for a valid file (fields carried from the YAML)."""
    p = load(tmp_path, "base")
    assert get(p, "project.name") == "fixture-alpha"
    assert list(get(p, "paths.eval")) == ["evals/**"]
    assert get(p, "schema_version") == 1


@case("TB01-G-002", "golden")
def test_g002_path_defaults(tmp_path):
    """Behaviour 1 + contract 'Defaults for omitted optional fields are exactly those shown above':
    research_dir research, design_dirs [docs/prd, docs/spec, docs/adr], audit_dir docs/audit,
    ledger_dir .factory/ledger, main_session_role orchestrator."""
    p = load(tmp_path, minimal())
    assert get(p, "paths.research_dir") == "research"
    assert list(get(p, "paths.design_dirs")) == ["docs/prd", "docs/spec", "docs/adr"]
    assert get(p, "paths.audit_dir") == "docs/audit"
    assert get(p, "paths.ledger_dir") == ".factory/ledger"
    assert get(p, "main_session_role") == "orchestrator"


@case("TB01-G-003", "golden")
def test_g003_schema_version_other_than_1(tmp_path):
    """Behaviour 3: schema_version other than 1 is rejected; ProfileError.field is 'schema_version'."""
    d = base()
    d["schema_version"] = 2
    assert load_error(tmp_path, d).field == "schema_version"


@case("TB01-G-004", "golden")
def test_g004_empty_eval_paths(tmp_path):
    """Behaviour 3 + contract: paths.eval is required, non-empty; field is the dotted path 'paths.eval'."""
    d = base()
    d["paths"]["eval"] = []
    assert load_error(tmp_path, d).field == "paths.eval"


@case("TB01-G-005", "golden")
def test_g005_unknown_top_level_key(tmp_path):
    """Behaviour 7: unknown top-level keys are rejected with the key name as the field."""
    d = base()
    d["surprise"] = True
    assert load_error(tmp_path, d).field == "surprise"


@case("TB01-G-006", "golden")
def test_g006_override_lists_undeclared_server(tmp_path):
    """Behaviour 5: an override that lists an MCP server not declared under mcp_servers is rejected
    with the field agents.<role>.mcp_servers."""
    d = base()
    d["agents"] = {"implement": {"mcp_servers": ["nosuchserver"]}}
    assert load_error(tmp_path, d).field == "agents.implement.mcp_servers"


@case("TB01-G-007", "golden")
def test_g007_first_problem_in_fixed_order(tmp_path):
    """Behaviour 2: the first problem is reported in fixed order; schema_version precedes paths."""
    d = base()
    d["schema_version"] = 3
    d["paths"]["eval"] = []
    assert load_error(tmp_path, d).field == "schema_version"


@case("TB01-G-008", "golden")
def test_g008_profile_is_immutable(tmp_path):
    """Behaviour 9 + [A-01]: Profile is a frozen dataclass; assigning a field raises."""
    p = load(tmp_path, "base")
    assert dataclasses.is_dataclass(p)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(p, "schema_version", 2)
    assert get(p, "schema_version") == 1


# ---------------------------------------------------------------- diagnostic

@case("TB01-D-001", "diagnostic")
def test_d001_enum_defaults(tmp_path):
    """Contract defaults: git_host 'default none', tracker 'default none' (the enumerated value 'none')."""
    p = load(tmp_path, minimal())
    assert get(p, "git_host") == "none"
    assert get(p, "tracker") == "none"


@case("TB01-D-002", "diagnostic")
def test_d002_alt_profile_values(tmp_path):
    """Behaviour 1 on the second fixture: every supplied field is carried, not a default."""
    p = load(tmp_path, "alt")
    assert get(p, "project.name") == "fixture-beta"
    assert get(p, "paths.research_dir") == "notes/research"
    assert list(get(p, "paths.design_dirs")) == ["design/prd", "design/adr"]
    assert get(p, "paths.audit_dir") == "notes/audit"
    assert get(p, "git_host") == "gitlab"
    assert get(p, "deploy.route") == "cloudctl release"
    assert get(p, "checks.test") == "npm test"


@case("TB01-D-003", "diagnostic", reqs=("R-02", "R-01"))
def test_d003_generality_paths_differ(tmp_path):
    """R-02 generality: base and alt fixtures differ in their paths, and the loaded Profiles reflect each."""
    a = load(tmp_path, "base", "a")
    b = load(tmp_path, "alt", "b")
    for f in ["paths.eval", "paths.held_out", "paths.frozen_tests", "paths.baseline_update",
              "paths.research_dir", "paths.design_dirs", "paths.audit_dir"]:
        va, vb = get(a, f), get(b, f)
        va = va if isinstance(va, str) else list(va)
        vb = vb if isinstance(vb, str) else list(vb)
        assert va != vb, f
    assert list(get(b, "paths.eval")) == ["qa/cases/**", "qa/golden/**"]


@case("TB01-D-004", "diagnostic")
def test_d004_missing_schema_version(tmp_path):
    """Contract: schema_version is required."""
    d = base()
    del d["schema_version"]
    assert load_error(tmp_path, d).field == "schema_version"


@case("TB01-D-005", "diagnostic")
def test_d005_missing_project_name(tmp_path):
    """Behaviour 3 + [A-07]: a project without name has field project.name."""
    d = base()
    d["project"] = {}
    assert load_error(tmp_path, d).field == "project.name"


@case("TB01-D-006", "diagnostic")
def test_d006_bad_main_session_role(tmp_path):
    """Behaviour 3: main_session_role that is not one of the seven role ids is rejected."""
    d = base()
    d["main_session_role"] = "manager"
    assert load_error(tmp_path, d).field == "main_session_role"


@case("TB01-D-007", "diagnostic")
def test_d007_every_role_accepted_as_main_session_role(tmp_path):
    """Negative control: each of the seven role ids is accepted for main_session_role."""
    for r in ROLES:
        d = base()
        d["main_session_role"] = r
        assert get(load(tmp_path, d, r), "main_session_role") == r


@case("TB01-D-008", "diagnostic")
def test_d008_missing_eval_key(tmp_path):
    """Contract: paths.eval is required."""
    d = base()
    del d["paths"]["eval"]
    assert load_error(tmp_path, d).field == "paths.eval"


@case("TB01-D-009", "diagnostic")
def test_d009_absolute_eval_path(tmp_path):
    """Behaviour 4: paths must not be absolute; [A-04] a bad list entry is field[index]."""
    d = base()
    d["paths"]["eval"] = ["/abs/evals/**"]
    assert load_error(tmp_path, d).field == "paths.eval[0]"


@case("TB01-D-010", "diagnostic")
def test_d010_parent_segment_in_dir(tmp_path):
    """Behaviour 4: paths must not contain '..'."""
    d = base()
    d["paths"]["research_dir"] = "../outside"
    assert load_error(tmp_path, d).field == "paths.research_dir"


@case("TB01-D-011", "diagnostic")
def test_d011_parent_segment_mid_path(tmp_path):
    """Behaviour 4 + [A-04]: a '..' segment inside a path is rejected, not only at the start."""
    d = base()
    d["paths"]["held_out"] = ["tests/../../x/**"]
    assert load_error(tmp_path, d).field == "paths.held_out[0]"


@case("TB01-D-012", "diagnostic")
def test_d012_absolute_design_dir(tmp_path):
    """Behaviour 4: absolute paths are rejected in list-valued dir fields too."""
    d = base()
    d["paths"]["design_dirs"] = ["docs/prd", "/etc/adr"]
    assert load_error(tmp_path, d).field == "paths.design_dirs[1]"


@pytest.mark.parametrize("glob", [
    pytest.param("qa/?.py", marks=case("TB01-D-013", "diagnostic"), id="question"),
    pytest.param("qa/[ab]/**", marks=case("TB01-D-014", "diagnostic"), id="class"),
    pytest.param("qa/{a,b}/**", marks=case("TB01-D-015", "diagnostic"), id="brace"),
])
def test_d013_non_star_glob_rejected(tmp_path, glob):
    """Behaviour 4 + contract: globs use `**` and `*` only; other glob syntax is rejected."""
    d = base()
    d["paths"]["frozen_tests"] = [glob]
    assert load_error(tmp_path, d).field == "paths.frozen_tests[0]"


@case("TB01-D-016", "diagnostic")
def test_d016_star_globs_accepted(tmp_path):
    """Negative control for behaviour 4: `*` and `**` globs and plain relative paths are accepted."""
    d = base()
    d["paths"]["eval"] = ["evals/**/*.py", "golden/*", "cases/**"]
    d["paths"]["held_out"] = ["tests/held_out/*.json"]
    assert list(get(load(tmp_path, d), "paths.eval")) == ["evals/**/*.py", "golden/*", "cases/**"]


@case("TB01-D-017", "diagnostic")
def test_d017_agents_key_not_a_role(tmp_path):
    """Behaviour 5 + [A-08] (field names the offending key): agents.<role> keys must be role ids."""
    d = base()
    d["agents"] = {"janitor": {"model": "m"}}
    assert load_error(tmp_path, d).field == "agents.janitor"


@case("TB01-D-018", "diagnostic")
def test_d018_override_with_declared_server_accepted(tmp_path):
    """Negative control for behaviour 5: an override listing a declared server, a model and extra skills loads."""
    d = base()
    d["agents"] = {"research": {"model": "some-model", "extra_skills": ["x-skill"], "mcp_servers": ["docsrv"]}}
    p = load(tmp_path, d)
    assert list(get(p, "agents[research].mcp_servers")) == ["docsrv"]
    assert get(p, "agents[research].model") == "some-model"


@case("TB01-D-019", "diagnostic")
def test_d019_bad_one_way_door_regex_index(tmp_path):
    """Behaviour 6 + [A-04]: a regex that does not compile is rejected as one_way_door_patterns[1]."""
    d = base()
    d["one_way_door_patterns"] = ["\\bok\\b", "(unclosed"]
    assert load_error(tmp_path, d).field == "one_way_door_patterns[1]"


@case("TB01-D-020", "diagnostic")
def test_d020_bad_secret_allow_regex_index(tmp_path):
    """Behaviour 6 + [A-04] for secret_allow_patterns, index 0: field secret_allow_patterns[0]."""
    d = base()
    d["secret_allow_patterns"] = ["[bad", "fine"]
    assert load_error(tmp_path, d).field == "secret_allow_patterns[0]"


@case("TB01-D-021", "diagnostic")
def test_d021_valid_regexes_accepted(tmp_path):
    """Negative control for behaviour 6: compiling regexes (alt fixture) load."""
    p = load(tmp_path, "alt")
    assert list(get(p, "secret_allow_patterns")) == ["FIXTURE-KEY-[0-9]+"]


@case("TB01-D-022", "diagnostic")
def test_d022_git_host_enum(tmp_path):
    """Contract: git_host is github | gitlab | none; other values rejected, listed values accepted."""
    d = base()
    d["git_host"] = "bitbucket"
    assert load_error(tmp_path, d, "bad").field == "git_host"
    for v in ["github", "gitlab", "none"]:
        d = base()
        d["git_host"] = v
        assert get(load(tmp_path, d, v), "git_host") == v


@case("TB01-D-023", "diagnostic")
def test_d023_tracker_enum(tmp_path):
    """Contract: tracker is none | linear | notion; other values rejected, listed values accepted."""
    d = base()
    d["tracker"] = "jira"
    assert load_error(tmp_path, d, "bad").field == "tracker"
    for v in ["none", "linear", "notion"]:
        d = base()
        d["tracker"] = v
        assert get(load(tmp_path, d, v), "tracker") == v


@pytest.mark.parametrize("name,mut", [
    pytest.param("deploy", _m_deploy, marks=case("TB01-D-024", "diagnostic"), id="deploy"),
    pytest.param("checks", _m_checks, marks=case("TB01-D-025", "diagnostic"), id="checks"),
    pytest.param("mcp_servers.docsrv", _m_mcp, marks=case("TB01-D-026", "diagnostic"), id="mcp_servers"),
])
def test_d024_structural_type_errors(tmp_path, name, mut):
    """[A-08]: a wrong-typed value anywhere in the schema is invalid and .field names the offending key
    (deploy, checks, mcp_servers.<name>)."""
    d = base()
    mut(d)
    assert load_error(tmp_path, d).field == name


_pairs = [(ORDER[i], ORDER[i + 1]) for i in range(len(ORDER) - 1)]


@pytest.mark.parametrize("first,second", [
    pytest.param(a, b, marks=case(f"TB01-D-{27 + i:03d}", "diagnostic"), id=f"{a[0]}-before-{b[0]}")
    for i, (a, b) in enumerate(_pairs)
])
def test_d027_field_order(tmp_path, first, second):
    """Behaviour 2: checking order is schema_version, project, main_session_role, paths, agents, mcp_servers,
    graph, deploy, git_host, tracker, checks, one_way_door_patterns, secret_allow_patterns, then unknown
    top-level keys. With problems in two adjacent fields, the earlier field is reported."""
    d = base()
    first[1](d)
    second[1](d)
    assert field_is(load_error(tmp_path, d).field, first[0])


@case("TB01-D-039", "diagnostic")
def test_d039_all_problems_reports_first(tmp_path):
    """Behaviour 2: with a problem in every field, schema_version is reported."""
    d = base()
    for _, mut in ORDER:
        mut(d)
    assert load_error(tmp_path, d).field == "schema_version"


@case("TB01-D-040", "diagnostic")
def test_d040_error_has_message(tmp_path):
    """Contract: ProfileError carries .field and .message."""
    d = base()
    d["tracker"] = "jira"
    e = load_error(tmp_path, d)
    assert isinstance(e.message, str) and e.message.strip()


@case("TB01-D-041", "diagnostic")
def test_d041_same_file_equal_profile(tmp_path):
    """Behaviour 8: the same file always gives an equal Profile."""
    m = mod()
    root = lib.make_project(tmp_path, "alt")
    path = root / ".factory" / "profile.yaml"
    assert m.load_profile(path) == m.load_profile(path)


@case("TB01-D-042", "diagnostic")
def test_d042_does_not_read_environment(tmp_path, monkeypatch):
    """Behaviour 8: the loader does not read environment variables."""
    m = mod()
    root = lib.make_project(tmp_path, "base")

    class RecordingEnv(dict):
        touched: list = []

        def __getitem__(self, k):
            self.touched.append(k)
            return super().__getitem__(k)

        def get(self, k, default=None):
            self.touched.append(k)
            return super().get(k, default)

        def __contains__(self, k):
            self.touched.append(k)
            return super().__contains__(k)

    env = RecordingEnv(os.environ)
    env.touched = []
    monkeypatch.setattr(os, "environ", env)
    m.load_profile(root / ".factory" / "profile.yaml")
    assert env.touched == []


@case("TB01-D-043", "diagnostic")
def test_d043_env_changes_do_not_change_profile(tmp_path, monkeypatch):
    """Behaviour 8 / contract: the result depends on the file only (FACTORY_PROFILE, HOME set elsewhere)."""
    m = mod()
    root = lib.make_project(tmp_path, "base")
    other = lib.make_project(tmp_path / "o", "alt")
    path = root / ".factory" / "profile.yaml"
    first = m.load_profile(path)
    monkeypatch.setenv("FACTORY_PROFILE", str(other / ".factory" / "profile.yaml"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(other)
    assert m.load_profile(path) == first


@case("TB01-D-044", "diagnostic")
def test_d044_no_network(tmp_path, monkeypatch):
    """Behaviour 8 / contract: the loader never makes a network call."""
    m = mod()
    root = lib.make_project(tmp_path, "base")

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert get(m.load_profile(root / ".factory" / "profile.yaml"), "project.name") == "fixture-alpha"


@case("TB01-D-045", "diagnostic")
def test_d045_nested_values_immutable(tmp_path):
    """Behaviour 9: mutating the Profile raises; a nested list value cannot be changed in place."""
    p = load(tmp_path, "base")
    ev = get(p, "paths.eval")
    try:
        ev.append("x/**")  # type: ignore[union-attr]
    except Exception:
        pass
    assert list(get(p, "paths.eval")) == ["evals/**"]


@case("TB01-D-046", "diagnostic")
def test_d046_mcp_servers_carried(tmp_path):
    """Behaviour 1: declared mcp_servers and their read_tools are carried into the Profile."""
    p = load(tmp_path, "base")
    assert list(get(p, "mcp_servers[docsrv].read_tools")) == ["search", "fetch"]


@case("TB01-D-047", "diagnostic")
def test_d047_minimal_profile_loads(tmp_path):
    """Negative control: only the required fields (schema_version, project.name, paths.eval) are needed."""
    p = load(tmp_path, minimal())
    assert get(p, "project.name") == "mini"


@case("TB01-D-048", "diagnostic")
def test_d048_unknown_key_reported_after_all_fields(tmp_path):
    """Behaviour 2 + 7: an unknown key is reported only when every named field is valid."""
    d = copy.deepcopy(base())
    d["aaa_unknown"] = 1
    d["one_way_door_patterns"] = ["(bad"]
    assert load_error(tmp_path, d).field == "one_way_door_patterns[0]"


# ---------------------------------------------------------------- added after docs/contracts/clarifications.md

@case("TB01-G-009", "golden")
def test_g009_agents_override_unknown_key(tmp_path):
    """[A-11]: in agents.<role> the only accepted keys are model, extra_skills, mcp_servers; any other key is a
    ProfileError with field agents.<role>.<key>."""
    d = base()
    d["agents"] = {"review": {"writes": "app"}}
    assert load_error(tmp_path, d).field == "agents.review.writes"


@case("TB01-D-049", "diagnostic")
def test_d049_omitted_optional_defaults(tmp_path):
    """[A-03]: omitted optional lists are empty tuples, omitted mappings empty mappings, and omitted deploy,
    checks and graph are None."""
    p = load(tmp_path, minimal())
    for f in ["paths.held_out", "paths.frozen_tests", "paths.baseline_update", "one_way_door_patterns",
              "secret_allow_patterns"]:
        assert get(p, f) == (), f
    for f in ["agents", "mcp_servers"]:
        v = get(p, f)
        assert isinstance(v, Mapping) and len(v) == 0, f
    for f in ["deploy", "checks", "graph"]:
        assert get(p, f) is None, f


@case("TB01-D-050", "diagnostic")
def test_d050_dotdot_inside_name_valid(tmp_path):
    """[A-05]: only a `..` path segment is rejected; `a..b` is a valid name."""
    d = base()
    d["paths"]["research_dir"] = "notes/a..b"
    d["paths"]["held_out"] = ["x..y/**"]
    p = load(tmp_path, d)
    assert get(p, "paths.research_dir") == "notes/a..b"


@case("TB01-D-051", "diagnostic")
def test_d051_one_way_door_patterns_profile_only(tmp_path):
    """[A-06]: Profile.one_way_door_patterns holds only the profile's own patterns (no built-in defaults)."""
    assert tuple(get(load(tmp_path, "base"), "one_way_door_patterns")) == ("\\bmigrate\\s+--drop\\b",)
    assert get(load(tmp_path, minimal(), "m"), "one_way_door_patterns") == ()


@case("TB01-D-052", "diagnostic")
def test_d052_missing_project(tmp_path):
    """[A-07]: a missing project has field project."""
    d = base()
    del d["project"]
    assert load_error(tmp_path, d).field == "project"


@pytest.mark.parametrize("mut,field", [
    pytest.param(lambda d: d.__setitem__("project", {"name": 5}), "project.name",
                 marks=case("TB01-D-053", "diagnostic"), id="project-name-int"),
    pytest.param(lambda d: d["checks"].__setitem__("test", 5), "checks.test",
                 marks=case("TB01-D-054", "diagnostic"), id="checks-test-int"),
    pytest.param(lambda d: d["deploy"].__setitem__("route", ["x"]), "deploy.route",
                 marks=case("TB01-D-055", "diagnostic"), id="deploy-route-list"),
    pytest.param(lambda d: d["paths"].__setitem__("research_dir", ["a"]), "paths.research_dir",
                 marks=case("TB01-D-056", "diagnostic"), id="research-dir-list"),
    pytest.param(lambda d: d.__setitem__("one_way_door_patterns", "\\bx\\b"), "one_way_door_patterns",
                 marks=case("TB01-D-057", "diagnostic"), id="patterns-string"),
])
def test_d053_wrong_type_names_key(tmp_path, mut, field):
    """[A-08]: a wrong-typed value anywhere in the schema is invalid; .field names the offending key."""
    d = base()
    mut(d)
    assert load_error(tmp_path, d).field == field


@pytest.mark.parametrize("value", [
    pytest.param("1", marks=case("TB01-D-058", "diagnostic"), id="string"),
    pytest.param(True, marks=case("TB01-D-059", "diagnostic"), id="bool"),
])
def test_d058_schema_version_must_be_int_1(tmp_path, value):
    """[A-09]: schema_version must be the integer 1; the string "1" and the boolean true are invalid."""
    d = base()
    d["schema_version"] = value
    assert load_error(tmp_path, d).field == "schema_version"


@pytest.mark.parametrize("graph", [
    pytest.param("not-a-mapping", marks=case("TB01-D-060", "diagnostic"), id="not-mapping"),
    pytest.param({"stages": "x", "edges": []}, marks=case("TB01-D-061", "diagnostic"), id="stages-not-list"),
    pytest.param({"stages": [{"id": "a"}], "edges": []}, marks=case("TB01-D-062", "diagnostic"),
                 id="stage-missing-role"),
    pytest.param({"stages": [{"id": "a", "role": "design", "gate": "yes"}], "edges": []},
                 marks=case("TB01-D-063", "diagnostic"), id="gate-not-bool"),
    pytest.param({"stages": [{"id": "a", "role": "design"}], "edges": [["a"]]},
                 marks=case("TB01-D-064", "diagnostic"), id="edge-one-item"),
    pytest.param({"stages": [{"id": "a", "role": "design"}], "edges": [], "subsets": {"s": ["wizard"]}},
                 marks=case("TB01-D-065", "diagnostic"), id="subset-member-not-role"),
])
def test_d060_graph_shape_checked(tmp_path, graph):
    """[A-02] + [A-29]: the loader checks the shape of graph (mapping; stages list of mappings with id, role,
    optional bool gate; edges and loops lists of two-item string lists; subsets names to role ids) and raises
    ProfileError on the graph field."""
    d = base()
    d["graph"] = graph
    assert field_is(load_error(tmp_path, d).field, "graph")


@case("TB01-D-066", "diagnostic")
def test_d066_graph_semantics_not_checked_by_loader(tmp_path):
    """[A-02]: graph semantics belong to TB-12, so a well-shaped graph with a cycle and an unknown stage role
    still loads."""
    d = base()
    d["graph"] = {"stages": [{"id": "a", "role": "wizard"}, {"id": "b", "role": "design"}],
                  "edges": [["a", "b"], ["b", "a"]]}
    load(tmp_path, d)


@pytest.mark.parametrize("first,second", [
    pytest.param(("mcp_servers", _m_mcp), ("graph", _m_graph), marks=case("TB01-D-067", "diagnostic"),
                 id="mcp_servers-before-graph"),
    pytest.param(("graph", _m_graph), ("deploy", _m_deploy), marks=case("TB01-D-068", "diagnostic"),
                 id="graph-before-deploy"),
])
def test_d067_graph_in_field_order(tmp_path, first, second):
    """Behaviour 2 + [A-02]: graph sits between mcp_servers and deploy in the fixed checking order."""
    d = base()
    first[1](d)
    second[1](d)
    assert field_is(load_error(tmp_path, d).field, first[0])


@case("TB01-D-069", "diagnostic")
def test_d069_to_dict(tmp_path):
    """[A-01]: Profile has .to_dict(), returning the profile's data."""
    td = load(tmp_path, "base").to_dict()
    assert isinstance(td, Mapping)
    assert td["project"]["name"] == "fixture-alpha"
    assert list(td["paths"]["eval"]) == ["evals/**"]


@case("TB01-D-070", "diagnostic")
def test_d070_nested_values_are_frozen_dataclasses(tmp_path):
    """[A-01]: nested values (paths, project, an mcp server entry, an agents override) are frozen dataclasses
    read by attribute."""
    d = base()
    d["agents"] = {"research": {"model": "m"}}
    p = load(tmp_path, d)
    for v in [get(p, "paths"), get(p, "project"), get(p, "mcp_servers[docsrv]"), get(p, "agents[research]")]:
        assert dataclasses.is_dataclass(v)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(v, dataclasses.fields(v)[0].name, None)


@case("TB01-D-071", "diagnostic")
def test_d071_list_values_are_tuples(tmp_path):
    """[A-03] + behaviour 9: list values are tuples (immutable)."""
    p = load(tmp_path, "alt")
    assert get(p, "paths.eval") == ("qa/cases/**", "qa/golden/**")
    assert get(p, "paths.design_dirs") == ("design/prd", "design/adr")


# ---------------------------------------------------------------- added after clarifications, third round

def parse():
    return lib.need("factory.agents.profile", "parse_profile", "ProfileError")


@pytest.mark.parametrize("fixture", [
    pytest.param("base", marks=case("TB01-D-072", "diagnostic"), id="base"),
    pytest.param("alt", marks=case("TB01-D-073", "diagnostic"), id="alt"),
])
def test_d072_parse_profile_matches_load_profile(tmp_path, fixture):
    """[A-11] third round: load_profile(path) is yaml.safe_load then parse_profile, so parse_profile on the same
    data gives an equal Profile."""
    m = parse()
    assert m.parse_profile(lib.profile_dict(fixture)) == load(tmp_path, fixture)


def _p_abs(d): d["paths"]["eval"] = ["/abs/**"]
def _p_owd(d): d["one_way_door_patterns"] = ["ok", "(bad"]
def _p_override(d): d["agents"] = {"review": {"writes": "app"}}
def _p_undeclared(d): d["agents"] = {"implement": {"mcp_servers": ["nosuchserver"]}}


@pytest.mark.parametrize("mut,field", [
    pytest.param(_m_schema, "schema_version", marks=case("TB01-D-074", "diagnostic"), id="schema"),
    pytest.param(_p_abs, "paths.eval[0]", marks=case("TB01-D-075", "diagnostic"), id="absolute"),
    pytest.param(_p_owd, "one_way_door_patterns[1]", marks=case("TB01-D-076", "diagnostic"), id="regex"),
    pytest.param(_p_override, "agents.review.writes", marks=case("TB01-D-077", "diagnostic"), id="override-key"),
    pytest.param(_p_undeclared, "agents.implement.mcp_servers", marks=case("TB01-D-078", "diagnostic"),
                 id="undeclared-server"),
    pytest.param(_m_unknown, "zzz_unknown_key", marks=case("TB01-D-079", "diagnostic"), id="unknown-key"),
])
def test_d074_parse_profile_applies_every_rule(mut, field):
    """[A-11] third round: parse_profile applies every rule of the profile contract, including the override-key
    rule, raising ProfileError with the same field as load_profile would."""
    m = parse()
    d = base()
    mut(d)
    with pytest.raises(m.ProfileError) as info:
        m.parse_profile(d)
    assert info.value.field == field


@case("TB01-D-080", "diagnostic")
def test_d080_parse_profile_field_order(tmp_path):
    """[A-11] + behaviour 2: parse_profile reports the first problem in the same fixed order as load_profile."""
    m = parse()
    d = base()
    for _, mut in ORDER:
        mut(d)
    with pytest.raises(m.ProfileError) as info:
        m.parse_profile(copy.deepcopy(d))
    assert info.value.field == "schema_version" == load_error(tmp_path, d).field
