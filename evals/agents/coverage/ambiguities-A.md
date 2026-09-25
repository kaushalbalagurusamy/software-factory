# Ambiguities found while authoring evals (author A: TB-01, TB-02, TB-03, TB-12, TB-13)

## Still open after `docs/contracts/clarifications.md`
- None is left open. A-11 and A-29 were settled in the third round.
- **A-22 (flagged unverified by the clarifications, not an open ambiguity):** it is assumed that a sub-agent's frontmatter `Stop` hook runs as `SubagentStop`. The cases follow the clarification, and the TB-14 manual rehearsal is to confirm or correct it.

## Resolution log
Every entry below is **RESOLVED** by `docs/contracts/clarifications.md` with the same id. Case ids are prefixed by slice (TB01-, TB02-, and so on).

| ID | Slice | Point | Resolution | Pinned by |
|---|---|---|---|---|
| A-01 | TB-01, TB-02 | Field access | Frozen dataclasses read by attribute, with `.to_dict()` | TB01-G-008, TB01-D-069, TB01-D-070; TB02-D-036; attribute-only helpers in all five files |
| A-02 | TB-01, TB-12 | graph in the TB-01 check order | Loader checks graph shape; semantics in TB-12 | TB01-D-060 to D-066, TB01-D-067, D-068; TB-12 rejection helper now requires the profile to load |
| A-03 | TB-01 | Defaults with none shown | Empty tuples, empty mappings, None for deploy, checks, graph | TB01-D-049, TB01-D-071 |
| A-04 | TB-01 | Index form in `.field` | `name[i]`, zero-based | TB01-D-009, D-011, D-012, D-013 to D-015, D-019, D-020, D-048 |
| A-05 | TB-01 | `..` | Segment only; `a..b` valid | TB01-D-010, D-011, D-050 |
| A-06 | TB-01 | one_way_door_patterns contents | Profile's own only | TB01-D-051 |
| A-07 | TB-01 | Missing project | `project` versus `project.name` | TB01-D-052, TB01-D-005 |
| A-08 | TB-01 | Wrong-typed values | Invalid; field names the offending key | TB01-D-017, D-024 to D-026, D-053 to D-057 |
| A-09 | TB-01 | schema_version `"1"`, `true` | Invalid | TB01-D-058, D-059 |
| A-10 | TB-03 | tools serialisation | Comma-separated strings; skills a list | TB03-D-027, TB03-D-036 (helper asserts a string) |
| A-11 | TB-03 | writes or write-access request | Loader rejects unknown override keys as `agents.<role>.<key>` | TB01-G-009, TB03-D-009; third round (parse_profile applies every rule, matches load_profile): TB01-D-072 to D-080, TB03-D-037. The generator defence cannot be reached by any valid Profile (see coverage/TB-03.md) |
| A-12 | TB-02 | read-tool placeholders | Only `len(core_tools) <= max_tools` | TB02-D-002 |
| A-13 | TB-02 | Roles with path_guard | All seven | TB02-D-006 |
| A-14 | TB-02 | Skill names | Exact table | TB02-D-009 to D-015 |
| A-15 | TB-02, TB-03 | Git-host and platform servers | Placeholders `$deploy`, `$git_host`; general servers named | TB02-D-017, D-034, D-035; TB03-D-033, D-034, D-035 |
| A-16 | TB-02 | Role error type | RoleError with `.role`, `.field` | TB02-G-008, D-024 to D-029 |
| A-17 | TB-02 | Role file shape | Mapping of field names | TB02-D-037 |
| A-18 | TB-02, TB-03 | spawns and Agent(...) | Exactly equal; no spawns means no Agent | TB02-D-022; TB03-D-021 |
| A-19 | TB-03 | Body headings | `## Purpose`, `## You may write`, `## You must never`, `## Skills` | TB03-G-009, TB03-D-015 |
| A-20 | TB-12 | Where GraphError arises | load_graph validates and raises | TB12-D-025 and every TB-12 rejection case |
| A-21 | TB-03 | ledger_audit event | SubagentStop, no matcher | TB03-D-028; TB13-D-022 |
| A-22 | TB-03, TB-13 | stop_gate event | Stop in frontmatter, SubagentStop in settings (unverified) | TB03-G-006; TB13-G-002, TB13-D-023 |
| A-23 | TB-03 | description | Spec description verbatim | TB03-D-030 |
| A-24 | TB-03 | Project-name match | Case-insensitive whole word | TB03-D-031, D-032, D-010 |
| A-25 | TB-12 | select raising | Only if the result has no start, end or stages | TB12-D-024, D-014 |
| A-26 | TB-12 | Gate definition | `gate: true` only | TB12-D-017 |
| A-27 | TB-12 | Tie-breaking | Kahn, smallest ready id | TB12-G-008 |
| A-28 | TB-12 | No graph in profile | Default graph | TB12-D-026 |
| A-29 | TB-12, TB-01 | Loops after select; subset names and members | Loop kept only if both ends kept; names are subset keys; members role ids checked at load | TB12-D-028, D-027, D-030; TB01-D-065; third round (Graph.stages, edges, loops): TB12-D-031, D-032, D-033 |
| A-30 | TB-12 | gates() | List of ids in order() order | TB12-D-029 (helper asserts a list of str) |
| A-31 | TB-12 | Empty stages | Rejected (GraphError or ProfileError) | TB12-D-019 |
| A-32 | TB-13 | Which hook ids | Union of role hooks, all eight | TB13-G-001, D-002, D-021 |
| A-33 | TB-13 | Settings hooks shape | Claude Code shape | helper `entries()` in TB-13 |
| A-34 | TB-03, TB-13 | Matchers | Exact strings; non-guards none | TB03-D-011, D-029; TB13-D-001, D-022 |
| A-35 | TB-13 | Mutation of `existing` | Must not mutate | TB13-G-008, TB13-D-024 |
