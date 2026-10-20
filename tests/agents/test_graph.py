"""Unit coverage for factory.agents.graph (TB-12). Not the acceptance gate."""
import pytest

from factory.agents.graph import Graph, GraphError, default_graph, load_graph
from factory.agents.profile import Stage, parse_profile


def profile_with(graph=None):
    data = {"schema_version": 1, "project": {"name": "p"}, "paths": {"eval": ["e/**"]}}
    if graph is not None:
        data["graph"] = graph
    return parse_profile(data)


def st(i, role, gate=False):
    return Stage(id=i, role=role, gate=gate)


def chain():
    return Graph([st("c", "implement"), st("a", "orchestrator"), st("b", "test")],
                 [("a", "b"), ("b", "c")])


def test_default_graph_validates_with_eight_roles():
    g = load_graph(profile_with())
    assert {s.role for s in g.stages} == {"orchestrator", "research", "design", "audit",
                                          "implement", "qa", "test", "review"}
    assert len(g.stages) == 8
    assert g.order() == ["orchestrate", "research", "design", "audit", "implement", "qa", "test", "review"]
    assert set(g.loops) == {("qa", "implement"), ("review", "implement")}


def test_profile_graph_is_used():
    g = load_graph(profile_with({"stages": [{"id": "x", "role": "test"}]}))
    assert [s.id for s in g.stages] == ["x"]


def test_order_is_topological_and_ties_by_id():
    g = Graph([st("z", "test"), st("m", "review"), st("a", "orchestrator")],
              [("a", "z"), ("a", "m")])
    assert g.order() == ["a", "m", "z"]


def test_order_ignores_loops():
    g = Graph([st("a", "orchestrator"), st("b", "test")], [("a", "b")], [("b", "a")])
    g.validate()
    assert g.order() == ["a", "b"]


def test_cycle_rejected_naming_edge():
    g = Graph([st("a", "orchestrator"), st("b", "test"), st("c", "review")],
              [("a", "b"), ("b", "c"), ("c", "b")])
    with pytest.raises(GraphError, match="cycle"):
        g.validate()


def test_self_edge_is_cycle():
    with pytest.raises(GraphError):
        Graph([st("a", "orchestrator")], [("a", "a")]).validate()


def test_same_back_reference_in_loops_accepted():
    Graph([st("a", "orchestrator"), st("b", "test")], [("a", "b")], [("b", "a")]).validate()


def test_duplicate_id():
    with pytest.raises(GraphError, match="'a'"):
        Graph([st("a", "test"), st("a", "review")]).validate()


def test_unknown_role():
    with pytest.raises(GraphError, match="'a'"):
        Graph([st("a", "janitor")]).validate()


def test_unknown_edge_and_loop_endpoint():
    with pytest.raises(GraphError, match="ghost"):
        Graph([st("a", "test")], [("a", "ghost")]).validate()
    with pytest.raises(GraphError, match="ghost"):
        Graph([st("a", "test")], [], [("ghost", "a")]).validate()


def test_empty_stages():
    with pytest.raises(GraphError):
        Graph([]).validate()


def test_gate_flag_only_and_gates_in_order():
    g = Graph([st("b", "test", True), st("a", "review"), st("c", "implement", True)],
              [("c", "b"), ("b", "a")])
    g.validate()
    assert g.gates() == ["c", "b"]


def test_default_gates():
    assert default_graph().gates() == ["audit", "review"]


def test_small_subset_selects_and_validates():
    g = default_graph().select("small")
    g.validate()
    assert {s.role for s in g.stages} == {"orchestrator", "implement", "qa", "test", "review"}
    assert g.order() == ["orchestrate", "implement", "qa", "test", "review"]
    assert ("orchestrate", "implement") in g.edges


def test_select_keeps_loops_only_with_both_endpoints():
    g = Graph([st("a", "orchestrator"), st("b", "research"), st("c", "test")],
              [("a", "b"), ("b", "c")], [("c", "a"), ("c", "b")],
              {"s": ["orchestrator", "test"]})
    s = g.select("s")
    assert s.loops == (("c", "a"),)
    assert s.edges == (("a", "c"),)


def test_select_unknown_subset():
    with pytest.raises(GraphError, match="nope"):
        default_graph().select("nope")


def test_select_empty_result_raises():
    g = Graph([st("a", "orchestrator")], [], [], {"s": ["review"]})
    with pytest.raises(GraphError):
        g.select("s")


def test_graph_is_read_only():
    g = chain()
    with pytest.raises(AttributeError):
        g.stages = ()
    assert isinstance(g.stages, tuple) and isinstance(g.edges, tuple) and isinstance(g.loops, tuple)


def test_unreachable_cannot_exist_in_dag_but_orphans_are_starts():
    g = Graph([st("a", "orchestrator"), st("b", "test")])
    g.validate()
    assert g.order() == ["a", "b"]
