# ADR-0003: Seven agent definitions sit above skills, not a seven-stage relay

* **Status:** Accepted (the role definitions, hooks and per-role model choices are proposals and are not built yet)
* **Date:** 2026-09-24
* **Authors:** Kaushal Balagurusamy & Software Factory Core Engineering
* **Deciders:** Kaushal Balagurusamy
* **Related:** ADR-0002 (epistemic zero-trust verification); `docs/plans/2026-09-24-seven-core-agents.md` (the full design and evidence); `docs/plans/2026-09-24-skills-consolidation-proposal.md`

---

## 1. Context and Problem Statement
The factory needs a small, clear set of agent roles, each with its own model, tool allowlist and hooks, and a smaller skill set that those roles load. The backlog proposed six roles (Research, Design, Implement, Test, Review, Audit). Deploy and orchestration had no home among them. ADR-0002 rejected multi-agent review panels (a PM, Dev, QA and Reviewer relay) as a verification mechanism, so any role structure must not reopen that decision.

## 2. Decision Drivers
* Split by **context boundary**, not by pipeline phase. Phase-based splits add coordination overhead; multi-agent setups lost accuracy on sequential tasks and gained it only on parallelisable ones, with a central coordinator (sources in the design file).
* **One writer at a time** per working tree. Parallelize reads, serialize writes.
* **Verification is independent and blind**: Implement never sees held-out evals, and deterministic checks carry the verification burden.
* **Hooks enforce; prompts advise.** Each "must never" is a hook or a missing tool.
* Narrow tool lists and the smallest adequate model per role, because every subagent inherits the plugin and skill listing.

## 3. Considered Options
* **Option 1:** Six roles as in the backlog, with Operate added as a seventh.
* **Option 2:** A seven-stage relay run in order for every ticket.
* **Option 3:** Seven agent *definitions* (Orchestrator, Research, Design, Audit, Implement, Test, Review) that sit above skills and are used only where they pay; Deploy is a scripted Orchestrator step, with post-deploy checks run by Test.

## 4. Decision Outcome
**Chosen Option:** Option 3.

1. Roles are agent definitions (model, tools, hooks, skills). Skills stay the procedures a role loads; roles replace no skills.
2. A small ticket may use only Orchestrator, Implement, Test and Review. Design runs at gates; Research and Audit run when the ticket needs them. There is no fixed relay.
3. The Orchestrator writes no application code. Its routing is code (typed state and deterministic rules); a classifier such as Jev runs in shadow mode until our own data sets its thresholds.
4. Only Implement edits application code, one per working tree. Research and Audit fan out, and each writes only its own docs folder.
5. Test writes evals before Implement exists and freezes them; a hook blocks Implement from reading them.
6. Review uses a different vendor from Implement when one is available, to avoid correlated blind spots.
7. Deploy has no agent of its own. The Orchestrator runs the scripted deploy and Test runs the `deploy-verify` skill against the project checklist.

### Relationship to ADR-0002
This does not reopen ADR-0002. Verification stays deterministic (`sf verify`, `sf audit`, hooks, frozen baselines). The independent Review role is a read-only second opinion after those checks, not a committee that replaces them.

### Positive Consequences
* Skills can be consolidated without losing the ownership of each step.
* Tool and model choices per role are explicit and cheap to audit.

### Negative Consequences & Mitigations
* Hooks and role definitions do not exist yet; until built, the rules are advice. Building them belongs with the Austin plan milestones M1 or M2.
* Whether a Claude Code subagent definition can preload skills and carry its own hooks was not verified; if not, hooks go in project settings.
* A second billing surface for cross-vendor Review. Model tiers stay proposals until measured against small experiments.
