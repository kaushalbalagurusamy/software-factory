# Real-repo rehearsal and dashboard gallery

Repo: official python-dotenv, baseline 0b2880591780a426b0551436f47a17e7a76d954f.
Feature: case-sensitive literal `dotenv list --prefix PREFIX`, preserving existing formats and behavior.
Model: Sonnet 5.5 on the VPS.

## Observed performance

The original phase ledger spans 13:41:43–13:44:59 UTC: **3 minutes 16 seconds**.
This is the interval between logged intake start and docs completion, not a measurement
of total setup, initial exploration, installation or supervisor work. Several phases
were marked together; their zero-second entries cannot support individual skill timing.
The original coding run disabled human checkpoints. Separate later rehearsals verified
blocking, approval, recording and applying on the final runtime.

Independent full-suite rerun: **305 passed, 1 skipped in 2.16 seconds**.
External behavioral checks: **14 failed on baseline, 14 passed after implementation**.
Independent QA identified a missing README example, which was added.
Final-runtime readiness rehearsal: **21 feature checks passed**, with a delegated
Codex approval recorded through the dashboard and reaching Applied.
No reliable peak-RAM, token-cost or full end-to-end agent latency benchmark was collected.
This small CLI feature does not establish performance on a large unfamiliar repo.

## Screenshots

Fresh captures of all eleven tabs on the final pinned VPS runtime, accessed through
http://127.0.0.1:8891/ over SSH. They contain real rehearsal artifacts, not mock data.
The displayed elapsed clock includes time since the old fixture was initialized and
later readiness exercises; **it is not the feature implementation duration**.
Some tabs show indexes linking to repo files rather than rendering the full report.
No approval token is included in these captures.

### Overview

![Overview](screenshots/lsf-final-now.png)

### Human stops

![Human stops](screenshots/lsf-final-stops.png)

### Telemetry

![Telemetry](screenshots/lsf-final-telemetry.png)

### Research

![Research](screenshots/lsf-final-research.png)

### Experiments

![Experiments](screenshots/lsf-final-experiments.png)

### ADRs

![ADRs](screenshots/lsf-final-adrs.png)

### PRD

![PRD](screenshots/lsf-final-prd.png)

### Architecture

![Architecture](screenshots/lsf-final-architecture.png)

### Docs

![Docs](screenshots/lsf-final-docs.png)

### Evals and bugs

![Evals and bugs](screenshots/lsf-final-evals.png)

### Git history

![Git history](screenshots/lsf-final-git.png)

