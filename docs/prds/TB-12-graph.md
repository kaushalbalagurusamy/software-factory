# TB-12: Stage graph as data

| | |
|---|---|
| **Delivers** | R-03 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-01 |
| **Kind** | PAR (wave 2) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/graph-and-ledger.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Represent the stages and gates a project runs as validated data, and pick a subset for small tickets.

## Required behaviour
1. `load_graph(profile)` builds a `Graph`; `validate()` enforces every rule in the contract and raises `GraphError` naming the offending stage or edge.
2. `order()` returns a deterministic topological order over `edges` (ties broken by stage id).
3. A cycle in `edges` is rejected; the same back-reference declared in `loops` is accepted.
4. `select(subset)` keeps only stages whose role is in the subset, reconnects edges across removed stages, and raises if that removes every start or end stage or if the subset name is unknown.
5. A default seven-role graph ships as data in `factory/agents/default_graph.yaml` and validates; a four-role subset `small` (orchestrator, implement, test, review) selects and validates on it.
6. Gate stages are reported by `gates()` in order.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/graph.py`, `tests/agents/test_graph.py`, `docs/hooks/graph.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Executing the graph or a runtime.
