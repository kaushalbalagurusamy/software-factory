#!/usr/bin/env python3
"""Re-inject the build loop's invariants when context is fresh or has been reset.

The failure this addresses: a defined development loop decays across a long
session. The back half — tests before implementation, implementing blind to the
tests, a separate agent running them, an independent adversarial review, a drift
check against the verbatim requirements — costs time without producing visible
progress, so it is what goes missing first. Compaction makes it worse, because the
reasoning that established the loop is summarised away while the coding momentum
survives.

This fires on SessionStart (startup, resume, clear, compact) and on PreCompact, and
only for projects that have opted in by containing a build-loop profile. Projects
without one see nothing.

Design rules for this file, because a hook that misbehaves is worse than no hook:
never fail loudly, never block, never write anything, and exit 0 no matter what.
"""

import json
import os
import sys

PROFILE_NAMES = (
    ".claude/build-loop.md",
    "docs/development-workflow.md",
)

INVARIANTS = """\
This project has a build-loop profile, so the fixed development loop applies. \
Invoke the `sf` skill (build loop) before implementing, and create a todo per stage.

The loop, in order: research from primary sources (never from recall) -> experiment \
with real numbers -> decide and record an ADR -> MECE tracer-bullet spec -> author \
tests and evals FIRST -> implement BLIND to the test code -> a SEPARATE agent runs \
the tests -> independent adversarial review for reward hacking -> drift check by \
rereading the verbatim source requirements line by line, every line of prose \
counting, re-derived rather than checked against an earlier summary table.

The loop is not a variable. Schedule pressure may reorder or slice work; it may not \
drop a stage, override a decision an ADR already settled, or cut a deliverable to fit \
a date. State such a conflict rather than resolving it by lowering fidelity.

Standing checks: a zero must mean a measurement, never a failed lookup; no comment \
may claim a guarantee the code does not implement; a gate satisfiable by the cheapest \
cases measures nothing; engineering requirements (typed contracts, error schemas, test \
design rules, decision records, documented external-API limits) are day-one habits, not \
deferrable deliverables; and report what an independent review finds even when it finds \
against you.

Profile: {profile}"""


def find_profile(start: str) -> str | None:
    """Walk up from cwd looking for a profile, stopping at the filesystem root."""
    try:
        current = os.path.abspath(start)
    except (OSError, ValueError):
        return None
    while True:
        for name in PROFILE_NAMES:
            candidate = os.path.join(current, name)
            if os.path.isfile(candidate):
                return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    profile = find_profile(cwd)
    if not profile:
        return 0

    try:
        shown = os.path.relpath(profile, cwd)
    except ValueError:
        shown = profile

    event = payload.get("hook_event_name") or "SessionStart"
    # PreCompact discards additionalContext — verified. SessionStart fires with
    # source="compact" straight after and is the real injection point, so emitting
    # here would be latency with no effect.
    if event == "PreCompact":
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": INVARIANTS.format(profile=shown),
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never let a reminder break a session.
        sys.exit(0)
