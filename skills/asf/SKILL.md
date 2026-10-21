---
name: asf
description: Fully automatic sf. Takes a business PRD plus an existing repo (brownfield) or nothing (greenfield) and runs the whole /sf build loop to finished with no human stops. Decisions a person would have made are made by a separate decision agent and recorded. Invoke explicitly with /asf.
disable-model-invocation: true
---

# asf: the build loop with nobody to ask

This is `/sf` (read `skills/sf/SKILL.md` and follow its stages, gates, ledger and end condition unchanged) run with no human in the
loop. It adds an input contract, an auto-decision procedure and an irreversible-action queue. It removes no `/sf` stage or gate.

## Input contract

1. A business PRD (verbatim, saved as the source of truth) and **greenfield or brownfield**. Brownfield also needs the repo URL or
   checkout and a baseline commit; either mode needs the owned destination (owner/name/visibility) if a remote is wanted.
   If any of these is missing, do not guess: record it as `blocked` in the ledger with what it waits on and do the rest.
2. Write `.sf/auto-charter.md` first: the PRD hash, the budget ceiling (time, tokens, spend), the allowed remotes, and the
   actions pre-authorised. Nothing outside the charter is done.

## Replacing a human stop

- **Never open a human stop that nobody can release.** Where `/sf` would ask the owner, spawn a **decision agent** that is not
  the implementer, give it the options, the brief and the ADRs, and have it write `docs/decisions/auto/NNN-title.md`: question,
  options, chosen option, rationale, what it would change if wrong, reversibility, and who decided (`auto:decision-agent`).
  Never record an auto decision as `human:`; the ledger and the dashboard must show the difference.
- A decision an accepted ADR already settles is not remade. A decision that contradicts the PRD is a ledger `blocked` row.
- A genuine one-way door (`one-way-door`) still gets the Socratic debate and an ADR, with the debate run between two agents.
  The ADR says `Decided by: auto`.

## Irreversible and outward actions

Force-push, deleting branches or data, publishing packages, opening or merging PRs, spending money, changing visibility of a
remote, and anything outside the charter are **not performed**. Append each to `docs/auto/needs-human.md` with the exact command
and why, mark the dependent ledger row `blocked`, and continue with the next independent line. The final report lists the queue.

## The run

Same stages, same gates, same end condition as `/sf` (every requirement line satisfied or blocked with what it waits on).
Independent review, the separate QA runner, mutation or equivalent adversarial testing, drift check and doc-sync are mandatory
and are not shortened for want of a person. A reviewer finding against the work is reported, not argued away.

## Final report

Ledger with every row's status, tests run and results, the list of auto decisions (each linked), the `needs-human.md` queue, and
what was not verified. Limit: this is a procedure with an audit trail. No software check proves that an agent obeyed the charter;
the OS sandbox and permission layer are the backstop.
