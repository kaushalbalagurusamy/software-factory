# Proposed patch for build-loop SKILL.md and the profile template

Apply by hand; nothing here has been applied. About 33 added lines of skill text.

## 1. SKILL.md: new section after "The stages" list (before "Checks that catch the common failures")

```diff
+## Hygiene: disk and memory (runs beside the stages, not as a stage)
+
+A long run dies of a full disk or memory pressure long before it runs out of requirements. The helper
+`~/.claude/skills/sf/hygiene/hygiene.sh` does this deterministically (design: `hygiene/DESIGN.md`).
+Use the script alone by default; spawn the hygiene agent (`hygiene/agent-brief.md`) only when `plan`
+lists items flagged `needs_judgment`.
+
+- **Before** fanning out more than 2 parallel agents, and before a stage 7 run that starts servers:
+  `hygiene.sh scan --agents N`. Exit 2 or higher: sweep first or reduce N.
+- **After** each stage 11 commit that merges worktree work and after each stage 8 review round:
+  `hygiene.sh plan`, then `apply <plan> --execute` for the auto items.
+- **At stage 12**, state the scan result in one line ("disk 43 GB free, memory normal").
+- **Emergency** (ENOSPC, free below the profile's emergency threshold, memory critical):
+  `plan --emergency`, then `apply --execute` immediately; record what was removed.
+- **Register** every server, validator or browser the run starts: `hygiene.sh register PID label`.
+  Only registered PIDs whose command line still matches are ever stopped.
+- **Standing rule: worktree agents share one build directory (`CARGO_TARGET_DIR` = the main checkout's
+  `target/`) and clean their own caches** (`.next`, `dist`, `.vitest`, `.turbo`) before reporting done.
+- The script never deletes branches, locked or dirty worktrees, keys, `.env*`, evidence or memory
+  directories, or anything with unique commits. Deleting a branch still needs the user's say-so.
+- `apply` without `--execute` is a dry-run. Never pass `-f -f` to `git worktree remove`.
```

## 2. SKILL.md: new bullet at the end of "Checks that catch the common failures"

```diff
+- **Was disk and memory checked before this fan-out, and after the last merge?** The failure mode is
+  not slowness but ENOSPC mid-write, which also corrupts the memory and ledger writes that keep the
+  run resumable. Worktree agents must share one build directory; every started process is registered.
```

## 3. SKILL.md: one clause in "Load the project profile first"

```diff
-starting. A profile states: where the verbatim source requirements live, where ADRs go, where
-specs go, where tests and evals go, the test command, and which reviewer agent to dispatch.
+starting. A profile states: where the verbatim source requirements live, where ADRs go, where
+specs go, where tests and evals go, the test command, which reviewer agent to dispatch, and
+(optionally) a `## Hygiene` section for disk and memory limits.
```

## 4. Profile template: optional `## Hygiene` section (every key optional; defaults are conservative)

```markdown
## Hygiene
- protected: docs/evidence/*, ~/.config/solana/*          # extra globs, in addition to the built-in denylist
- protected_branches: main                                # default: the main checkout's branch, main, master
- scratch_dirs: /private/tmp/claude-501/<proj>/scratchpad # children older than the age below are deletable
- scratch_max_age_days: 3
- worktree_roots: .claude/worktrees                       # only worktrees under these may be removed
- worktree_min_age_min: 20                                # untouched this long before removal
- cache_names: .next, dist, .vitest, .turbo
- shared_build_dir: target                                # never auto-deleted
- disk_warn_gb: 20     - disk_act_gb: 10     - disk_emergency_gb: 3
- disk_warn_pct: 15    - disk_act_pct: 8     - disk_emergency_pct: 3
- mem_warn_free_pct: 25  - mem_crit_free_pct: 10
- agent_headroom_gb: 3                                    # per parallel agent, with a shared build dir
- ports: 3000, 8899                                       # ports this run owns (scan flags foreign listeners)
- process_patterns: next start ;; solana-test-validator   # regexes, separated by " ;; "; report-only
- run_registry: .claude/run-registry.tsv                  # written by `hygiene.sh register`
```
