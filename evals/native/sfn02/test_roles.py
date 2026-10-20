"""SFN-02 acceptance: role data, loader, graph, reviewer rubric. Public interfaces and files on disk only."""
from __future__ import annotations

import shutil

import pytest
import yaml

from factory.agents.generate import generate_agents
from factory.agents.graph import Graph, GraphError, default_graph
from factory.agents.profile import parse_profile
from factory.agents.roles import RoleError, load_roles

from .conftest import REPO, ROLES8

ROLE_DIR = REPO / "factory/agents/roles"
PROFILE = {"schema_version": 1, "project": {"name": "t"}, "paths": {"eval": ["evals/**"]}}


def role_copy(tmp_path):
    d = tmp_path / "roles"
    shutil.copytree(ROLE_DIR, d)
    return d


def edit(d, role, **kv):
    p = d / f"{role}.yaml"
    data = yaml.safe_load(p.read_text())
    data.update(kv)
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def generated():
    return generate_agents(parse_profile(PROFILE), load_roles())


# ---------------------------------------------------------------- A-01 all roles Sonnet
def test_A01_every_role_file_declares_sonnet():
    files = sorted(ROLE_DIR.glob("*.yaml"))
    assert {f.stem for f in files} == set(ROLES8)
    for f in files:
        assert yaml.safe_load(f.read_text())["model"] == "sonnet", f.name


def test_A01_loader_returns_eight_sonnet_roles():
    roles = load_roles()
    assert set(roles) == set(ROLES8) and len(roles) == 8
    assert {r.model for r in roles.values()} == {"sonnet"}


def test_A01_loader_rejects_opus_unless_allow_models_lists_it(tmp_path):
    d = role_copy(tmp_path)
    edit(d, "implement", model="opus")
    with pytest.raises(RoleError) as e:
        load_roles(d)
    assert e.value.role == "implement" and e.value.field == "model"
    # literal reading of "unless the profile's allow_models list names it": keyword argument
    assert load_roles(d, allow_models=["opus"])["implement"].model == "opus"
    with pytest.raises(RoleError):
        load_roles(d, allow_models=["haiku"])  # a different model does not allow opus


def test_A01_every_generated_agent_file_carries_sonnet_and_there_are_eight():
    out = generated()
    assert set(out) == {f".claude/agents/{r}.md" for r in ROLES8}
    for path, text in out.items():
        assert yaml.safe_load(text.split("---")[1])["model"] == "sonnet", path


def test_A01_default_profile_has_no_allow_models(rig):
    assert rig.install().returncode == 0
    assert "allow_models" not in (rig.proj / ".factory/profile.yaml").read_text()


def test_A01_installer_refuses_opus_role_by_default_and_honours_allow_model(rig):
    rig.set_role("implement", model="opus")
    r = rig.install()
    assert r.returncode == 1 and "opus" in (r.stdout + r.stderr) and "implement" in (r.stdout + r.stderr)
    assert not (rig.proj / ".claude/agents/implement.md").exists()  # nothing half-written
    assert rig.install("--allow-model", "opus").returncode == 0
    assert rig.agent_fm("implement")["model"] == "opus"
    assert rig.agent_fm("qa")["model"] == "sonnet"


def test_A01_profile_allow_models_key_allows_the_model(rig):
    rig.set_role("implement", model="opus")
    prof = rig.tmp / "prof.yaml"
    prof.write_text("schema_version: 1\nproject: {name: p}\npaths: {eval: ['evals/**']}\nallow_models: [opus]\n")
    r = rig.install("--profile", prof)
    assert r.returncode == 0, r.stderr
    assert rig.agent_fm("implement")["model"] == "opus"


# ---------------------------------------------------------------- A-02 qa role
def test_A02_qa_role_spec_exact():
    q = load_roles()["qa"]
    assert q.id == "qa" and q.model == "sonnet"
    assert q.core_tools == ("Read", "Glob", "Grep", "Write", "Edit", "Bash")
    assert q.skills == ("qa-supervisor", "superpowers:verification-before-completion")
    assert q.hooks == ("path_guard", "secrets_guard", "bash_guard", "subagent_stop")
    assert q.blind is False
    assert q.spawns == ()
    assert q.writes == "qa_paths"  # the new writes class named after its path set
    for kw in ("run", "protected", "feedback", "attempt", "regression"):
        assert kw in q.description.lower(), kw
    assert "never" in q.description.lower() and "test source" in q.description.lower()


def test_A02_qa_cannot_spawn_or_write_application_code():
    q = load_roles()["qa"]
    assert q.writes not in ("app", "eval_paths", "none") and q.spawns == ()
    assert not any(t.startswith("Agent") for t in q.core_tools)
    assert "Agent" not in yaml.safe_load(generated()[".claude/agents/qa.md"].split("---")[1])["tools"]


def test_A02_generated_qa_file_tool_list_exact():
    fm = yaml.safe_load(generated()[".claude/agents/qa.md"].split("---")[1])
    assert fm["name"] == "qa"
    assert fm["tools"] == "Read, Glob, Grep, Write, Edit, Bash"
    assert fm["skills"] == ["qa-supervisor", "superpowers:verification-before-completion"]


def test_A02_qa_paths_documented_in_roles_doc():
    text = (REPO / "docs/hooks/roles.md").read_text()
    assert "qa_paths" in text


def test_A02_other_roles_do_not_gain_qa_writes():
    for rid, spec in load_roles().items():
        if rid != "qa":
            assert spec.writes != "qa_paths", rid


# ---------------------------------------------------------------- A-03 graph
def test_A03_default_graph_order_implement_qa_review():
    g = default_graph()
    order = g.order()
    assert {s.id for s in g.stages} >= {"implement", "qa", "test", "review"}
    assert next(s.role for s in g.stages if s.id == "qa") == "qa"
    assert next(s.role for s in g.stages if s.id == "test") == "test"  # retained as the runner
    assert order.index("implement") < order.index("qa") < order.index("review")
    assert "test" in order


def test_A03_loops_are_exactly_qa_and_review_back_to_implement():
    assert {tuple(x) for x in default_graph().loops} == {("qa", "implement"), ("review", "implement")}


def test_A03_undeclared_cycle_still_rejected_declared_loop_accepted():
    g = default_graph()
    bad = Graph(g.stages, [*g.edges, ("qa", "implement")], g.loops, g.subsets)
    with pytest.raises(GraphError):
        bad.validate()
    Graph(g.stages, g.edges, g.loops, g.subsets).validate()


def test_A03_small_subset_contains_qa_and_keeps_the_rest():
    g = default_graph()
    assert set(g.subsets["small"]) == {"orchestrator", "implement", "qa", "test", "review"}
    sel = g.select("small")
    sel.validate()
    assert "qa" in {s.role for s in sel.stages}


def test_A03_default_graph_covers_all_eight_roles():
    assert {s.role for s in default_graph().stages} == set(ROLES8)


# ---------------------------------------------------------------- A-04 reviewer
def test_A04_reviewer_skill_list_exact():
    assert load_roles()["review"].skills == (
        "implementation-review", "code-review:code-review", "mermaid-nesting-dolls", "minesweeper", "doc-sync")


def test_A04_ponytail_rubric_has_the_five_questions():
    text = (REPO / "skills/implementation-review/ponytail-rubric.md").read_text()
    low = text.lower()
    assert sum(1 for l in text.splitlines() if l.strip().rstrip("*_`").endswith("?")) >= 5
    assert "need to exist" in low
    assert "already" in low and "codebase" in low.replace("code base", "codebase")
    assert ("stdlib" in low or "standard library" in low) and "dependency" in low
    assert "unreachable" in low and "speculative" in low
    assert "branch" in low and ("covered" in low or "tested" in low)


def test_A04_implementation_review_skill_tells_reviewer_to_apply_rubric():
    text = (REPO / "skills/implementation-review/SKILL.md").read_text()
    assert "ponytail-rubric.md" in text


def test_A04_reviewer_text_states_approval_conditions(rig):
    assert rig.install().returncode == 0
    body = (rig.proj / ".claude/agents/review.md").read_text()
    assert "sf slice done" in body
    assert "doc-sync" in body and "stale" in body.lower()
    assert "sf slice amend --role reviewer" in body
    assert [s for s in rig.agent_fm("review")["skills"]] == list(load_roles()["review"].skills)


def test_A04_review_still_cannot_write():
    r = load_roles()["review"]
    assert r.writes == "none" and "Write" not in r.core_tools and "Edit" not in r.core_tools


# ---------------------------------------------------------------- A-05 design
def test_A05_design_uses_prd_writer_not_prd_designer():
    sk = load_roles()["design"].skills
    assert "prd-writer" in sk and "prd-designer" not in sk
    assert (REPO / "skills/prd-writer/SKILL.md").is_file()
    for s in ("axiomatic-spec", "one-way-door"):
        assert s in sk  # the rest of the list is unchanged
