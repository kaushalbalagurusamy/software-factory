"""TB-12 stage graph as data: golden and diagnostic cases.

Expectations come only from docs/contracts/graph-and-ledger.md (Graph section), docs/contracts/profile.md,
docs/prds/TB-12-graph.md and the binding docs/contracts/clarifications.md (bracketed ids cite it).
load_graph builds and validates, raising GraphError [A-20]; the profile loader checks only graph shape [A-02],
so a well-shaped graph with a semantic problem loads and load_graph raises. gates() returns stage ids [A-30].
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
    """[A-20] + [A-02]: the well-shaped profile loads; load_graph raises GraphError. Returns its text."""
    prof, g = mods()
    root = lib.make_project(tmp_path / sub, with_graph(graph))
    p = prof.load_profile(root / ".factory" / "profile.yaml")
    with pytest.raises(g.GraphError) as info:
        g.load_graph(p)
    return str(info.value)


def ids(items):
    """[A-30]: gates() returns a list of stage ids."""
    assert isinstance(items, list) and all(isinstance(x, str) for x in items), items
    return items


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
    """Behaviour 6 + [A-26]: a stage is a gate iff gate: true (role does not matter); alt reports none."""
    assert ids(valid(tmp_path, "alt").gates()) == []
    gr = valid(tmp_path, with_graph({"stages": [st("a", "design", True), st("b", "implement", False),
                                                st("c", "review", True), st("d", "design")],
                                     "edges": [["a", "b"], ["b", "c"], ["c", "d"]]}))
    assert ids(gr.gates()) == ["a", "c"]


@case("TB12-D-018", "diagnostic")
def test_d018_every_role_accepted(tmp_path):
    """Negative control: a chain with one stage per role of the seven validates."""
    stages = [st(f"s{i}", r) for i, r in enumerate(ROLES)]
    edges = [[f"s{i}", f"s{i + 1}"] for i in range(len(ROLES) - 1)]
    assert list(valid(tmp_path, with_graph({"stages": stages, "edges": edges})).order()) == [s["id"] for s in stages]


@case("TB12-D-019", "diagnostic")
def test_d019_empty_graph_has_no_end_stage(tmp_path):
    """Contract + [A-31]: an empty stages list is rejected (GraphError, or ProfileError on the shape)."""
    prof, g = mods()
    root = lib.make_project(tmp_path, with_graph({"stages": [], "edges": []}))
    with pytest.raises((g.GraphError, prof.ProfileError)):
        g.load_graph(prof.load_profile(root / ".factory" / "profile.yaml"))


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


# ---------------------------------------------------------------- added after docs/contracts/clarifications.md

def profile_without_graph(tmp_path, sub="ng"):
    prof, g = mods()
    d = lib.profile_dict("base")
    d.pop("graph", None)
    root = lib.make_project(tmp_path / sub, d)
    return prof.load_profile(root / ".factory" / "profile.yaml")


@case("TB12-G-008", "golden")
def test_g008_kahn_smallest_ready_id(tmp_path):
    """Behaviour 2 + [A-27]: order() is Kahn's algorithm always taking the smallest ready id: starts a, z with
    edges z->m, a->n give [a, n, z, m] (n becomes ready before z is taken)."""
    gr = valid(tmp_path, with_graph({"stages": [st("z", "design"), st("a", "research"), st("m", "implement"),
                                                st("n", "test")],
                                     "edges": [["z", "m"], ["a", "n"]]}))
    assert list(gr.order()) == ["a", "n", "z", "m"]


@case("TB12-D-024", "diagnostic")
def test_d024_base_small_selects(tmp_path):
    """[A-25]: select raises only if the result has no start, no end or no stages; base `small` drops only the
    start stage spec, leaving evals -> build -> review, which is valid."""
    sel = valid(tmp_path).select("small")
    sel.validate()
    assert list(sel.order()) == ["evals", "build", "review"]


@case("TB12-D-025", "diagnostic")
def test_d025_load_graph_raises_directly(tmp_path):
    """[A-20]: load_graph itself validates and raises GraphError (validate() is not needed to see it)."""
    prof, g = mods()
    root = lib.make_project(tmp_path, with_graph({"stages": [st("a", "design"), st("a", "test")], "edges": []}))
    p = prof.load_profile(root / ".factory" / "profile.yaml")
    with pytest.raises(g.GraphError):
        g.load_graph(p)


@case("TB12-D-026", "diagnostic")
def test_d026_no_graph_uses_default(tmp_path):
    """[A-28]: with no graph in the profile, load_graph uses the shipped default graph."""
    _, g = mods()
    gr = g.load_graph(profile_without_graph(tmp_path))
    ref = valid(tmp_path, with_graph(default_graph_data()), "ref")
    assert list(gr.order()) == list(ref.order())
    assert gr.gates() == ref.gates()


@case("TB12-D-027", "diagnostic")
def test_d027_default_subsets_selectable(tmp_path):
    """[A-29]: subset names are keys of graph.subsets or of the default graph's subsets; with no graph in the
    profile, select("small") works."""
    _, g = mods()
    sel = g.load_graph(profile_without_graph(tmp_path)).select("small")
    sel.validate()
    assert sel.order()


@case("TB12-D-028", "diagnostic")
def test_d028_select_drops_loop_with_removed_endpoint(tmp_path):
    """[A-29]: select keeps a loop only if both endpoints are kept, so a loop into a removed stage does not make
    the selected graph invalid."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "test"), st("b", "design"), st("c", "review")],
                                     "edges": [["a", "b"], ["b", "c"]], "loops": [["c", "b"]],
                                     "subsets": {"lean": ["test", "review"]}}))
    sel = gr.select("lean")
    sel.validate()
    assert list(sel.order()) == ["a", "c"]


@case("TB12-D-029", "diagnostic")
def test_d029_gates_in_topological_order(tmp_path):
    """[A-30]: gates() lists stage ids in order() order, not declaration order."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "review", True), st("c", "design", True)],
                                     "edges": [["c", "a"]]}))
    assert ids(gr.gates()) == ["c", "a"]


@case("TB12-D-030", "diagnostic")
def test_d030_select_unknown_subset_graph_error_or_raise(tmp_path):
    """[A-29]: subset names are keys of graph.subsets; a role id that is not a subset name is unknown."""
    gr = valid(tmp_path)
    with pytest.raises(Exception):
        gr.select("implement")


# ---------------------------------------------------------------- added after clarifications, third round

@case("TB12-D-031", "diagnostic")
def test_d031_select_keeps_loop_only_with_both_endpoints(tmp_path):
    """[A-29]: select keeps a loop only if both its endpoints are kept and drops the others; edges are
    reconnected across the removed stage. Read through Graph.loops and Graph.edges (tuples of (from, to))."""
    gr = valid(tmp_path, with_graph({"stages": [st("a", "test"), st("b", "implement"), st("c", "design"),
                                                st("d", "review")],
                                     "edges": [["a", "b"], ["b", "c"], ["c", "d"]],
                                     "loops": [["d", "b"], ["c", "a"]],
                                     "subsets": {"lean": ["test", "implement", "review"]}}))
    sel = gr.select("lean")
    assert set(sel.loops) == {("d", "b")}
    assert set(sel.edges) == {("a", "b"), ("b", "d")}
    assert {s.id for s in sel.stages} == {"a", "b", "d"}


@case("TB12-D-032", "diagnostic")
def test_d032_graph_attributes(tmp_path):
    """[A-29]: Graph exposes stages (tuple of objects with id, role, gate), edges and loops (tuples of
    (from_id, to_id)) for the base fixture."""
    gr = valid(tmp_path)
    assert isinstance(gr.stages, tuple) and isinstance(gr.edges, tuple) and isinstance(gr.loops, tuple)
    assert {(s.id, s.role, bool(s.gate)) for s in gr.stages} == {
        ("spec", "design", True), ("evals", "test", False), ("build", "implement", False), ("review", "review", True)}
    assert set(gr.edges) == {("spec", "evals"), ("evals", "build"), ("build", "review")}
    assert set(gr.loops) == {("review", "build")}
    assert all(isinstance(e, tuple) and len(e) == 2 for e in gr.edges + gr.loops)


@case("TB12-D-033", "diagnostic")
def test_d033_graph_attributes_read_only(tmp_path):
    """[A-29]: the attributes are read-only; assigning one raises."""
    gr = valid(tmp_path)
    for name in ["stages", "edges", "loops"]:
        with pytest.raises(Exception):
            setattr(gr, name, ())
