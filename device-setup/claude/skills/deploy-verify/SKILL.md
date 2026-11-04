---
name: deploy-verify
description: >-
  Use when shipping a change to a live environment and confirming it works: "deploy this", "ship to
  production", "redeploy the service", "did the deploy work", "post-deploy check", "verify the live
  app", "roll this back". Runs a pre-deploy gate (review verdict approved, tests green, no secrets in
  the diff), the deploy, then a verify loop against the project's named health checks with a stop
  condition (all green, or roll back), and writes a fixed Deploy Log ending in DEPLOYED or FAILED.
  Reads the project's own checklist at docs/ops/deploy-verification.md for its hazards and checks.
  Not for choosing an architecture (one-way-door) or reviewing code (implementation-review).
---

# Deploy and verify

A deploy is not done when the command exits. It is done when the named checks pass against the live target. This skill is the generic procedure; each project keeps its own hazards and checks in a checklist file that this skill reads first.

## 0. Read the project checklist

Read `docs/ops/deploy-verification.md` in the project (see the template below). If it does not exist, say so and stop before deploying: writing it is part of the work, and the person or session that owns the project decides its contents. Do not invent health checks.

The checklist names, for each deployable service: how it is deployed, the source it must be deployed from, known hazards, the health checks with expected results, and the rollback command.

## 1. Pre-deploy gate (stop on any failure)

1. The review verdict for this change is APPROVE. If it is REQUEST_CHANGES or missing, stop and report.
2. The tests the checklist names are green, on the exact commit being deployed. Run them; do not rely on a report.
3. A secrets scan of the diff is clean (names of secrets are fine; values are not). Stop if a value is found.
4. Every hazard in the checklist that applies to this service is answered in writing in the log (for example "deploying from a clean clone, not from the configured image source").
5. The rollback path is known and tested or at least written down before the deploy starts.

## 2. Deploy

Use only the deploy route the checklist names. Prefer a preview or staging step first when the platform has one. Record the deployment id or URL. If the deploy command fails, stop: do not retry blindly; read the build or deploy log first.

## 3. Verify loop

For each health check in the checklist, in order:

1. Run it against the live target (not a local copy) and record the actual output or status code.
2. Compare with the expected result in the checklist. Pass or fail, nothing in between.
3. On a failure, read the service logs, then either fix forward if the cause is understood and small, or roll back.

Stop conditions:
- **Green:** every check passes. Write DEPLOYED.
- **Red after one fix-forward attempt, or any check that shows data or access is wrong:** roll back with the checklist's command, re-run the checks against the rolled-back target, and write FAILED with the reason.
- Never leave a half-verified deploy: it is either DEPLOYED with all checks passed, or FAILED with the state of the target stated.

Report only what commands returned. If a check could not be run, mark it `not run` with the reason; it does not count as a pass.

## 4. Deploy Log (fixed output)

Append this to the ticket or memory file, or print it if none exists:

```
_ISO 8601 timestamp_

### Pre-Deploy Checks
- Review verdict: [APPROVE / REQUEST_CHANGES / missing]
- Tests: [all passing on <commit> / N failures]
- Secrets scan: [clean / found issues]
- Project hazards answered: [list, one line each]
- Rollback path: [command or link]

### Deploy
- Route: [command or tool used]
- Source: [commit, image or clone]
- Result: [success / failed] [deployment id or URL]

### Post-Deploy Checks
- <check name>: [pass / fail / not run] [observed result]
- ...

### Status
[DEPLOYED SUCCESSFULLY or DEPLOY FAILED: reason, and the current state of the live target]
```

## Project checklist template

Create this file in a project that lacks one (the project's owner reviews it):

```markdown
# Deploy verification

## Services
| Service | Deployed by | Must be deployed from | Rollback |
|---|---|---|---|

## Hazards
- (things that have broken a deploy before, and the rule that prevents each)

## Health checks
| Name | How to run | Expected |
|---|---|---|

## Secrets
Names of the variables the service needs. Never their values.
```

## Judgment calls

- A deploy that changes a one-way door (schema drop, contract change) needs the `one-way-door` skill first; this skill does not replace it.
- The person owning the live system decides whether a red check justifies waiting instead of rolling back; when unattended, roll back.
- Provenance: the log shape and the "APPROVE and green tests before deploying, verify health after" rules follow the `deploy-checklist` skill of the minimum-viable-factory reference repository, generalized away from its Vercel and Supabase specifics.
