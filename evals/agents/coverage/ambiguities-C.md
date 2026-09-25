# Ambiguities found while authoring evals (author C: TB-09, TB-10, TB-11, TB-14)

Entries C-01 to C-33 are resolved by `docs/contracts/clarifications.md` (binding), C-30 to C-33 in its second round. The cases that now pin each resolution are listed below.

## Still unsettled
| ID | Slice | Point | Handling |
|---|---|---|---|
| C-34 | TB-09 / TB-14 | Whether Claude Code runs a sub-agent's frontmatter Stop hook as SubagentStop. The clarifications keep it *unverified* | No case depends on it. It goes to the TB-14 manual rehearsal |
| C-35 | TB-11 | New point, raised by C-30: moving an entry block inside the file (or into another section) while keeping its chain line and seq. `verify` orders by seq and the hash covers only the body, so is this a reorder that must be reported? | No case |

## Resolved entries
| ID | Slice | Point (short) | Resolution | Pinned by |
|---|---|---|---|---|
| C-01 | TB-09 | Transcript schema | RESOLVED: Claude Code native format | TB09-D-028 to D-035, D-052 to D-056, D-070 |
| C-02 | TB-09 | No Edit/Write, missing or unparseable transcript | RESOLVED: missing/unparseable skipped + log line; no Edit/Write passes; Edit with no later test blocks | TB09-D-052, D-053, D-054, D-029 |
| C-03 | TB-09 | Stop and the transcript | RESOLVED: `transcript_path` if present, else skipped | TB09-D-055, D-056 |
| C-04 | TB-09 | Untracked file lines | RESOLVED: all count as added | TB09-D-057 |
| C-05 | TB-09 | Substring or token matching | RESOLVED: whole tokens | TB09-D-058, D-059 |
| C-06 | TB-09 | Markers outside test files | RESOLVED: test files only (listed name forms) | TB09-D-060, D-061 to D-064 |
| C-07 | TB-09 | Git unavailable | RESOLVED: no executable, not a repository, or no HEAD | TB09-D-016, D-017, D-065, D-066 |
| C-08 | TB-09 | Counter reset, log frequency | RESOLVED: reset on a passing stop; one line per allowed stop after the cap | TB09-D-067, D-068 |
| C-09 | TB-09 | Deleted frozen file; manifest keys | RESOLVED: missing on disk or from the manifest blocks; project-relative POSIX keys | TB09-D-069, D-018, G-004 |
| C-10 | TB-09 | Full suite or containment | RESOLVED: containment, even narrowed | TB09-D-070, D-031 |
| C-11 | TB-10 | "New" rows | RESOLVED: relative to HEAD plus untracked | TB10-D-049, D-050 |
| C-12 | TB-10 | Header and separator lines | RESOLVED: excluded | TB10-D-048 |
| C-13 | TB-10 | "Changed" design files | RESOLVED: relative to HEAD plus untracked | TB10-D-051, D-052 |
| C-14 | TB-10 | ADR directory | RESOLVED: `docs/adr` or a design_dirs entry ending `adr` | TB10-D-053, D-054, D-055, D-033, D-034 |
| C-15 | TB-10 | inconclusive + APPROVE | RESOLVED: blocks | TB10-D-046 |
| C-16 | TB-10 | `unverified` case; Sources label forms | RESOLVED: case-insensitive; `Sources`, `**Sources**`, `**Sources:**`, `## Sources` | TB10-D-045, D-005, D-044, D-002, D-001 |
| C-17 | TB-10 | Both verdicts | RESOLVED: blocks | TB10-D-047 |
| C-18 | TB-10 | Reason wording | RESOLVED: names each missing element | TB10-D-011, D-021, D-028, D-030, D-052, G-008 |
| C-19 | TB-11 | Hash formula | RESOLVED: sha256(prev + "\n" + text) | TB11-D-042, D-043 |
| C-20 | TB-11 | Chain scope | RESOLVED (revised by C-30): global, append (seq) order | TB11-D-042, D-053 |
| C-21 | TB-11 | Removing the last entry | RESOLVED: head anchor line | TB11-D-044, D-045, D-046 |
| C-22 | TB-11 | How verify names the entry | RESOLVED: `section '<name>' entry <n>`, 1-based in the file | TB11-G-006, D-020, D-023, D-024 |
| C-23 | TB-11 | `now` type and format | RESOLVED: aware datetime or `Z` string; `YYYY-MM-DDTHH:MM:SSZ` | TB11-G-003, D-047 |
| C-24 | TB-11 | Audit role, missing ledger, whitespace | RESOLVED: orchestrator; do nothing; trimmed | TB11-D-048, D-049, D-050, D-034 |
| C-25 | TB-11 | Truncate or redact first | RESOLVED: redact, then truncate | TB11-D-051 |
| C-26 | TB-14 | run_events signature | RESOLVED: `run_events(root, [{"payload"}]) -> list[Outcome(kind, reasons)]` | TB14-G-002 to G-008, D-001 to D-019, D-023, D-035, D-040 to D-045 |
| C-27 | TB-14 | Shadow details | RESOLVED: `state_digest` parameter (default ""), `agrees` = choice equality, missing dir created | TB14-G-009, D-033, D-037, D-038, D-039  |
| C-28 | TB-03/13/09 | stop_gate event | RESOLVED: Stop in frontmatter, SubagentStop in settings (unverified behaviour, see C-34) | TB14-D-044, D-045 (settings SubagentStop path only); TB09-D-041 |
| C-29 | TB-14 | Small fixture profile | RESOLVED: base without `mcp_servers` | all TB14 stream cases |
| C-30 | TB-11 | File-order chain vs appends to an earlier section | RESOLVED: append order, `seq` on each chain line, verify orders by seq, gaps and repeats reported | TB11-D-052, D-053, D-054, D-055, D-056, D-058, D-042, D-022 |
| C-31 | TB-11 | Empty-ledger anchor | RESOLVED: `<!-- entries: 0; head: -->` | TB11-D-057 |
| C-32 | TB-09 | Zero-byte transcript; logging with `checks.test` unset | RESOLVED: zero-byte is unparseable (skipped, one line logged); nothing logged when `checks.test` is unset | TB09-D-071, D-072, D-052, D-053 |
| C-33 | TB-14 | Routing instance required? | RESOLVED: duck-typed, reads only the `log_record` attributes | TB14-D-046, D-029, and the shared `routing()` fixture |
