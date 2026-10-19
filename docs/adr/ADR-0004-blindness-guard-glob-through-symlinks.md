# ADR-0004: Should the blindness guard deny a recursive Glob that can reach protected files through a symlink?

* **Status:** Proposed. Needs a decision from the owner or the delegated engineering reviewer. Nothing has been changed to hide the conflict.
* **Date:** 2026-10-19
* **Related:** `docs/prds/TB-06-blindness-guard.md` item 2 and 3, `docs/contracts/clarifications.md` (A-06 series, C-36, C-38), `docs/hooks/blindness_guard.md`

## 1. Context
The acceptance case `TB06-D-035` ("B3 Glob on a source dir") expects `Glob {pattern: "**/*.py", path: <root>/src}` to be **allowed** for the implement role. Its own fixture contains `src/alias -> ../evals` (a directory symlink to the protected eval folder, used by other cases such as `TB06-D-004` and `D-026`, which expect denies when the symlinked path is named).
The TB-06 guard now expands the pattern on disk and, after automated security review, follows symlinks it meets: `**/*.py` under `src` reaches `src/alias/*.py`, which resolve into `evals/`, so it **denies**. If the Glob tool follows directory symlinks, the allow expectation would let the implement role list eval files, which is the thing the guard exists to prevent.
The contract is silent on this. PRD item 2 says paths are symlink-resolved "when the path exists"; no clause says whether a recursive pattern is judged by what it can reach. Whether Claude Code's Glob tool follows symlinks is **unverified**.

## 2. Options
* **A. Keep the stricter guard; amend the contract and the case.** Add a clarification that a Glob or Grep pattern under an allowed `path` is judged after on-disk expansion and a directory symlink reaching a protected path denies it. Change `TB06-D-035` to use a path with no symlink under it (for example `src/util`, still allow) and add a case that `**/*.py` under `src` in the symlinked fixture denies. Net effect: more protective, one existing case changes its input.
* **B. Revert to the literal reading.** The guard ignores symlinks reached by pattern expansion; `D-035` passes unchanged. Risk: a symlink inside a searched tree is a read path to eval files if the tool follows links.
* **C. Verify the tool first.** Determine in a real Claude Code session whether Glob and Grep follow directory symlinks, then choose A (if they do) or B (if they do not).

## 3. Recommendation
C then A: verify the tool's behaviour, and if it follows symlinks adopt A. Until decided, option A's behaviour is what the code does, `TB06-D-035` is **left failing** (one diagnostic case; the golden gate is green at 141 of 141), and the evals were not edited. This does not weaken any acceptance criterion; choosing B would, which is why it needs an explicit decision.
