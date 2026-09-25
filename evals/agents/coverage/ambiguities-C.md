# Ambiguities found while authoring evals (author C: TB-09, TB-10, TB-11, TB-14)

Each entry gives the slice, the clause, and the readings. Unless the Handling column says otherwise, no case pins the ambiguous point.

| ID | Slice | Clause | Readings | Handling |
|---|---|---|---|---|
| C-01 | TB-09 | b5 "the sub-agent's transcript (`agent_transcript_path`, JSON lines) shows no Bash tool call ..." | The line schema is unpublished: (a) Claude Code's native transcript (`{"type":"assistant","message":{"content":[{"type":"tool_use","name":..,"input":..}]}}`); (b) a factory-specific schema | D-028 to D-034 use reading (a), treated as a protocol fact, diagnostic tier only; auditor may drop them if reading (a) is disputed |
| C-02 | TB-09 | b5 "after the last Edit or Write call" | For a transcript with no Edit/Write, or an empty or missing transcript: (a) vacuous, so allow; (b) no evidence, so block | Not tested |
| C-03 | TB-09 | b1 Stop for main-session implement + b5 | The Stop payload in hook-io has no `agent_transcript_path`: (a) check 5 skipped on Stop; (b) block for lack of evidence; (c) read `transcript_path` | Stop cases use a profile without `checks.test` |
| C-04 | TB-09 | b3 "the added lines" with b2 including untracked files | (a) every line of an untracked new file is added; (b) only `git diff HEAD` hunks count | Not tested (bypass risk: a new test file containing a skip marker) |
| C-05 | TB-09 | b3 marker list (`xit`, `assert 1`) | (a) substring match (`sys.exit` contains `xit`; `assert 1 == f()` contains `assert 1`); (b) token/statement match | Not tested; negative controls avoid such strings |
| C-06 | TB-09 | b3 | (a) markers count in any file; (b) only in test files | Markers placed only in test files |
| C-07 | TB-09 | b2 "if git is unavailable" | (a) no git executable only; (b) also a root that is not a repository or has no HEAD | Only (a) tested (PATH without git) |
| C-08 | TB-09 | b7 | (a) the counter resets when a stop passes; (b) never resets. Log line: (a) once at the cap; (b) on every post-cap stop | Cases check only that blocks 1-5, allows 6+, and at least one log line after the 6th |
| C-09 | TB-09 | b4 | A frozen file deleted from disk; manifest key form (relative path assumed from the profile contract "paths are relative") | Deletion not tested; keys are project-relative |
| C-10 | TB-09 / R-15 | R-15 "no evidence of a full-suite run" vs b5 "a Bash tool call containing `profile.checks.test`" | (a) `pytest -q tests/one.py` is evidence (contains); (b) not a full suite | Not tested |
| C-11 | TB-10 | b3 "every new row" | New relative to (a) git HEAD; (b) the previous run; (c) all rows | Fixtures use an untracked new file, so all readings agree |
| C-12 | TB-10 | b3 "rows are Markdown table lines beginning `|`" | (a) header and separator lines are rows (so any conventional table blocks); (b) they are excluded | Fixtures use header-less rows with a valid first row |
| C-13 | TB-10 | b5 "any Markdown file changed under `paths.design_dirs`" | Changed per (a) git; (b) all files present | Fixtures use untracked new files |
| C-14 | TB-10 | b5 "an ADR file under `docs/adr`" | (a) literal `docs/adr`; (b) the ADR directory among the profile's `design_dirs` (alt: `design/adr`) | Only the base profile (where both agree) tested |
| C-15 | TB-10 / METHODOLOGY §5 | b4 blocks only "a `wrong_reason` grade with `VERDICT: APPROVE`"; METHODOLOGY: "A `wrong_reason` or `inconclusive` verdict blocks like a failure" | `inconclusive` with APPROVE: (a) allowed by the hook; (b) blocked | Not tested |
| C-16 | TB-10 | b2 | Case of `unverified` (`Unverified`); `**Sources:**` with a colon inside the bold | Not tested |
| C-17 | TB-10 | b4 | A message containing both `VERDICT: APPROVE` and `VERDICT: REJECT` | Not tested |
| C-18 | TB-10 | b6 "lists every missing element" | Exact wording of each element | Cases check element names case-insensitively (Sources, unverified, severity, citation, verdict, grade, heading names) |
| C-19 | TB-11 | Contract: hash "covers the previous chain value ... and this entry's text" | Byte layout (separator, encoding, whether the header line is part of the text) | No case recomputes a hash; cases check format, determinism, and sensitivity to text and previous value |
| C-20 | TB-11 | "the previous chain value" | (a) previous entry in the file; (b) previous entry in the same section | Tamper cases stay within one section so both readings detect them |
| C-21 | TB-11 | b4 "a removed entry" | Removing the last entry leaves a valid prefix chain: (a) must be detected (needs an anchor); (b) only interior removals | Only an interior removal tested |
| C-22 | TB-11 | b4 "names the section and entry" | Entry identified by index, timestamp or header | Only the section name asserted |
| C-23 | TB-11 | `append(path, section, role, text, now)` | `now` as datetime or string; `Z` or `+00:00` | Cases pass an aware UTC datetime and accept either suffix |
| C-24 | TB-11 | b6 | Role on the Audit Trail header (orchestrator owns the section); ticket named in `current_ticket` without a ledger file; trailing whitespace in `current_ticket` | Not tested; fixtures create the ledger and write the id without a newline |
| C-25 | TB-11 | b6 "first 200 characters ... with secret-shaped values removed" | Truncate then redact, or redact then truncate | Secret placed well inside the first 200 characters |
| C-26 | TB-14 | b1 "`run_events(project_root, events)` ... for each event (a payload dict plus the hook ids registered for that event and tool) returns the combined outcome" | Input: (a) list of (payload, hook_ids) pairs; (b) list of dicts; (c) payloads only, with hooks looked up from the emitted settings. Output: Decision objects, kinds, or one combined value | No case calls `run_events`; the stream is driven through the published seams with the b1 rule, gated on `run_events` existing. Recommend publishing the signature, then adding direct cases |
| C-27 | TB-14 | b4 `shadow.record(result, actual_choice, ledger_dir)` with `log_record(result, state_digest)` | Source of `state_digest`; whether `result` must be a `Routing` instance; which field `agrees` compares (decision, choice or action); a missing `ledger_dir` (create or skip) | Duck-typed result with decision = choice = action; `state_digest` presence only; a missing `ledger_dir` is not tested |
| C-28 | TB-03 / TB-13 / TB-09 | TB-03 b6 "Stop for `stop_gate`"; TB-13 b1 "SubagentStop for ... `stop_gate`"; TB-09 b1 both | Which event the settings register `stop_gate` under | No end-to-end implement-stop case |
| C-29 | TB-14 | b2 "a small profile with two agents' worth of paths, no MCP servers" | Undefined "two agents' worth" | Base fixture with `mcp_servers` removed |
