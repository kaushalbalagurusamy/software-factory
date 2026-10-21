"""SFN-02 unit coverage: eight Sonnet roles, qa role, allow_models, graph, reviewer skills."""
import shutil

import pytest
import yaml

from factory.agents.generate import generate_agents
from factory.agents.graph import default_graph
from factory.agents.profile import parse_profile
from factory.agents.roles import DEFAULT_DIR, ROLE_IDS, RoleError, load_roles

PROFILE = {"schema_version": 1, "project": {"name": "demo"}, "paths": {"eval": ["evals/**"]}}


def test_eight_roles_all_sonnet():
    roles = load_roles()
    assert tuple(roles) == ROLE_IDS and len(roles) == 8
    assert {r.model for r in roles.values()} == {"sonnet"}


def test_qa_role_shape():
    qa = load_roles()["qa"]
    assert qa.writes == "qa_paths" and not qa.blind and qa.spawns == ()
    assert qa.core_tools == ("Read", "Glob", "Grep", "Write", "Edit", "Bash")
    assert qa.skills == ("qa-supervisor", "superpowers:verification-before-completion")
    assert qa.hooks == ("path_guard", "secrets_guard", "bash_guard", "subagent_stop")


def test_reviewer_and_design_skills():
    roles = load_roles()
    assert roles["review"].skills == ("implementation-review", "code-review:code-review",
                                      "mermaid-nesting-dolls", "minesweeper", "doc-sync")
    assert "prd-writer" in roles["design"].skills and "prd-designer" not in roles["design"].skills


@pytest.fixture
def roles_copy(tmp_path):
    d = tmp_path / "roles"
    shutil.copytree(DEFAULT_DIR, d)
    p = d / "test.yaml"
    p.write_text(p.read_text().replace("model: sonnet", "model: opus"))
    return d


def test_non_sonnet_model_rejected_unless_allowed(roles_copy):
    with pytest.raises(RoleError) as e:
        load_roles(roles_copy)
    assert (e.value.role, e.value.field) == ("test", "model")
    assert load_roles(roles_copy, allow_models=["opus"])["test"].model == "opus"
    with pytest.raises(RoleError):
        load_roles(roles_copy, allow_models=["haiku"])


def test_profile_allow_models_parsed_and_default_empty():
    assert parse_profile(PROFILE).allow_models == ()
    assert parse_profile({**PROFILE, "allow_models": ["opus"]}).allow_models == ("opus",)
    with pytest.raises(Exception):
        parse_profile({**PROFILE, "allow_models": "opus"})


def test_generates_eight_files_with_qa_paths():
    out = generate_agents(parse_profile(PROFILE), load_roles())
    assert len(out) == 8
    qa = out[".claude/agents/qa.md"]
    assert "docs/slices/*/qa-notes.md" in qa and ".sf/slices/**" in qa and "model: sonnet" in qa
    assert all("model: sonnet" in t for t in out.values())


def test_default_graph_has_qa_between_implement_and_review():
    g = default_graph()
    order = g.order()
    assert order.index("implement") < order.index("qa") < order.index("test") < order.index("review")
    assert ("implement", "qa") in g.edges and ("qa", "test") in g.edges
    assert set(g.loops) == {("qa", "implement"), ("review", "implement")}
    small = g.select("small")
    assert [s.id for s in small.stages if s.role == "qa"] == ["qa"]


def test_reviewer_rubric_and_approval_rule():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "skills" / "implementation-review"
    skill = (root / "SKILL.md").read_text()
    rubric = (root / "ponytail-rubric.md").read_text()
    assert "ponytail-rubric.md" in skill and "sf slice amend" in skill and "doc-sync" in skill
    for q in ("need to exist", "already in the codebase", "standard library", "unreachable or speculative", "branch"):
        assert q in rubric
    desc = yaml.safe_load((DEFAULT_DIR / "review.yaml").read_text())["description"]
    assert "sf slice done" in desc and "doc-sync" in desc and "sf slice amend --role reviewer" in desc
