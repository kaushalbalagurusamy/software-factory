---
name: alsf
description: Fully automatic lsf. Takes a business PRD plus a repo (brownfield) or greenfield and runs the lite lsf loop to finished on a phase clock with no human stops. Decisions are made by a separate decision agent and recorded in docs/decisions/auto and the event log. Invoke explicitly with /alsf.
disable-model-invocation: true
---

# alsf: the lite factory with nobody to ask

This is `/lsf` (read `skills/lsf/SKILL.md`; same phases `0-intake` to `10-docs`, phase clock, telemetry, dashboard, hooks) run with
no human in the loop. It is to `/lsf` what `/asf` is to `/sf`: faster, shallower, fewer gates, and the same auto-decision rules.
It removes no `/lsf` phase.

## Differences from /lsf

- **Intake** is the `/asf` input contract: PRD verbatim, greenfield or brownfield, source repo and baseline for brownfield, owned
  destination. Missing items are recorded as blocked, not guessed. Write `.lsf/auto-charter.md` (PRD hash, time and spend ceiling,
  allowed remotes, pre-authorised actions) before `lsf init`.
- **Phase-end checkpoints are not opened as human stops.** `lsf phase end` opens `<phase>-review` automatically; in alsf run it with
  `--checkpoints none` at `lsf init`, and write the decision the checkpoint would have asked for to
  `docs/decisions/auto/NNN-title.md` (question, options, choice, rationale, reversibility, `auto:decision-agent`). Record it with
  `lsf event STAGE pass --role decision-agent --note "auto decision NNN"` so the Telemetry tab lists it. Never use
  `lsf hitl release` or `supersede`; they stay human acts, and an auto decision is never labelled `human:`.
- **Irreversible or outward actions** (force-push, deletes, publishing, spend, visibility changes, anything outside the charter)
  are not performed: append to `docs/auto/needs-human.md` with the exact command, mark the dependent row blocked, move on.
- The phase clock still applies. If a group is over plan, cut slice size, not stages; `lsf budget` is reported in the final output.

## Final report

Phase table with times, evals and results, auto decisions (linked), the `needs-human.md` queue, what was not verified. Same limit
as `/asf`: an audit trail and a charter, not proof the agent obeyed it.
