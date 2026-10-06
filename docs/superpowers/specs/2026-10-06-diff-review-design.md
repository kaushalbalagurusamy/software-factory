# diff-review: repo-aware, diff-anchored review at build-loop stage 8

_Status: draft for review · Date: 2026-10-06 · Path: architectural · Decision mode for this design: Human gate (approach and re-entry rule chosen in conversation)_

## 1. Purpose

Add a reviewer to the build loop that behaves like an automated pull-request reviewer: it reads the slice's diff, comments on specific lines, knows each repository's own rules, and covers implementation mechanics, performance, scalability, and security. Its findings also serve as the loop's check for reward hacking and emergent issues. When findings are serious, a human decides whether to send the loop back to design, where the slice is treated as brownfield and the issue is designed out through a remediation tracer-bullet PRD and a new MECE eval surface.

What the owner said, kept separate from my assumptions:

| Said | Assumed (correct me) |
|---|---|
| Bugbot-level functionality and repo-specific review in the loop's code review, with inline comments as diff reviews | Runs once per slice at stage 8 of the `build-loop` skill, beside `implementation-review` |
| Inline comments land local first, GitHub PR optional | No PR is opened unless asked (standing rule) |
| Separate skill, not an extension of `implementation-review` | Diff-visible reward-hacking checks move into it (section 9) |
| Findings check for reward hacking and emergent issues, and can return the loop to audit/design as a brownfield run | The reviewer proposes severity and route; it never decides re-entry |
| A human decides whether findings are severe enough to re-enter | Re-entry produces a remediation PRD plus a new eval surface authored first |

## 2. Non-goals

- Autofix. The reviewer is read-only; the builder fixes. (Bugbot's Autofix spawns an agent to commit fixes; that conflicts with the loop's rule that the reviewer is on the grading side.)
- Cross-repository analysis. One repo per review, as Bugbot does.
- Replacing `implementation-review`'s trace work (observability, per-case trace evidence, doctored-input probe, verdicts).
- Opening or merging pull requests.

## 3. What Bugbot does (read from primary sources, 2026-10-06; not run)

Used as a reference design, not copied.

- Rules: `.cursor/BUGBOT.md` at the repo root and in each directory above a changed file; admin rules with optional globs; one rule capped at 30,000 characters, all rules combined at 100,000.
- Learned rules: reactions, developer replies, and human reviewers' comments become candidate rules; a candidate is promoted as signal accumulates, and an active rule with consistent negative signal is disabled.
- Config in `.cursor/config/bugbot.yaml`: `review.effort` (low, default, high, smart), `review.incremental`, trigger frequency, autofix mode.
- Output: inline comments with severity and a suggested fix; a CI check concluding `success`, `neutral`, or `failure` that can gate merge.
- Reported metric: a "resolution rate" near 78–80%, meaning bugs addressed by merge.
- Gaps named by an independent assessment: single repo, no deep security analysis, no performance-impact analysis, and the published metric is not precision or recall.
- Cursor's posts do not describe the review architecture. The two-stage design in section 5 is this project's own.

Sources: cursor.com/docs/bugbot; cursor.com/blog/bugbot-learning; cursor.com/blog/bugbot-out-of-beta; cursor.com/changelog/04-08-26; augmentcode.com/guides/cursor-bugbot-code-review-capabilities-limits.

## 4. Files

| Path | Role |
|---|---|
| `~/.claude/skills/diff-review/SKILL.md` | The skill (installed, master copy) |
| `.claude/review-rules.md` (per repo) | Root repo rules |
| `<dir>/REVIEW.md` (per repo, optional) | Rules scoped to files changed under `<dir>`; the reviewer reads the root file and every `REVIEW.md` from each changed file's directory upward |
| `.claude/review-config.yaml` (per repo, optional) | `effort: low\|default\|high`, `incremental: true\|false`, `noise: strict\|include_unverified` |
| `reviews/<slice>/review.json` | Machine-readable findings (section 6) |
| `reviews/<slice>/review.md` | Rendered diff hunks with each finding as an inline comment |
| `reviews/<slice>/dispositions.json` | The disposition of each finding |
| `.claude/rule-candidates.md` (per repo) | Candidate rules proposed from dismissals, pending approval |
| `.claude/review-knowledge.md` (per repo) | Approved repo knowledge: architecture, style idioms, intended oddities, hazards (section 9b) |
| `.claude/knowledge-candidates.md` (per repo) | Proposed knowledge entries awaiting human approval |

The build-loop profile (`.claude/build-loop.md`) gains one line naming the rules file and the reviews directory.

Rule format, one block per rule: `id`, `lens` (`mechanics|security|performance|scalability|integrity|repo`), optional `glob`, `severity`, a one-line statement, and one violating and one compliant example. A rule without an example is rejected at load time, because an example is what lets the verifier and the evals test it.

## 5. How a review runs

1. **Scope.** The diff of the slice. With `incremental: true`, only changes since the last review of this slice.
2. **Reviewer** (one read-only agent, Opus by default, tools restricted to read and search). For each changed file it reads the surrounding code and the callers it can find. Unity cannot return callers today (verified 2026-10-05: the default resolver returns `@api.default`), so caller search uses grep or LSP, and the review notes when it could not find them. Lenses in order: mechanics, security, performance, scalability, integrity (reward hacking), repo rules. Output: candidate findings.
3. **Verifier** (a separate agent per batch of candidates). It receives the repository and the candidates' claims and locations, not the reviewer's reasoning. It confirms from the code, or from a deterministic check where one exists (a type check, a test, a query plan, a grep that reproduces the pattern). Each candidate becomes `confirmed`, `rejected`, or `unverified`. Rejected candidates are kept in `review.json` under `rejected` with the reason, so false-positive rates can be measured.
4. **Fan-out by lens** only when the diff is too large for one reviewer pass. The threshold is not set; it is decided from measurement (section 10). Parallel work stays limited to independent lenses, and each file scope has one writer, per the manifesto.
5. **Verdict.** `clean`, `advisory`, or `blocking`, where `blocking` means at least one confirmed finding proposed as severe. The reviewer proposes; the human decides (section 7).

## 6. Findings schema

`review.json` contains `slice`, `diff_base`, `diff_head`, `rules_hash`, a `verdict`, and a list of findings. Each finding has:

| Field | Meaning |
|---|---|
| `id` | Stable within the slice |
| `file`, `line`, `side` | Anchor in the diff (`new` or `old` side) |
| `lens` | mechanics, security, performance, scalability, integrity, repo |
| `kind` | defect, test-gap, integrity, design, evidence, drift, emergent |
| `severity` | proposed: `critical`, `high`, `medium`, `low` |
| `mechanism` | One sentence naming the mechanism, never the intent |
| `evidence` | What the reviewer and verifier saw: code excerpts, check output |
| `rule_id` | Present when a repo rule produced it |
| `status` | confirmed, unverified (rejected ones sit under `rejected`) |
| `route_proposed` | fix, test-gap, design, research, drift, backlog |
| `requirement_refs` | Ledger rows or ADR ids it touches, when known |

## 7. Severity, routing, and the human gate

The reviewer proposes `severity` and `route_proposed`. The human sets the disposition. Dispositions:

| Disposition | Meaning | Where the loop goes |
|---|---|---|
| `fix-in-slice` | Small, local | Stage 6, then 7 and 8 on the delta |
| `add-case` | A test gap; the finding becomes an eval case first | Stage 5, then 6 |
| `re-enter` | Severe enough to design out | Section 8 |
| `accept` | Risk accepted, with a reason | Recorded; no change |
| `backlog` | Real but not for this slice | Ranked into the ledger or backlog (stage 12 rule); no context switch |
| `dismiss` | Not a real finding | Recorded with a reason; feeds rule candidates (section 9) |

Rules for the gate:

- Nothing re-enters design automatically. `re-enter` requires a human disposition on a finding or a cluster of findings.
- Integrity findings (reward hacking, a pass for the wrong reason) are always shown to the human whatever their severity, and the affected case is marked voided until reviewed.
- Each gate is logged as a `gate` row in the affected ADR's Decision Trail (or in `docs/adr/AUTONOMY-LOG.md` when no ADR exists and the project has opted in), with the human's words verbatim and what was shown, including known gaps such as `unverified` findings.
- Away mode: the gate is raised as a notification, and the loop waits. It does not choose a disposition on the human's behalf.

## 8. Re-entry as a brownfield pass

When the human chooses `re-enter` for a finding or cluster:

1. **Cluster.** Group the selected findings by shared cause. Each cluster gets one remediation slice, so the PRD is MECE over the cluster, not one PRD per comment.
2. **Map.** `brownfield-explorer` maps the blast radius from the findings' anchors. That map is the scope. Nothing outside it is re-derived.
3. **Reopen.** The ADR a finding invalidates gets a `reopen` row citing the finding. The original requirement ledger is carried over unchanged; re-entry reopens decisions, never requirements.
4. **Current contracts.** `axiomatic-spec` Mode B extracts S_pre from the built code and diffs it against the revised target (S_post).
5. **Remediation tracer-bullet PRD.** `prd-writer` writes a dev-facing PRD for the cluster with work units, each carrying file scope (`owns`, `new`, `reads`, `entry_points`), checked by `check_scope.py`.
6. **New MECE eval surface, authored first.** `eval-designer` writes the cases before any fix, in three groups that together cover the cluster without overlap:
   - a failing reproduction per finding (it must fail on the current code);
   - cases for the failure modes the design change is meant to prevent, including neighbors of the finding that the review did not flag;
   - boundary cases for what must keep working, so the fix cannot pass by breaking something else.
   Golden-set cases stay at rung 3 or below. The rung and coverage rules in `eval-designer` apply unchanged.
7. **Run the loop again** over that scope: decide (stage 3), spec (4), tests first (5, done in step 6), implement blind to test code (6), a separate agent runs tests (7), and this review again (8).
8. **Round cap.** A project-level cap (default 3 [proposed], the same default as the factory research loop). Past the cap, the findings go to the human with the rounds' evidence, and the loop does not run again on its own.

## 9. Overlap with `implementation-review` and the learning loop

Changes to `implementation-review`:

- Move out to `diff-review`: step 1 (diff audit for weakened tests and eval-directory edits) and the string-literal checks in the diff; the code-review delegation in step 5.
- Keep: observability review, trace evidence per passing golden case, the doctored-input probe, drift cross-check, and verdicts.
- Add: read `reviews/<slice>/review.json`; a confirmed integrity finding on a case forces that case's verdict to `wrong_reason` until a human dispositions it.

Learning loop, human-gated where Bugbot's is automatic:

- Each `dismiss` with a reason, and each human reviewer comment on a diff, can add a candidate to `.claude/rule-candidates.md`.
- A candidate becomes a rule only when the human approves it. A rule that accrues dismissals is flagged for review, not silently disabled.

## 9b. Repo knowledge learned from feedback

Rules say what to flag. Knowledge says how this repository works and how code is written in it, so the reviewer reads a diff the way a long-time maintainer would. Both are fed by the same human feedback, and they are kept apart because they are used differently: a rule is enforced and needs an example, while a knowledge entry is context the reviewer weighs.

- **File:** `.claude/review-knowledge.md` per repo, one entry per fact, grouped by area (architecture and module boundaries, naming and style idioms, error and logging conventions, concurrency and data-access patterns, known hazards, things that look wrong but are intended).
- **Entry fields:** `id`, `area` or `glob`, the statement, `evidence` (a file path and symbol, a commit, or the feedback quoted verbatim), `learned` (date), `source` (disposition id or human comment), and `last_verified` (date).
- **What feeds it:**
  - A `dismiss` with a reason such as "this is intended because..." becomes a "looks wrong but intended" entry.
  - An `accept` or `fix-in-slice` whose comment states a convention becomes a style or architecture entry.
  - A human reviewer's comment on a diff, or an edit the human makes to a builder's fix, can propose an entry, with the diff as evidence.
  - A finding the human adds that the reviewer missed becomes a candidate hazard entry, and is also queued as an eval case (section 10).
- **Gate:** entries are proposed into `.claude/knowledge-candidates.md` and become active only on human approval, logged like rule approvals. Nothing the reviewer wrote about itself is trusted as repo knowledge without that approval.
- **Use:** the reviewer loads entries whose `area` or `glob` matches the changed files, within a size budget. A knowledge entry never suppresses a finding on its own. It lowers confidence or adds context, and the verifier still has to confirm from the code.
- **Staleness:** before relying on an entry, the reviewer checks its evidence still exists in the current code. If the file or symbol is gone, the entry is treated as a hint and flagged for the human to retire or update. `last_verified` is updated only by that check.
- **Hygiene:** no secrets, credentials, or personal data in entries; quotes are redacted the same way as in the Decision Trail.
- **Bootstrap:** on a repo with no knowledge file, the first reviews seed candidates from `CLAUDE.md`, existing ADRs, and a `brownfield-explorer` map when one exists, all marked as unapproved candidates.

## 10. Evaluation of diff-review itself

Authored before the skill body, using `eval-designer`.

- **Seeded-bug diffs** per lens: each plants one known defect, and the case passes when the review finds it at the right file and line.
- **Rule cases** per sample rule: a violating diff must be flagged with the rule id, and a compliant diff must not.
- **Clean diffs** must produce zero confirmed findings. This measures false positives directly.
- **Integrity cases:** a diff that special-cases a fixture id, and one that widens an assertion range; both must be flagged as integrity.
- **Verifier cases:** a plausible but false candidate must be rejected.
- **Knowledge cases:** (a) a convention taught through one feedback item is applied to a later diff that violates it; (b) an "intended oddity" entry stops the same non-bug from being flagged again; (c) an entry whose evidence no longer exists is treated as a hint and flagged, not trusted; (d) an entry that conflicts with the code must not suppress a confirmed defect.
- **Feedback-miss cases:** each finding a human adds that the reviewer missed is added to the coverage set as a seeded case, so the same miss is measurable next time.
- **Metrics:** precision and recall per lens, measured on these sets. The resolution rate Bugbot publishes is not used, because it cannot separate a fixed bug from a dismissed comment.
- The golden set holds only checks at rung 3 or below (anchor correctness, rule id present, zero findings on clean diffs). Judgment-quality checks go in the coverage set.
- Also measured: cost per review and wall time, so the fan-out threshold and the default `effort` are set from numbers.

## 11. Changes outside the new skill

| Change | Where |
|---|---|
| Stage 8 text: dispatch both `diff-review` and `implementation-review`; route findings per section 7 | `build-loop/SKILL.md` |
| Profile line for the rules file and reviews directory | `build-loop` profile section and each repo's profile |
| Overlap move (section 9) | `implementation-review/SKILL.md` |
| Ledger row and promotion entry | `PROMOTIONS.md` |

## 12. Open questions

1. Fan-out threshold and default `effort`: unset; to be decided from the cost and wall-time measurements in section 10.
2. How the `post` step maps `review.json` to GitHub inline review comments (line mapping for `old` side, multi-line comments). Deferred until local mode works; it is optional.
3. Whether the Decision Trail or a separate log is the better home for gates on repos with no ADRs. Tied to the open `AUTONOMY-LOG` opt-in decision.
4. A review-rule size cap like Bugbot's. No cap is set; decide if rule files grow past what one pass can hold.
5. Round cap default of 3 is carried over from the factory loop and is a proposal for this loop.

## 13. Decision mode annotations

| Decision | Mode |
|---|---|
| Separate `diff-review` skill (approach B) | Human gate (conversation) |
| Local first, PR optional | Human gate (conversation) |
| Human decides re-entry; remediation PRD and new eval surface | Human direction (conversation) |
| Feedback also builds repo knowledge and style understanding (section 9b), human-approved | Human direction (conversation) |
| Reward-hacking diff checks move to `diff-review` | AI autonomous, pending spec review |
| Rule format, config keys, schema fields, round cap default | AI autonomous, pending spec review |
