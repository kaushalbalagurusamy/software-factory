"""TB-12 stage graph as data: golden and diagnostic cases.

Expectations come only from docs/contracts/graph-and-ledger.md (Graph section), docs/contracts/profile.md
and docs/prds/TB-12-graph.md. Where the contract leaves open whether a graph problem surfaces from
load_graph or from validate(), a rejection from either counts (ambiguities A-20). Where TB-01's check order
lists `graph` while TB-01 puts graph validation out of scope, a ProfileError on the graph field also counts
as the rejection (ambiguities A-02).
"""
from __future__ import annotations

from collections.abc import Mapping

import pytest
import yaml

from evals.agents import lib

ROLES = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]
DEFAULT_GRAPH = lib.REPO / "factory" / "agents" / "default_graph.yaml"


def case(cid, tier, reqs=("R-03",)):
    return pytest.mark.case(cid, tier=tier, tb="12", reqs=list(reqs))


def mods():
    prof = lib.need("factory.agents.profile", "load_profile", "ProfileError")
    g = lib.need("factory.agents.graph", "load_graph", "GraphError")
    return prof, g


def with_graph(graph):
    d = lib.profile_dict("base")
    d["graph"] = graph
    return d


def graph_of(tmp_path, data="base", sub="p"):
    prof, g = mods()
    root = lib.make_project(tmp_path / sub, data)
    return g.load_graph(prof.load_profile(root / ".factory" / "profile.yaml"))


def valid(tmp_path, data="base", sub="p"):
    gr = graph_of(tmp_path, data, sub)
    gr.validate()
    return gr


def rejection(tmp_path, graph, sub="p"):
    """Return the text of the rejection (GraphError from load_graph/validate, or ProfileError on graph)."""
    prof, g = mods()
    root = lib.make_project(tmp_path / sub, with_graph(graph))
    try:
        p = prof.load_profile(root / ".factory" / "profile.yaml")
    except prof.ProfileError as e:
        assert str(getattr(e, "field", "")).startswith("graph"), f"unexpected ProfileError field {e.field}"
        return f"{e} {e.field} {getattr(e, 'message', '')}"
    with pytest.raises(g.GraphError) as info:
        gr = g.load_graph(p)
        gr.validate()
    return str(info.value)


def ids(items):
    out = []
    for x in items:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, Mapping):
            out.append(x["id"])
        else:
            out.append(getattr(x, "id"))
    return out


def st(i, role, gate=None):
    s = {"id": i, "role": role}
    if gate is not None:
        s["gate"] = gate
    return s


def default_graph_data():
    mods()
    assert DEFAULT_GRAPH.exists(), "PRD behaviour 5: factory/agents/default_graph.yaml ships as data"
    data = yaml.safe_load(DEFAULT_GRAPH.read_text())
    return data["graph"] if isinstance(data, Mapping) and "graph" in data else data


# ---------------------------------------------------------------- golden

@case("TB12-G-001", "golden")
def test_g001_base_graph_validates_and_orders(tmp_path):
    """Behaviours 1-2: the base fixture graph validates; order() is the topological order over edges."""
    assert list(valid(tmp_path).order()) == ["spec", "evals", "build", "review"]


@case("TB12-G-002", "golden")
def test_g002_cycle_in_edges_rejected(tmp_path):
    """Behaviour 3 + contract: edges contain no cycle; a cycle is rejected with GraphError."""
    rejection(tmp_path, {"stages": [st("a", "design"), st("b", "implement")], "edges": [["a", "b"], ["b", "a"]]})


@case("TB12-G-003", "golden")
def test_g003_back_reference_in_loops_accepted(tmp_path):
    """Behaviour 3: the same back-reference declared in loops is accepted."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "design"), st("b", "implement")],
                                     "edges": [["a", "b"]], "loops": [["b", "a"]]}))
    assert list(gr.order()) == ["a", "b"]


@case("TB12-G-004", "golden")
def test_g004_unknown_role_rejected_naming_stage(tmp_path):
    """Behaviour 1 + contract: every stage's role is one of the seven; the error names the offending stage."""
    msg = rejection(tmp_path, {"stages": [st("alpha", "design"), st("magicstage", "wizard")],
                               "edges": [["alpha", "magicstage"]]})
    assert "magicstage" in msg


@case("TB12-G-005", "golden")
def test_g005_select_reconnects_across_removed_stage(tmp_path):
    """Behaviour 4: select keeps only stages whose role is in the subset and reconnects edges across removed
    stages: z -> m -> a with m removed keeps the edge z -> a, so order() is [z, a] (not the id tie order)."""
    gr = valid(tmp_path, with_graph({"stages": [st("z", "test"), st("m", "design"), st("a", "review")],
                                     "edges": [["z", "m"], ["m", "a"]],
                                     "subsets": {"lean": ["test", "review"]}}))
    assert list(gr.select("lean").order()) == ["z", "a"]


@case("TB12-G-006", "golden")
def test_g006_default_graph_and_small_subset(tmp_path):
    """Behaviour 5: the shipped default seven-role graph validates, and its `small` subset (orchestrator,
    implement, test, review) selects and validates."""
    gr = valid(tmp_path, with_graph(default_graph_data()))
    small = gr.select("small")
    small.validate()
    assert small.order()


@case("TB12-G-007", "golden")
def test_g007_gates_in_order(tmp_path):
    """Behaviour 6: gate stages are reported by gates() in order (base: spec and review are gate: true)."""
    assert ids(valid(tmp_path).gates()) == ["spec", "review"]


# ---------------------------------------------------------------- diagnostic

@case("TB12-D-001", "diagnostic")
def test_d001_alt_graph(tmp_path):
    """Generality: the alt fixture's different graph validates and orders as its own edges say."""
    assert list(valid(tmp_path, "alt").order()) == ["build", "verify"]


@case("TB12-D-002", "diagnostic")
def test_d002_duplicate_stage_id(tmp_path):
    """Contract: every stage id is unique; the error names the offending stage."""
    msg = rejection(tmp_path, {"stages": [st("dupstage", "design"), st("dupstage", "test")], "edges": []})
    assert "dupstage" in msg


@case("TB12-D-003", "diagnostic")
def test_d003_edge_endpoint_missing(tmp_path):
    """Contract: every edge endpoint exists; the error names the offending edge endpoint."""
    msg = rejection(tmp_path, {"stages": [st("a", "design")], "edges": [["a", "ghoststage"]]})
    assert "ghoststage" in msg


@case("TB12-D-004", "diagnostic")
def test_d004_loop_endpoint_missing(tmp_path):
    """Contract: every loop endpoint exists."""
    msg = rejection(tmp_path, {"stages": [st("a", "design"), st("b", "implement")], "edges": [["a", "b"]],
                               "loops": [["phantomstage", "a"]]})
    assert "phantomstage" in msg


@case("TB12-D-005", "diagnostic")
def test_d005_self_edge(tmp_path):
    """Contract: edges contain no cycle; a self edge is a cycle."""
    rejection(tmp_path, {"stages": [st("a", "design"), st("b", "test")], "edges": [["a", "b"], ["b", "b"]]})


@case("TB12-D-006", "diagnostic")
def test_d006_three_cycle_named(tmp_path):
    """Behaviour 1 + 3: a longer cycle is rejected and the error names a stage or edge in it."""
    msg = rejection(tmp_path, {"stages": [st("s0", "orchestrator"), st("c1", "design"), st("c2", "implement"),
                                          st("c3", "test")],
                               "edges": [["s0", "c1"], ["c1", "c2"], ["c2", "c3"], ["c3", "c1"]]})
    assert any(x in msg for x in ["c1", "c2", "c3"])


@case("TB12-D-007", "diagnostic")
def test_d007_back_reference_in_edges_rejected(tmp_path):
    """Contract: a back-reference is allowed only as a declared entry in loops (the base review->build loop
    written as an edge is rejected)."""
    g = lib.profile_dict("base")["graph"]
    g["edges"] = g["edges"] + [["review", "build"]]
    g.pop("loops", None)
    rejection(tmp_path, g)


@case("TB12-D-008", "diagnostic")
def test_d008_order_ties_by_id(tmp_path):
    """Behaviour 2: ties are broken by stage id (no edges: sorted ids, whatever the declaration order)."""
    gr = valid(tmp_path, with_graph({"stages": [st("c", "test"), st("a", "design"), st("b", "review")],
                                     "edges": []}))
    assert list(gr.order()) == ["a", "b", "c"]


@case("TB12-D-009", "diagnostic")
def test_d009_order_diamond(tmp_path):
    """Behaviour 2: a diamond s -> {b, a} -> t orders its tied middle stages by id."""
    gr = valid(tmp_path, with_graph({"stages": [st("t", "review"), st("b", "test"), st("a", "implement"),
                                                st("s", "design")],
                                     "edges": [["s", "b"], ["s", "a"], ["b", "t"], ["a", "t"]]}))
    assert list(gr.order()) == ["s", "a", "b", "t"]


@case("TB12-D-010", "diagnostic")
def test_d010_order_deterministic(tmp_path):
    """Behaviour 2: order() is deterministic across calls and loads."""
    assert list(valid(tmp_path, "base", "a").order()) == list(valid(tmp_path, "base", "b").order())
    gr = valid(tmp_path, "base", "c")
    assert list(gr.order()) == list(gr.order())


@case("TB12-D-011", "diagnostic")
def test_d011_order_ignores_loops(tmp_path):
    """Contract: order() is over edges, ignoring loops (a loop to an earlier stage does not reorder)."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "design"), st("b", "implement"), st("c", "review")],
                                     "edges": [["a", "b"], ["b", "c"]], "loops": [["c", "a"], ["c", "b"]]}))
    assert list(gr.order()) == ["a", "b", "c"]


@case("TB12-D-012", "diagnostic")
def test_d012_select_keeps_only_subset_roles(tmp_path):
    """Behaviour 4: select keeps only stages whose role is in the subset (start and end stages kept)."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "orchestrator"), st("b", "design"), st("c", "implement"),
                                                st("d", "review")],
                                     "edges": [["a", "b"], ["b", "c"], ["c", "d"]],
                                     "subsets": {"core": ["orchestrator", "implement", "review"]}}))
    sel = gr.select("core")
    sel.validate()
    assert list(sel.order()) == ["a", "c", "d"]


@case("TB12-D-013", "diagnostic")
def test_d013_select_unknown_subset(tmp_path):
    """Behaviour 4: select raises if the subset name is unknown."""
    gr = valid(tmp_path)
    with pytest.raises(Exception):
        gr.select("no-such-subset")


@case("TB12-D-014", "diagnostic")
def test_d014_select_removing_everything(tmp_path):
    """Behaviour 4 + contract: select raises if the subset removes every start and end stage (here every stage)."""
    gr = valid(tmp_path, with_graph({"stages": [st("build", "implement"), st("verify", "test")],
                                     "edges": [["build", "verify"]], "subsets": {"docs_only": ["design"]}}))
    with pytest.raises(Exception):
        gr.select("docs_only")


@case("TB12-D-015", "diagnostic")
def test_d015_default_graph_covers_seven_roles(tmp_path):
    """Behaviour 5: the default graph is a seven-role graph (every role has a stage)."""
    data = default_graph_data()
    valid(tmp_path, with_graph(data))
    roles = {s["role"] for s in data["stages"]}
    assert roles == set(ROLES)


@case("TB12-D-016", "diagnostic")
def test_d016_default_small_roles(tmp_path):
    """Behaviour 5: the default small subset is orchestrator, implement, test, review; the selected graph keeps
    only stages with those roles."""
    data = default_graph_data()
    assert sorted(data["subsets"]["small"]) == sorted(["orchestrator", "implement", "test", "review"])
    gr = valid(tmp_path, with_graph(data))
    kept = set(gr.select("small").order())
    expected = {s["id"] for s in data["stages"] if s["role"] in {"orchestrator", "implement", "test", "review"}}
    assert kept == expected


@case("TB12-D-017", "diagnostic")
def test_d017_gates_exclude_non_gates(tmp_path):
    """Behaviour 6: only gate stages are reported; a graph with no gate: true stage reports none (alt)."""
    assert ids(valid(tmp_path, "alt").gates()) == []
    gr = valid(tmp_path, with_graph({"stages": [st("a", "design", True), st("b", "implement", False),
                                                st("c", "review", True)],
                                     "edges": [["a", "b"], ["b", "c"]]}))
    assert ids(gr.gates()) == ["a", "c"]


@case("TB12-D-018", "diagnostic")
def test_d018_every_role_accepted(tmp_path):
    """Negative control: a chain with one stage per role of the seven validates."""
    stages = [st(f"s{i}", r) for i, r in enumerate(ROLES)]
    edges = [[f"s{i}", f"s{i + 1}"] for i in range(len(ROLES) - 1)]
    assert list(valid(tmp_path, with_graph({"stages": stages, "edges": edges})).order()) == [s["id"] for s in stages]


@case("TB12-D-019", "diagnostic")
def test_d019_empty_graph_has_no_end_stage(tmp_path):
    """Contract: at least one end stage exists; a graph with no stages is rejected."""
    rejection(tmp_path, {"stages": [], "edges": []})


@case("TB12-D-020", "diagnostic")
def test_d020_select_keeps_gates_of_kept_stages(tmp_path):
    """Behaviours 4 + 6: after select, gates() reports only the kept gate stages."""
    gr = valid(tmp_path, with_graph({"stages": [st("z", "test", True), st("m", "design", True),
                                                st("a", "review")],
                                     "edges": [["z", "m"], ["m", "a"]], "subsets": {"lean": ["test", "review"]}}))
    assert ids(gr.select("lean").gates()) == ["z"]


@case("TB12-D-021", "diagnostic")
def test_d021_select_multi_hop_reconnect(tmp_path):
    """Behaviour 4: reconnection spans several consecutive removed stages (y -> m1 -> m2 -> b becomes y -> b)."""
    gr = valid(tmp_path, with_graph({"stages": [st("y", "implement"), st("m1", "design"), st("m2", "research"),
                                                st("b", "review")],
                                     "edges": [["y", "m1"], ["m1", "m2"], ["m2", "b"]],
                                     "subsets": {"lean": ["implement", "review"]}}))
    assert list(gr.select("lean").order()) == ["y", "b"]


@case("TB12-D-022", "diagnostic")
def test_d022_select_is_deterministic(tmp_path):
    """Behaviours 2 + 4: selecting the same subset twice gives the same order."""
    g = {"stages": [st("z", "test"), st("m", "design"), st("a", "review")], "edges": [["z", "m"], ["m", "a"]],
         "subsets": {"lean": ["test", "review"]}}
    gr = valid(tmp_path, with_graph(g))
    assert list(gr.select("lean").order()) == list(gr.select("lean").order())


@case("TB12-D-023", "diagnostic")
def test_d023_valid_graph_does_not_raise_for_multiple_starts(tmp_path):
    """Negative control: several start stages (no incoming edges) are valid; ties among them break by id."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "research"), st("b", "design"), st("c", "implement"),
                                                st("d", "test")],
                                     "edges": [["a", "c"], ["b", "c"], ["c", "d"]]}))
    assert list(gr.order()) == ["a", "b", "c", "d"]
