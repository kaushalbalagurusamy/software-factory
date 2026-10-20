# Owner-supplied Codex analysis: ops dashboard as the HITL interface (2026-10-20)

Supplied by the owner as the ideal behaviour. Its references to the current implementation are stale (owner's words);
the last column of the table and the intended path are the target. Condensed faithfully; the table's last column and
all quoted requirements are kept.

**The development tools and native Claude integration exist. The single dashboard artifact, with a working
human-decision loop, does not yet exist as an integrated system.**

Per-step target (last column): 1 Overview (stage, agents, tested commit, blockers, freshness; artifact created or
recovered at startup). 2 Business/PRD (source requirements, assumptions, coverage). 3 Minesweep (findings, severity,
evidence, dispositions, original vs reframed) and Decisions; a universal pause after minesweep must be requested/configured.
4 Business/PRD one-page value and UX journeys, proposed scope, exclusions, changes from the brief; stop for owner review.
5 Research (questions, alternatives, findings, uncertainties, sources, resulting decisions; full findings, not titles).
6 Experiments (hypothesis, method, results, limitations, winner/inconclusive, linked PRD/ADR). 7 ADRs hold rationale;
Decisions/HITL holds unresolved choices and the answer; a bridge between them. 8 PRD/Slices (ready queue, UX stories,
acceptance, implemented vs verified). 9 Architecture (nesting dolls, source refs, affected components, uncertainty,
before/after; self-contained renderer). 10 Quality/Contracts (invariants, boundaries, golden gates, coverage); freezing
criteria is not proof of owner approval, so a baseline approval needs an explicit checkpoint. 11 Development (active
task, ownership, changes, checklist, evidence). 12 Quality/Bugs (failures, attempts, feedback, regressions, verified
commit); retry exhaustion goes to the reviewer first, not every failure to HITL. 13 Reviews (finding -> affected
requirement -> amendment -> remediation -> verification). 14 Update all affected tabs in the same artifact.

Backward paths stay visible in the dashboard:

    Minesweep finding -> research/experiment -> revised finding -> revised PRD
    Research uncertainty -> experiment -> decision/ADR
    Exploration reveals wider impact -> slice/contract revision
    Invalid contract -> contract author or PRD revision
    QA failure -> implementer -> QA
    Repeated failure -> regression proposal -> eval author -> QA
    Review finding -> prioritized PRD amendment -> implementer/QA -> review
    Drift finding -> the earlier stage responsible for the missing obligation
    New requirements -> delta minesweep -> ledger -> affected downstream stages

**The central HITL gap is the return path from the dashboard answer into the actual gates.** Intended path:

    SF discovers a decision
    -> creates a scoped stop and stable decision ID
    -> updates the existing artifact's Decisions / HITL tab
    -> owner answers on that artifact
    -> SF reads the answer and checks which proposal/version it approves
    -> records it in the requirements/PRD/ADR
    -> releases only the corresponding stop through an authorized mechanism
    -> resumes the affected work
    -> updates the same decision card to Applied, with evidence

Requirements: one artifact URL per project, recovered across sessions; pending decisions prominent throughout, with one
Decisions/HITL tab holding full context and history; states Asked -> Answered -> Recorded -> Applied (an answer must not
appear implemented before the repo reflects it); pending decisions separate from the historical Git snapshot selector;
the artifact and repo dashboard use the same underlying records; reports updated at stage boundaries with source commit
and timestamp; detailed findings and evidence preserved behind summaries (no hardcoded-path or index-only collectors).

Not yet demonstrated: the complete intake -> build -> review -> singular-artifact -> human-answer -> resumed-work loop.
