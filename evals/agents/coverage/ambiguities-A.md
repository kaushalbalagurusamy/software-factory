# Ambiguities found while authoring evals (author A: TB-01, TB-02, TB-03, TB-12, TB-13)

Each entry gives the slice, the clause, and the readings. Unless an entry says a case accepts every reading, no case pins the ambiguous point.

| ID | Slice | Clause | Readings | Handling |
|---|---|---|---|---|
| A-01 | TB-01, TB-02 | `Profile` and `RoleSpec` field access is not specified | (a) attributes; (b) mapping keys | Cases read either way |
| A-02 | TB-01 / TB-12 | TB-01 behaviour 2 lists `graph` in the check order; TB-01 "Out of scope: Graph validation (TB-12)" | (a) the loader checks only the shape of `graph`; (b) it checks nothing under `graph` | No TB-01 order case involves `graph`; TB-12 cases accept a ProfileError on `graph.*` as the rejection |
| A-03 | TB-01 | "Defaults for omitted optional fields are exactly those shown above" for fields with no default shown (held_out, frozen_tests, baseline_update, agents, mcp_servers, graph, deploy, checks, pattern lists) | (a) empty list or mapping; (b) null | Not tested |
| A-04 | TB-01 | Behaviour 6 "the field name and the index of the entry" | (a) `one_way_door_patterns.1`; (b) `one_way_door_patterns[1]`; (c) other | Cases check the prefix and the index digit only |
| A-05 | TB-01 | "must not contain `..`" | (a) any substring, so `a..b` is rejected; (b) a `..` path segment only | Only `..` segments tested |
| A-06 | TB-01 | `one_way_door_patterns` "added to the built-in defaults" | (a) Profile holds only the profile's patterns; (b) Profile holds defaults plus profile patterns | Not tested |
| A-07 | TB-01 | Field for a missing `project.name` | (a) `project`; (b) `project.name` | Cases accept either |
| A-08 | TB-01 | Type checks on `deploy`, `checks`, `mcp_servers` are inferred from the schema shape and R-02 ("an invalid profile is rejected with an error that names the field"), not stated as a rule | (a) a wrong-shaped value is invalid; (b) only listed rules are enforced | Reading (a) taken in D-024 to D-026 and the order pairs; flag for the auditor |
| A-09 | TB-01 | `schema_version: "1"` (string) | (a) invalid; (b) accepted | Not tested |
| A-10 | TB-03 | Serialisation of the `tools` frontmatter value | (a) YAML list; (b) comma-separated string | Cases parse both |
| A-11 | TB-03 | Behaviour 4 "a request that would add write access or change `writes` raises GenerationError"; the profile override schema has only `model`, `extra_skills`, `mcp_servers` | (a) the loader accepts extra override keys and the generator raises; (b) the loader rejects them first (ProfileError) | D-009 accepts either; no case for "add write access" because no profile field can express it |
| A-12 | TB-02 | Behaviour 2 "`len(core_tools) + read-tool placeholders` never exceeds `max_tools`" | "read-tool placeholders" undefined (one per mcp entry? per expected read tool?) | Only `len(core_tools) <= max_tools` tested |
| A-13 | TB-02 | Behaviour 6 "write-restricted roles list `path_guard`" | (a) research, design, audit only (map 3.2 to 3.4); (b) also test and review (R-10 lists them); (c) also orchestrator (writes none) | Only research, design, audit pinned |
| A-14 | TB-02 | Behaviour 7 skill names | Plugin prefix form (`superpowers:x` or `x`); whether test lists `eval-gate-triage` (project-local) and `langfuse`; whether review and audit list plugin skills (`code-review`, `claude-security`) | Only unprefixed consolidated names pinned; implement skills matched by suffix |
| A-15 | TB-02 | Behaviour 8 "never mention a specific project platform as a required server" | (a) git-host servers (github, gitlab) are allowed entries, omitted when absent; (b) they are platform-specific | Only deploy platforms (railway, vercel, supabase) tested |
| A-16 | TB-02 | Behaviour 9 error type | Not named (unlike ProfileError, GenerationError, GraphError) | Cases accept any exception and check the message names role and field |
| A-17 | TB-02 | Shape of each role YAML file | Assumed a mapping whose keys are the RoleSpec field names (the contract lists the fields right after naming the files) | Used by the load_roles rejection cases; flag if the auditor reads it otherwise |
| A-18 | TB-02, TB-03 | Relationship between `spawns` and `Agent(...)` entries in `core_tools` | (a) Agent(...) lists exactly `spawns`; (b) independent | Only "Agent names are a subset of the allowed spawns, no bare Agent" tested |
| A-19 | TB-03 | Body "sections in order: role purpose, what the agent may write, what it must never do, and the skills to use" | Heading text or markers not specified | Section order not tested; skill mentions tested |
| A-20 | TB-12 | Whether `load_graph` validates or only `validate()` raises | (a) load_graph raises; (b) only validate raises | Cases accept a GraphError from either |
| A-21 | TB-03 | Event for `ledger_audit` in agent frontmatter | TB-03 behaviour 6 does not list it; TB-13 uses SubagentStop | Not pinned in TB-03 |
| A-22 | TB-03 / TB-13 | `stop_gate` event: TB-03 says Stop (agent frontmatter); TB-13 says SubagentStop (project settings) | (a) consistent, since Claude Code runs a sub-agent's frontmatter Stop hook as SubagentStop; (b) a conflict | Read as (a): each case follows its own PRD (TB03-G-006 Stop, TB13-G-002 SubagentStop); flag for the auditor |
| A-23 | TB-03 | Source of the frontmatter `description` | Role spec description, or generated text | Only presence tested |
| A-24 | TB-03 | "generated text contains a project name ... inside a role template body" | (a) substring; (b) whole word | D-010 uses a whole-token collision that satisfies both |
| A-25 | TB-12 | select "raises if the subset removes every start or end stage" | (a) every original start (or end) stage was removed, so the base fixture's `small` (drops its only start `spec`) raises; (b) the result has no start or end stage, that is, is empty | Only the all-removed case tested; base `small` not tested |
| A-26 | TB-12 | "a gate stage must have a human-facing role or be marked `gate: true`" | Which roles are human-facing, and what makes a stage a gate without the flag, are undefined | Not tested; gates() tested on `gate: true` only |
| A-27 | TB-12 | "ties broken by stage id" | (a) Kahn's algorithm, smallest ready id first; (b) level by level, ids sorted within a level | Only graphs where both give the same order |
| A-28 | TB-12 | load_graph for a profile with no `graph` | (a) default graph; (b) empty or error | Not tested; the default graph file is injected into a profile's `graph` (assumes the profile graph schema) |
| A-29 | TB-12 | select with loops between kept stages; subsets that name non-role ids | Unspecified | Not tested |
| A-30 | TB-12 | gates() return type and "in order" | Ids or stage objects; declaration or topological order | Either type accepted; only graphs where both orders agree |
| A-31 | TB-12 | Empty stage list | Read as violating "at least one end stage exists" | D-019 pins rejection (by GraphError or a ProfileError on graph) |
| A-32 | TB-13 | Behaviour 1 "registering each hook id" | (a) all eight published ids; (b) the ids the role specs use | Cases check the roles' union |
| A-33 | TB-13 | Shape of the settings `hooks` section | Taken from the Claude Code shape in roles-and-generation.md (`event -> [{matcher, hooks: [{type, command}]}]`) | Used throughout TB-13 |
| A-34 | TB-03, TB-13 | Matcher per guard | Not stated in the PRDs; derived from R-10 (writes), R-11 (Read, Grep, Glob, Bash), R-12 (Write, Edit, Bash) | Diagnostic only (TB03-D-011, TB13-D-001) |
| A-35 | TB-13 | Whether emit_settings may mutate `existing` | Unspecified | Not tested; cases pass copies |
