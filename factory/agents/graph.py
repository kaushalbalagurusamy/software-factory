"""Stage graph as data (TB-12).

Builds and validates the stages and gates a project runs, from the profile's ``graph``
section or the shipped default graph. Pure: no network, no model call, no project names.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from factory.agents.profile import (
    ROLE_IDS, FrozenMap, GraphSpec, Profile, Stage, parse_profile,
)

DEFAULT_GRAPH_PATH = Path(__file__).with_name("default_graph.yaml")


class GraphError(Exception):
    """An invalid graph; the message names the offending stage or edge."""


class Graph:
    """Immutable stage graph. ``edges`` are acyclic; ``loops`` are declared back-references."""

    __slots__ = ("_stages", "_edges", "_loops", "_subsets")

    def __init__(self, stages, edges=(), loops=(), subsets: Mapping | None = None) -> None:
        object.__setattr__(self, "_stages", tuple(stages))
        object.__setattr__(self, "_edges", tuple((a, b) for a, b in edges))
        object.__setattr__(self, "_loops", tuple((a, b) for a, b in loops))
        object.__setattr__(self, "_subsets", FrozenMap(
            {k: tuple(v) for k, v in (subsets or {}).items()}))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Graph is immutable")

    @property
    def stages(self) -> tuple[Stage, ...]:
        return self._stages

    @property
    def edges(self) -> tuple[tuple[str, str], ...]:
        return self._edges

    @property
    def loops(self) -> tuple[tuple[str, str], ...]:
        return self._loops

    @property
    def subsets(self) -> Mapping:
        return self._subsets

    def __repr__(self) -> str:
        return f"Graph(stages={[s.id for s in self._stages]}, edges={list(self._edges)}, loops={list(self._loops)})"

    # ------------------------------------------------------------ validation

    def validate(self) -> None:
        """Raise :class:`GraphError` naming the first problem found."""
        if not self._stages:
            raise GraphError("graph has no stages")
        seen: set[str] = set()
        for st in self._stages:
            if st.id in seen:
                raise GraphError(f"duplicate stage id {st.id!r}")
            seen.add(st.id)
        for st in self._stages:
            if st.role not in ROLE_IDS:
                raise GraphError(f"stage {st.id!r} has unknown role {st.role!r}")
        for kind, pairs in (("edge", self._edges), ("loop", self._loops)):
            for a, b in pairs:
                for end in (a, b):
                    if end not in seen:
                        raise GraphError(f"{kind} [{a}, {b}] names unknown stage {end!r}")
        self._check_acyclic()
        incoming = {b for _, b in self._edges}
        starts = [s.id for s in self._stages if s.id not in incoming]
        if not starts:
            raise GraphError("graph has no start stage")
        reach = set(starts)
        frontier = list(starts)
        while frontier:
            cur = frontier.pop()
            for a, b in self._edges:
                if a == cur and b not in reach:
                    reach.add(b)
                    frontier.append(b)
        for st in self._stages:
            if st.id not in reach:
                raise GraphError(f"stage {st.id!r} is not reachable from a start stage")
        outgoing = {a for a, _ in self._edges}
        if not any(s.id not in outgoing for s in self._stages):
            raise GraphError("graph has no end stage")

    def _check_acyclic(self) -> None:
        indeg = {s.id: 0 for s in self._stages}
        for _, b in self._edges:
            indeg[b] += 1
        ready = [i for i, d in indeg.items() if d == 0]
        removed: set[str] = set()
        while ready:
            cur = ready.pop()
            removed.add(cur)
            for a, b in self._edges:
                if a == cur:
                    indeg[b] -= 1
                    if indeg[b] == 0:
                        ready.append(b)
        if len(removed) != len(self._stages):
            for a, b in self._edges:
                if a not in removed and b not in removed:
                    raise GraphError(
                        f"edges contain a cycle through edge [{a}, {b}]; declare a back-reference under loops")
            raise GraphError("edges contain a cycle")  # pragma: no cover

    # ------------------------------------------------------------ queries

    def order(self) -> list[str]:
        """Topological order over ``edges`` (Kahn, always the smallest ready stage id)."""
        self.validate()
        return self._order()

    def _order(self) -> list[str]:
        indeg = {s.id: 0 for s in self._stages}
        for _, b in self._edges:
            indeg[b] += 1
        ready = sorted(i for i, d in indeg.items() if d == 0)
        out: list[str] = []
        while ready:
            cur = ready.pop(0)
            out.append(cur)
            for a, b in self._edges:
                if a == cur:
                    indeg[b] -= 1
                    if indeg[b] == 0:
                        ready.append(b)
            ready.sort()
        return out

    def gates(self) -> list[str]:
        """Ids of stages with ``gate: true``, in :meth:`order` order."""
        gate_ids = {s.id for s in self._stages if s.gate}
        return [i for i in self.order() if i in gate_ids]

    def select(self, subset_name: str) -> "Graph":
        """Keep stages whose role is in the named subset; reconnect edges across removed stages."""
        if not isinstance(subset_name, str) or subset_name not in self._subsets:
            raise GraphError(f"unknown subset {subset_name!r}")
        roles = set(self._subsets[subset_name])
        kept = [s for s in self._stages if s.role in roles]
        kept_ids = {s.id for s in kept}
        succ: dict[str, list[str]] = {s.id: [] for s in self._stages}
        for a, b in self._edges:
            succ[a].append(b)
        new_edges: set[tuple[str, str]] = set()
        for s in kept:
            stack = list(succ[s.id])
            visited: set[str] = set()
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                if n in kept_ids:
                    new_edges.add((s.id, n))
                else:
                    stack.extend(succ[n])
        pos = {s.id: i for i, s in enumerate(self._stages)}
        edges = sorted(new_edges, key=lambda e: (pos[e[0]], pos[e[1]]))
        loops = [(a, b) for a, b in self._loops if a in kept_ids and b in kept_ids]
        result = Graph(kept, edges, loops, self._subsets)
        if not kept:
            raise GraphError(f"subset {subset_name!r} removes every stage")
        incoming = {b for _, b in edges}
        outgoing = {a for a, _ in edges}
        if all(s.id in incoming for s in kept):
            raise GraphError(f"subset {subset_name!r} removes every start stage")
        if all(s.id in outgoing for s in kept):
            raise GraphError(f"subset {subset_name!r} removes every end stage")
        result.validate()
        return result


def _from_spec(spec: GraphSpec) -> Graph:
    return Graph(spec.stages, spec.edges, spec.loops, spec.subsets)


def default_graph() -> Graph:
    """The shipped seven-role graph, validated."""
    data = yaml.safe_load(DEFAULT_GRAPH_PATH.read_text(encoding="utf-8"))
    spec = parse_profile({"schema_version": 1, "project": {"name": "default"},
                          "paths": {"eval": ["evals/**"]}, "graph": data}).graph
    graph = _from_spec(spec)
    graph.validate()
    return graph


def load_graph(profile: Profile) -> Graph:
    """Build and validate the graph for ``profile`` (the default graph if it declares none)."""
    spec = profile.graph
    graph = default_graph() if spec is None else _from_spec(spec)
    graph.validate()
    return graph
