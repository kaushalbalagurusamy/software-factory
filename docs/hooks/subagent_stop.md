# SubagentStop validators (`factory.hooks.subagent_stop`)

Hook id `subagent_stop` (TB-10, requirement R-16). Registered on `SubagentStop` with no matcher. It rejects a sub-agent report that lacks the shape its role owes the orchestrator. Contracts: `docs/prds/TB-10-subagent-stop-validators.md`, `docs/contracts/hook-io.md`, and clauses C-11 to C-18 of `docs/contracts/clarifications.md` (binding). It does not judge whether the content is correct. Deterministic; no network or model call (R-09); nothing project-specific is hard-coded (R-01): directories come from the profile (`paths.audit_dir`, `paths.design_dirs`). It reads only the message and files under the project root, plus read-only local `git` queries (HEAD, diff, untracked) to find new or changed files.

`decide(payload, cfg) -> Decision` returns `allow`, or `block` whose reason lists every missing element, one `- ` line each. The validator is chosen by `payload.agent_type`; `implement`, `test`, `orchestrator`, unknown types and a missing type are allowed, as is any event other than `SubagentStop`. Research and review need a string `last_assistant_message`; if it is absent or not a string the hook blocks. Malformed stdin and exceptions fail closed through `run_hook` (`hook error: ...`, block JSON, exit 0).

## Validators
- **research:** a line that is the label `Sources` (C-16): plain `Sources` / `Sources:`, a bold `**Sources**` / `**Sources:**`, or a heading `## Sources` (any heading level; trailing colon allowed), followed anywhere later in the message by at least one URL (`http(s)://`) or file path (a token such as `docs/a.md`, `./x`, `a/b/c`, or a bare name with an extension of two or more letters). Every sentence (split on `.`, `!`, `?` followed by space, and on newlines) containing the word `unverified` (case-insensitive) must also contain `[unverified]`. The message is at most 8,000 characters.
- **audit:** `<audit_dir>/BUGS-MITIGATIONS.md`. Each new table row (a line beginning `|`, excluding the header and separator lines, C-12) needs a cell equal to `critical`, `high`, `medium` or `low` (case-insensitive) and a citation `<path>:<line>`. New means not present in the HEAD version of the file; a file untracked, or in a project without git or HEAD, has all rows new (C-11). A missing file is allowed only if the message says `no findings` (case-insensitive).
- **review:** exactly one of `VERDICT: APPROVE` / `VERDICT: REJECT` (both blocks, C-17); a REJECT needs a `<path>:<line>` citation; a grade is a whole line `<id>: right_reason|wrong_reason|inconclusive` (optional list bullet); at least one grade unless the message says `no passing cases`; `wrong_reason` or `inconclusive` with APPROVE blocks (C-15) and the ids are named.
- **design:** Markdown files (`.md`) under `paths.design_dirs` that are new or changed (C-13). A file whose name contains `spec` (case-insensitive) needs the headings `Goals`, `Non-goals`, `Axioms`, `Open questions` (any level, case-insensitive, trailing colon allowed), and every list item (bullet or numbered, with its continuation lines) under `Axioms`, up to the next heading of the same or higher level, must contain `check:`. If any such design document contains `one-way door: yes` an ADR file must exist: any non-hidden file under `docs/adr` or under a `design_dirs` entry whose last segment is `adr` (C-14).

## Example (recorded run)
Profile: `schema_version: 1`, `project: {name: demo}`, `paths: {eval: ["evals/**"]}`. Payload on stdin:
```json
{"session_id": "s1", "cwd": "/work/demo", "hook_event_name": "SubagentStop", "permission_mode": "default", "agent_id": "a1", "agent_type": "research", "agent_transcript_path": "/tmp/t.jsonl", "stop_hook_active": false, "last_assistant_message": "The cache is unverified.\n\n## Sources\nnone"}
```
```
$ python -m factory.hooks subagent_stop < payload.json; echo "exit=$?"
{"decision":"block","reason":"research report rejected; missing or invalid:\n- at least one URL or file path after the Sources label\n- the marker [unverified] in the sentence: 'The cache is unverified.'"}
exit=0
```
With `The cache is unverified [unverified].` and `## Sources\nhttps://example.com/cache` the same command prints nothing and exits 0.

## Interpretations where the contracts are silent (unverified against the gate)
- The label starts its line and is matched case-sensitively; `Sources` inside an ordinary sentence (`The sources of the bug...`, `Sources are listed...`) is not a label.
- "Followed by" means anywhere after the label to the end of the message.
- Slash tokens without a dot, a leading `/`, `./`, `~/` or two or more slashes (for example `and/or`) are not file paths.
- Nested list items under `Axioms` are checked as items of their own; a parent item's `check:` does not cover a child.
- The one-way-door scan covers every new or changed Markdown file under `design_dirs`, not only `spec` files; committed, unchanged documents are not rescanned. Without git every Markdown file counts as changed.
- A present audit file that is unchanged relative to HEAD has no new rows and is allowed. Row numbers in audit reasons are 1-based file line numbers.
- The audit message may be absent (treated as empty); design ignores the message.
