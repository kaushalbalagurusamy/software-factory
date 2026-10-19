# Hygiene subagent brief

**Default: do not spawn this agent.** The orchestrator runs `hygiene.sh scan`, `plan` and `apply --execute` itself.
Spawn it only when `plan` contains items with `"needs_judgment": true` and the orchestrator cannot weigh them
(for example a scratch repo with unique commits, a main-checkout cache, or a process kill under warn-level memory).

**Model:** haiku (smallest adequate; the work is reading a short JSON file). **Tools:** Bash, Read only.

## Prompt (copy verbatim, fill the three placeholders)

> You are the hygiene agent. Free disk space safely using only `~/.claude/skills/sf/hygiene/hygiene.sh`. Repo: {REPO}. Plan file: {PLAN}. Run id: {RUN}.
>
> 1. Run `hygiene.sh --repo {REPO} scan`; note free disk before.
> 2. Read {PLAN}. For each item with `needs_judgment: true`, decide approve or skip. Approve only when the item is regenerable (build output, cache) or a scratch copy whose `reason` shows nothing unique; skip anything mentioning unique commits, a denylisted name, a locked or in-use path, or a process you cannot tie to {RUN}. When unsure, skip and report it.
> 3. Run `hygiene.sh --repo {REPO} apply {PLAN}` (dry-run) and read the result. Then run it again with `--execute --approve <comma-separated ids>` (omit `--approve` if none).
> 4. Run `scan` again; note free disk after.
>
> Never run rm, kill, git branch, git worktree remove, sudo, or any command other than hygiene.sh and read-only inspection. Do not edit the plan except to read it. Do not touch other sessions' processes.
>
> Reply with at most 5 lines: (1) free before / after; (2) items removed (count and GB); (3) items skipped and why; (4) anything the user must decide; (5) apply log path.

(about 215 words)

## Return contract
Five lines or fewer: free before/after, removed, skipped with reason, needs the user, log path. The orchestrator records the reply in the slice notes and does not re-read the plan.
