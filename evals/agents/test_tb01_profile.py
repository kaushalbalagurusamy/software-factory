"""TB-01 project profile loader: golden and diagnostic cases.

Expectations come only from docs/contracts/profile.md and docs/prds/TB-01-profile-loader.md.
The contract does not say whether Profile fields are read as attributes or as mapping keys, so
`get()` accepts either (see coverage/ambiguities-A.md, A-01).
"""
from __future__ import annotations

import copy
import os
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
    for part in dotted.split("."):
        if isinstance(obj, Mapping):
            obj = obj[part]
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            obj = obj[part]
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


# One invalid value per checked top-level field, in the PRD's fixed order (graph omitted: see A-02).
def _m_schema(d): d["schema_version"] = 2
def _m_project(d): d["project"] = {}
def _m_msr(d): d["main_session_role"] = "wizard"
def _m_paths(d): d["paths"]["eval"] = []
def _m_agents(d): d["agents"] = {"wizard": {"model": "m"}}
def _m_mcp(d): d["mcp_servers"] = {"docsrv": "not-a-mapping"}
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
    """Behaviour 9: Profile is hashable or otherwise immutable; mutating it raises."""
    p = load(tmp_path, "base")
    with pytest.raises(Exception):
        setattr(p, "schema_version", 2)
    with pytest.raises(Exception):
        p["schema_version"] = 2  # type: ignore[index]
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
    """Behaviour 3: a missing project.name is rejected (field is project or project.name)."""
    d = base()
    d["project"] = {}
    assert field_is(load_error(tmp_path, d).field, "project")


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
    assert field_is(load_error(tmp_path, d).field, "paths")


@case("TB01-D-009", "diagnostic")
def test_d009_absolute_eval_path(tmp_path):
    """Behaviour 4: paths must not be absolute."""
    d = base()
    d["paths"]["eval"] = ["/abs/evals/**"]
    assert field_is(load_error(tmp_path, d).field, "paths.eval")


@case("TB01-D-010", "diagnostic")
def test_d010_parent_segment_in_dir(tmp_path):
    """Behaviour 4: paths must not contain '..'."""
    d = base()
    d["paths"]["research_dir"] = "../outside"
    assert field_is(load_error(tmp_path, d).field, "paths.research_dir")


@case("TB01-D-011", "diagnostic")
def test_d011_parent_segment_mid_path(tmp_path):
    """Behaviour 4: '..' inside a path is rejected, not only at the start."""
    d = base()
    d["paths"]["held_out"] = ["tests/../../x/**"]
    assert field_is(load_error(tmp_path, d).field, "paths.held_out")


@case("TB01-D-012", "diagnostic")
def test_d012_absolute_design_dir(tmp_path):
    """Behaviour 4: absolute paths are rejected in list-valued dir fields too."""
    d = base()
    d["paths"]["design_dirs"] = ["docs/prd", "/etc/adr"]
    assert field_is(load_error(tmp_path, d).field, "paths.design_dirs")


@pytest.mark.parametrize("glob", [
    pytest.param("qa/?.py", marks=case("TB01-D-013", "diagnostic"), id="question"),
    pytest.param("qa/[ab]/**", marks=case("TB01-D-014", "diagnostic"), id="class"),
    pytest.param("qa/{a,b}/**", marks=case("TB01-D-015", "diagnostic"), id="brace"),
])
def test_d013_non_star_glob_rejected(tmp_path, glob):
    """Behaviour 4 + contract: globs use `**` and `*` only; other glob syntax is rejected."""
    d = base()
    d["paths"]["frozen_tests"] = [glob]
    assert field_is(load_error(tmp_path, d).field, "paths.frozen_tests")


@case("TB01-D-016", "diagnostic")
def test_d016_star_globs_accepted(tmp_path):
    """Negative control for behaviour 4: `*` and `**` globs and plain relative paths are accepted."""
    d = base()
    d["paths"]["eval"] = ["evals/**/*.py", "golden/*", "cases/**"]
    d["paths"]["held_out"] = ["tests/held_out/*.json"]
    assert list(get(load(tmp_path, d), "paths.eval")) == ["evals/**/*.py", "golden/*", "cases/**"]


@case("TB01-D-017", "diagnostic")
def test_d017_agents_key_not_a_role(tmp_path):
    """Behaviour 5: agents.<role> keys must be role ids."""
    d = base()
    d["agents"] = {"janitor": {"model": "m"}}
    assert field_is(load_error(tmp_path, d).field, "agents")


@case("TB01-D-018", "diagnostic")
def test_d018_override_with_declared_server_accepted(tmp_path):
    """Negative control for behaviour 5: an override listing a declared server, a model and extra skills loads."""
    d = base()
    d["agents"] = {"research": {"model": "some-model", "extra_skills": ["x-skill"], "mcp_servers": ["docsrv"]}}
    p = load(tmp_path, d)
    assert list(get(p, "agents.research.mcp_servers")) == ["docsrv"]
    assert get(p, "agents.research.model") == "some-model"


@case("TB01-D-019", "diagnostic")
def test_d019_bad_one_way_door_regex_index(tmp_path):
    """Behaviour 6: a regex that does not compile is rejected with the field name and the entry index."""
    d = base()
    d["one_way_door_patterns"] = ["\\bok\\b", "(unclosed"]
    f = load_error(tmp_path, d).field
    assert f.startswith("one_way_door_patterns") and "1" in f[len("one_way_door_patterns"):]


@case("TB01-D-020", "diagnostic")
def test_d020_bad_secret_allow_regex_index(tmp_path):
    """Behaviour 6 for secret_allow_patterns, index 0."""
    d = base()
    d["secret_allow_patterns"] = ["[bad", "fine"]
    f = load_error(tmp_path, d).field
    assert f.startswith("secret_allow_patterns") and "0" in f[len("secret_allow_patterns"):]


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
    pytest.param("mcp_servers", _m_mcp, marks=case("TB01-D-026", "diagnostic"), id="mcp_servers"),
])
def test_d024_structural_type_errors(tmp_path, name, mut):
    """R-02 'an invalid profile is rejected with an error that names the field': a value of the wrong
    shape for a schema field (mapping expected) names that field."""
    d = base()
    mut(d)
    assert field_is(load_error(tmp_path, d).field, name)


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
    assert list(get(p, "mcp_servers.docsrv.read_tools")) == ["search", "fetch"]


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
    assert field_is(load_error(tmp_path, d).field, "one_way_door_patterns")
