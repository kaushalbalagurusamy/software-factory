# Parallel integration

> Reference for the orchestration skill (formerly the sf-parallel-integration skill), carried over unchanged apart from names.

Runs multiple Sonnet implementers **concurrently** against one shared git
checkout when their slices are file-disjoint and their inputs are already
committed. Reconciles with the sequential-by-default rule in `SKILL.md`: that
rule ("never run multi-bullet parallel implementations") protects slices that
share files or dependencies. This is the documented exception — file-disjoint
PAR slices with committed inputs run in parallel.

## 1. Build the DAG, not the ledger order

The ledger's linear order (TB-01 → TB-02 → TB-03 → …) understates real
parallelism — it's a checklist, not a dependency graph.

- For every ledger item, read its actual inputs from the PRD **and** the
  research's critical path, not just the item above it in the list.
- Mark each item **BLOCKING** (produces a contract, schema, or wiring another
  item needs) or **PAR** (needs only already-committed inputs).
- Start every PAR item as soon as its inputs are committed. A pure-function
  slice (SVG chart, guideline retrieval, a data transform) that only depends
  on an already-merged contracts tracer bullet is PAR — don't leave it idle
  behind an unrelated chain.
- Target as many concurrent agents as there are independent, file-disjoint
  slices — usually 3–4. One or two concurrent agents when four are possible
  is under-parallelizing, not caution.
- **Late aggregation rule:** work that aggregates across features (e.g. a
  50-case golden eval set) is scheduled after **every** feature whose cases
  it exercises, not after the first one lands. Check each case family's
  producer before scheduling the aggregator.

## 2. Pre-dispatch checklist (run before spawning any agent)

- [ ] Grading-side acceptance cases for every slice about to be dispatched
      already exist (authored against the published contracts by an eval
      agent the implementers never see; red or blocked is fine). A case
      needs its feature to *pass*, not to be *written* — if a plan
      schedules eval authoring after the features, reorder it first.
      Implementer-written tests are unit coverage, never the gate.
- [ ] DAG drawn; each item tagged BLOCKING or PAR with its real inputs listed
- [ ] Inputs for every PAR item about to be dispatched are committed on the
      shared branch (not just written locally by another agent)
- [ ] One brief per agent, each with a **file-ownership manifest**:
  - `OWN`: explicit paths/directories this agent may create or edit (prefer
    new directories over touching shared ones)
  - `DO-NOT-EDIT`: explicit paths this agent must never touch
- [ ] Orchestrator-only seams are excluded from every agent's `OWN` list:
      dependency manifests and lockfiles (`pyproject.toml`, `uv.lock`,
      `package.json`/lockfiles), migration numbering, app wiring (router
      registration, DI/dependencies, config/settings), CI YAML. The
      orchestrator edits these itself, between agents, never during a
      concurrent window.
- [ ] Any agent that needs a new package lists it (name, version, licence,
      reason) in its report instead of installing it.
- [ ] Each brief forbids every git command that touches the shared working
      tree or index, naming them: `stash`, `checkout`, `restore`, `reset`,
      `clean`, `add`, `commit`, `mv`, `rm` (renames and deletions use plain
      filesystem operations; the orchestrator stages them). Agents read "no git" as "no commits" and
      have used `git stash` to bisect a failure, which silently removes a
      peer's in-flight edits for the duration. Read-only git (`diff`, `log`,
      `show`, `status`) is fine. The orchestrator is bound by the same rule:
      to test a script against historical commits, use a separate clone in
      the scratchpad (`git clone --no-hardlinks`), never `checkout` in the
      shared tree while any agent has uncommitted work.
- [ ] Operations briefs name the allowed live channels explicitly and forbid
      every other one, including data-plane writes over `railway ssh` or a
      database shell. An operations agent told "enable via an admin account
      or stop" instead ran a direct `UPDATE` on a production config table,
      reasoning it was lower risk; the agent must stop and report, and the
      orchestrator decides.
- [ ] Each brief carries **complete scope** — no plan to message additional
      scope into a running agent (see §4).
- [ ] Each brief states the side-effect guard (see §3) as an explicit
      acceptance check.
- [ ] Repo's worktree/checkout rules confirmed (e.g. some repos forbid raw
      `git worktree add` and require a wrapper command, or forbid worktrees
      entirely — check before assuming isolation is available).

## 3. Shared-checkout hazards

All agents share one working tree unless the repo's sanctioned tooling gives
real isolation.

- A peer's half-finished edit can make another agent's test run fail. Treat
  any reported failure as unverified until you re-run it on the tree as
  currently committed — either in a clean worktree via the repo's sanctioned
  tooling, or by re-running after the peer's slice lands. Don't act on a
  failure caused by a peer's in-flight edit.
- **Side-effect guard:** any agent that runs hooks, generators, or other
  runners must leave `git status --porcelain` unchanged outside its own
  `OWN` list. Make this an explicit acceptance check in the brief — a
  pre-push hook silently writing into tracked eval results is a real failure
  mode, not a hypothetical.
- Stage by explicit path only. Never `git add -A` / `git add .` in a shared
  checkout — that sweeps in a peer's in-flight files.
- Scratch-clone commands must reference the path as `${S:?}` and set `S`
  on its own line, not partway through an `&&` chain. When an earlier
  step failed, `S` stayed empty, and `git clone <repo> $S` cloned the
  whole repo into the checkout itself (an untracked 13k-file copy);
  `rm -rf $S` in the same pattern would act on the current directory.

## 4. Complete scope up front

Give each agent everything it needs in the initial brief. A mid-flight
message adding scope may be — correctly — refused by the agent as a possible
injection; agents shouldn't treat a follow-up mid-task message as trusted
scope expansion. To add scope:
- Wait for the agent to finish, then resume or spawn fresh with a normal,
  complete brief, or
- Do the small addition yourself once the file is free (not while the agent
  may still be editing it).

## 5. Per-agent integration loop (run for each agent as it finishes)

- [ ] Read the agent's report in full
- [ ] Review the diff yourself for anything blast-radius-relevant: auth
      checks, headers, exporter/credential wiring, anything that replaced a
      vendor default — don't rubber-stamp on the agent's self-report
- [ ] Verify key claims with a cheap, direct command — real exit codes, not
      `| tail` of a command whose exit code you never checked
- [ ] Confirm `git status --porcelain` is clean outside the agent's `OWN`
      list (side-effect guard from §3)
- [ ] Stage explicitly by path and commit that slice atomically — one
      agent's slice per commit, not batched with another agent's
- [ ] Push, and let CI be the integration gate, not your own judgment alone
- [ ] Watch the CI pipeline; for each failed job, triage whether it's
      expected-and-honest (e.g. a stub correctly flagged) or a real defect
      before deciding what to do next
- [ ] Run the full suite on the committed tree via a Haiku runner that
      returns only failure lines, not full logs
- [ ] After each wave of parallel slices, run a read-only supersession audit:
      start from the source requirements, find earlier mechanisms that a
      later slice replaced (old gates, duplicate contracts, stale flags,
      shims, "not yet built" comments and docs), then delete, merge or
      document each once its owning agent is idle. Out-of-order and parallel
      builds leave this debt by construction.
- [ ] Before EVERY slice commit, even when a peer's in-flight edits make the
      full suite noisy, run the repo-wide guard tests yourself (artifact /
      PHI scans, no-print and literal-error-detail checks, contract tests).
      A slice agent runs only its own tests, so these cross-cutting guards
      are the ones most likely to be skipped and first to fail in CI
- [ ] Report to the user now, briefly: what was committed, what's blocked on
      an external action. Don't batch this with the next agent's report.

## 6. Routing inside this workflow

| Task | Model |
|---|---|
| Inventories, running a test suite, digesting logs to failure lines only | Haiku |
| Bounded implementation, eval-side work, research | Sonnet |
| Adversarial boundary red-teams, unexplained persistent failures | Opus sub-agent (rare) |

Keep implementers blind to eval/golden files — they must not see the cases
that will grade them. Eval-side agents never edit app code.

## 7. Adversarial loops

After fixing a red-team finding, re-run the red-team against the fix — don't
call it closed on the first patch. Each re-run pass targets the *new* code's
escape routes, not the original finding again; a pass that only re-checks
the old bug proves nothing about what the fix introduced.

## Quick reference

| Situation | Rule |
|---|---|
| Ledger says serial, DAG says independent | Trust the DAG; dispatch in parallel |
| Aggregator (golden set, dashboard) needs cases from features A, B, C | Schedule after A, B, **and** C are committed |
| Lockfile/migration/CI YAML needs a change | Orchestrator edits it directly, between agents |
| Agent's test fails, peer agent still running | Re-verify on committed tree before treating as real |
| Need to add scope to a running agent | Wait for it to finish, then resume/spawn with full brief |
| Hook/generator ran during an agent's task | Check `git status --porcelain` stayed inside `OWN` |
