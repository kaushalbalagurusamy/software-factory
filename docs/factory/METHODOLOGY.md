# Build methodology for the factory's agent layer

Rules every agent (any vendor, any tool) must follow when planning, building, testing or reviewing this work. They are written here, not only in skills or memory, because planners and reviewers from other vendors cannot load Claude skills. If a plan conflicts with a rule here, the plan is wrong.

## 1. Order of work
1. **Requirements first.** Every requirement has an ID in `docs/factory/requirements.md`, with its source.
2. **Contracts next.** Published contracts in `docs/contracts/` say what each component accepts and returns. Evals and implementers both depend on these, and on nothing else.
3. **Evals before features.** Golden and diagnostic cases are authored against the published contracts before any implementation. A case can be written before its producer exists; it then resolves to `blocked` (never `pass`). Scheduling eval authoring after the features is a defect in the plan.
4. **Independent MECE audit of the golden gate.** A separate read-only agent grades the golden set as mutually exclusive and collectively exhaustive over the requirements, and against the repository, before implementers start, and again when cases change materially. The author of an eval set must not be its only grader.
5. **Implement blind.** Implementers get a slice brief and the published contracts. They never read, list, run or edit the eval directories. Their own unit tests are unit coverage, never the acceptance gate.
6. **Verify deterministically, then review independently.** Deterministic checks (tests, baseline hashes, skip and weakened-assertion scans) run first. Then a reviewer that did not write the code (a different model family where available) checks the diff and the evidence, and grades each pass as right-reason, wrong-reason or inconclusive.

## 2. Roles of the people and agents
- **Implementers** (Sonnet-class by default, Opus for hard slices): own only the paths in their brief.
- **Eval author** (separate agent): writes cases and graders from the contracts; never edits application code.
- **Auditor** (separate agent): MECE grading, read-only.
- **Reviewer:** read-only; never edits implementation, tests or cases.
- **Orchestrator:** writes no application code; sequences, dispatches, integrates.

## 3. Parallel work
- Build the dependency graph from real inputs, not list order. Items that need only committed inputs run in parallel.
- Every agent gets a file-ownership manifest (`OWN`, `DO-NOT-EDIT`). Shared seams (dependency manifests, wiring, CI files) are edited only by the orchestrator, between agents.
- Agents never run git commands that touch the shared working tree (`stash`, `checkout`, `restore`, `reset`, `clean`, `add`, `commit`, `mv`, `rm`); the orchestrator stages by explicit path and commits one slice per commit.
- Before each slice commit, the orchestrator runs the repo-wide guard tests and the slice's own tests.

## 4. Gates and pauses
- Decide reversible, well-grounded gates from the requirements, contracts and evals, and record the reasoning in the PRD or an ADR.
- Pause and ask a person only for a genuine fork with several valid avenues that could critically drift the work, or an irreversible external action (secrets, live deployments, merges, opening pull requests, deleting or force-pushing shared history).
- A pause is a concrete question, not running commentary.

## 5. Done means
- Required checks green on the exact commit, with evidence, and no test weakened, skipped or deleted to get there.
- A `wrong_reason` or `inconclusive` verdict blocks like a failure.
- Anything unverified is marked unverified in the document that makes the claim.

## 6. Hygiene
- No secret values in any file, ever: reference variables by name. A value pasted into a chat is treated as exposed.
- Stage files by explicit path; one logical change per commit; do not amend, squash, rebase or force-push shared history.
- Project-specific facts (platform, host, hazards, eval paths) live in the project profile, never in role or skill definitions.
- Record measured or estimated cost per stage where a run produces it.
