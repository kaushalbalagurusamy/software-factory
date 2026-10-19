# Stage graph (`factory.agents.graph`)

Stages and gates as validated data (R-03). Contract: `docs/contracts/graph-and-ledger.md` (Graph part); binding clarifications A-20, A-25 to A-31. Pure: no network, no model call, no project names in code.

## API
- `load_graph(profile) -> Graph`: builds from `profile.graph`, or the shipped `factory/agents/default_graph.yaml` when the profile has none (A-28); validates before returning.
- `Graph.stages / edges / loops` (read-only tuples), `Graph.subsets` (read-only mapping).
- `Graph.validate()`: raises `GraphError` naming the stage or edge. Checks, in order: no stages, duplicate id, unknown role, unknown edge/loop endpoint, cycle in `edges`, unreachable stage, no end stage.
- `Graph.order()`: Kahn's algorithm over `edges`, always taking the smallest ready stage id; `loops` are ignored.
- `Graph.gates()`: ids of stages with `gate: true`, in `order()` order (A-26, A-30).
- `Graph.select(name)`: keeps stages whose role is in `subsets[name]`, reconnects edges across removed stages (a path through only removed stages becomes one edge), keeps a loop only when both ends are kept, raises `GraphError` for an unknown subset or when no start or end stage would remain.
- `default_graph()`: the shipped seven-stage graph (`small` subset: orchestrator, implement, test, review).

## Example call
```python
from factory.agents.profile import load_profile
from factory.agents.graph import load_graph, GraphError

graph = load_graph(load_profile(".factory/profile.yaml"))
print(graph.order())      # ['orchestrate', 'research', 'design', 'audit', 'implement', 'test', 'review']
print(graph.gates())      # ['audit', 'review']
small = graph.select("small")
print(small.order())      # ['orchestrate', 'implement', 'test', 'review']
```

## Decisions where the contract is silent (unverified against the gate)
- The default graph's stage ids, edges, loops and gates are chosen here (one stage per role, linear chain, loops `test->implement` and `review->implement`, gates `audit` and `review`).
- `select` on a profile graph that declares no `subsets` raises for any name (the default graph's subsets are not merged in).
- Duplicate edges are not an error.
