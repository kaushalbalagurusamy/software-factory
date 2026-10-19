# Build-loop hygiene: disk and memory management for long autonomous runs

## Purpose
Keep a long run (many parallel agents, builds, test validators, headless browsers) from dying of a
full disk or memory pressure, without spending agent tokens on routine work. A deterministic script
(`hygiene.sh`) does the work; a small agent is used only for judgment calls (`agent-brief.md`).

## Threats (all observed on 2026-10-05/06, M1 MacBook Air, APFS)
1. Per-worktree build output: eight agent worktrees each built Rust into their own `target/` (2.5-4.8 GB); ENOSPC at 661 MB free.
2. Throwaway repo copies (2.8-4.4 GB each), old probes, regenerable `.next` caches left in scratch space.
3. Merged agent worktrees never removed. `du` overstates their cost: pnpm `node_modules` are hard links to a shared store (about 12 GB measured, about 1 GB freed).
4. Accumulating processes: `next start`, solana-test-validator (a probe once hit another worktree's validator on a shared port), headless Chrome, `playwright-mcp` instances that belong to other sessions.
5. A full disk makes even memory-file writes fail, so the check must run before the failure, not after.

## Modes (the only way anything changes)
| Mode | Effect |
|---|---|
| `scan [--agents N]` | Read-only report. Exit code: 0 ok, 1 warn, 2 act, 3 emergency. `--agents N` adds a preflight (N x `agent_headroom_gb` must leave `disk_act_gb` free). |
| `plan [--emergency] [--out F]` | Read-only. Writes a JSON plan: per item `class`, `path`, `reason`, `du_bytes`, `reclaim_bytes` (hard-link aware: only inodes whose every link is inside the item count), `needs_judgment`; plus a `skipped` list with the reason each candidate was kept. |
| `apply PLAN [--execute] [--approve IDS]` | Dry-run unless `--execute`. Requires a plan file. Re-verifies every precondition at execution time, skips `needs_judgment` items unless approved, logs to `~/.claude/hygiene/hygiene.log` (or `HYGIENE_LOG`). Plans older than 6 hours are rejected. |
| `register PID [label]` | Records PID, start time and full command line in the run registry. |

## Policy tiers
- Auto (no judgment): whole merged agent worktree (clean, HEAD an ancestor of a protected branch or every commit patch-equivalent per `git cherry`, no unknown ignored files, unlocked, no process with cwd inside, not touched in `worktree_min_age_min`); scratch children older than `scratch_max_age_days`.
- Merged worktree that holds ignored files outside the allowlist (for example `.env`): the worktree stays; only its `target/`, `node_modules/` and cache dirs go.
- Needs judgment: caches in the main checkout (normal mode); scratch git repos whose HEAD is not in protected history; registered processes under warn-level memory pressure.
- Emergency (`plan --emergency`): additionally clears regenerable `target/`, `node_modules/` and caches in dirty or unique-commit worktrees (never the worktree, never locked ones), main-checkout caches, and kills registered processes without approval. The shared build dir and scratch dirs younger than the age limit (but over 1 hour) are offered only as judgment items.

## Protected (never deleted, enforced in both plan and apply)
Locked worktrees (never `-f -f`); dirty worktrees; worktrees with unique commits; the main checkout and its `.git`; all branches (the script never runs a branch command); denylisted names (`.env*`, `*.pem`, `*.key`, `keys`, `keypair*.json`, `evidence`, `memory`, `.ssh`, `secrets*`) and `~/.config/solana`, `~/.ssh`, `~/.claude/projects`; profile `protected` globs; any path not in an allowlisted class; symlinks and non-canonical paths. A scratch dir containing a denylisted name is refused whole. Processes: only PIDs in the registry whose start time and full command line still equal the registered values; never init or the script's own ancestors; other sessions' processes (`playwright-mcp` and similar) are reported, never killed.

## Where it plugs into the loop
| Point | Action |
|---|---|
| Before stages 6-8 fan out more than 2 parallel agents (and before any stage 7 run that starts servers) | `scan --agents N`; exit 2 or higher means run a sweep first or reduce N. Agents get `CARGO_TARGET_DIR` pointing at the main checkout's target. |
| After every stage 11 commit that merges or cherry-picks worktree work | `plan`, then `apply --execute` for auto items. |
| After each stage 8 review round | Same sweep (reviewers and mutation runs leave copies). |
| Stage 12 | One-line `scan` result ("disk 43 GB free, memory normal"). |
| Idle after completion (run finished, stage 12 done, nothing project-critical running; never mid-run) | Commit what matters, stop registered processes and this session's background work, `plan` + `apply --execute` for auto items, clear this session's regenerable scratch, keep the shared build dir, one-line report. Proposed `plan --idle`: include live registered processes as auto items and treat this session's own scratch as eligible regardless of age, limited to regenerable directories (venvs, `node_modules`, `target`, caches, throwaway repo copies). Not implemented; needs tests in `test-hygiene.sh` first. |
| Emergency: ENOSPC, "No space left", free below `disk_emergency_*`, or memory critical | `plan --emergency`, then `apply --execute` at once; afterwards re-run `scan` and record what was removed. |
| Stage 7 test runners | Register every server or validator the run starts with `register`, and stop it when the test run ends. |
Check added to "Checks that catch the common failures": was disk and memory checked before fan-out, do worktree agents share one build dir, and is every started process registered?

## Thresholds (profile-overridable)
Disk free, whichever condition is worse: warn below 20 GB or 15%; act below 10 GB or 8%; emergency below 3 GB or 3%. Read from `df`/statvfs Avail on the repo volume (purgeable space and local snapshots are not counted or touched). Memory: `sysctl kern.memorystatus_vm_pressure_level` (1 normal, 2 warn, 4 critical) combined with the `memory_pressure` free percentage (warn below 25%, critical below 10%); swap use from `vm.swapusage` is reported. No sudo means no `purge`; memory relief comes only from stopping registered processes.

## Known limits
APFS clones (`cp -c`, copy-on-write) share extents without hard links and cannot be detected, so `reclaim_bytes` may overstate; the apply log records free space before and after. Per-item hard-link accounting ignores links shared between two items in the same plan (it under-estimates). Worktree liveness relies on the lock, working-directory and age checks; an agent that has no lock, cwd or recent git activity is indistinguishable from an idle one.
