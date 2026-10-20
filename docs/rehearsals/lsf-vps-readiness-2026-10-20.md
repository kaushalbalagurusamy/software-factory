# VPS fallback readiness — 20 October 2026

Ready before the owner's 11:30 America/Chicago deadline. The remote build
runs Claude Sonnet 5.5 and tests; this Mac retains Codex and Antigravity.

## Versions and isolation

Local installed LSF and the final pinned VPS standby runtime both use
30ed8d5a0e060086ec4119bbd711572d91693fc0. The Mac launcher, Antigravity link
support and bounded-command helper are personal overlays recorded in this
branch. No existing AEA, Riverside, SF, Qrypt, qrypt-build, vultr-sf or original
LSF-rehearsal session was stopped. The original local demo branch and files
were independently checked unchanged after fetching remote work.

Final fixture agent: `lsf-vps-fallback-ready` (Sonnet, idle pending a real brief).
Final fixture dashboard: http://127.0.0.1:8891/ through SSH; VPS listens only on
loopback. This is the python-dotenv rehearsal fixture, not the yet-to-arrive
interview repository. Prepare the actual repo using the runbook.

## Evidence

- VPS coordinator reported 768 focused checks passing for the final factory release.
- The Mac snapshot gate passed 403 checks and skipped one old-ledger check because
  the archive lacks Git history. That exact compatibility check was then run
  successfully from the full working tree; its LSF backend bytes were verified
  identical to the installed snapshot.
- First delegated rehearsal: checkpoint blocked phase start (exit 3), approval
  through the tunnel, ADR recorded, 21 remote tests passing, Applied evidence.
- Final pinned runtime repeated the approval/record/test/apply path with 21
  passing tests. This time `via=dashboard` was explicitly verified in the ledger.
  Requirement, ADR and true-exit-status test log were committed as 62b67ef07daa
  in the isolated VPS fixture repo. The full SHA is available in `lsf-vps status`.
- Ten fallback-helper checks passed; fresh shallow clone transfer, deleted and
  untracked files, preserved prior reviewer notes, and non-merging fetch were
  also exercised against the real VPS.
- Five resource-runner checks passed, including descendant memory, timeout,
  preserved exit code and shared locking. Actual VPS memory failure returned
  137; actual VPS timeout returned 124. Normal guarded command returned 0.
- Seven launcher checks passed. ELI12 documentation checks passed for the two
  new helper modules. Both Max logins remained signed in.

The first rehearsal discovered an audit-label bug (dashboard approvals labelled
cli-nontty). Its original ledger was retained; the release fixed the API call,
and the final repeated exercise verified the corrected transport.

The screenshots show real VPS data rendered through the tunnel. Their clock is
inherited from the earlier completed fixture; it is not the duration of this
readiness smoke. Approvals identify Codex as the owner's delegated HITL reviewer.
No approval token appears in the captures.

[Final decision card](screenshots/lsf-vps-ready.png)

[Earlier capture exposing the audit-label bug](screenshots/lsf-vps-fallback.png)

Native IDE-window inspection was unavailable. Antigravity scheme registration,
URL encoding, OS dispatch, local checkout mapping, and its `--new-window` CLI
option were checked. Actual interview dependencies cannot be installed or tested
until its repository is supplied. Review copies are separate snapshots; refresh
at each HITL pause, and send edits back through Codex rather than assuming a
local edit has reached the VPS.

[Commands and handoff guide](../runbooks/lsf-vps-fallback.md)
