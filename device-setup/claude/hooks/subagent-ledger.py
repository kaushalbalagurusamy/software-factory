#!/usr/bin/env python3
"""Record every subagent completion at the moment it happens.

WHY THIS IS THE HIGHEST-VALUE PIECE

Handoff must be written **before** performance degrades, not at compaction — by the
time a compaction fires, context is nearly full and the quality of anything written
then has already suffered. So state has to be captured on *events*, and a subagent
completing is the sharpest event available: it is the exact moment a result exists
and has not yet been forgotten.

It also closes a specific observed failure. A subagent's file writes land on disk
immediately, but only a prose summary returns to the parent. Nothing forces the
parent to notice a path the summary did not mention — which is how one research
brief was nearly stranded as an untracked directory. The harness writes this ledger,
not the model, so it cannot be skipped by an agent that compacts or moves on first.

TWO THINGS RECORDED, FOR TWO DIFFERENT FAILURES

  * The agent's own final message, truncated. Catches "what did that agent conclude
    again" after the answer has been summarised away.
  * **Paths that became untracked or modified around the completion.** Catches the
    written-but-unmentioned artifact, which the summary text by definition cannot.

Append-only, because these are immutable events — unlike the state file, which is
overwritten in place so current state is never buried in history.

Never fails loudly, never blocks, exits 0 regardless.
"""

import json
import os
import subprocess
import sys
import time

STATE_DIR = ".claude"
LEDGER = "subagent-ledger.jsonl"
SUMMARY_CHARS = 700


def run(args, cwd, timeout=8):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def find_root(start):
    try:
        current = os.path.abspath(start)
    except (OSError, ValueError):
        return None
    while True:
        if os.path.isdir(os.path.join(current, STATE_DIR)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    root = find_root(payload.get("cwd") or os.getcwd())
    if not root:
        return 0

    message = (payload.get("last_assistant_message") or "").strip()
    truncated = len(message) > SUMMARY_CHARS

    # Paths git can see as changed. Recorded regardless of whether the agent's own
    # summary mentioned them, which is the entire point: an artifact nobody named is
    # exactly the one that gets stranded.
    changed = []
    for line in run(["git", "status", "--porcelain"], root).splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            changed.append({"status": parts[0], "path": parts[1].rstrip("/")})

    unmentioned = [c["path"] for c in changed
                   if os.path.basename(c["path"]) not in message
                   and c["path"] not in message]

    entry = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type"),
        "session_id": payload.get("session_id"),
        "summary": message[:SUMMARY_CHARS],
        "summary_truncated": truncated,
        "summary_chars": len(message),
        "changed_paths": changed[:40],
        "paths_not_mentioned_in_summary": unmentioned[:40],
    }

    try:
        os.makedirs(os.path.join(root, STATE_DIR), exist_ok=True)
        with open(os.path.join(root, STATE_DIR, LEDGER), "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        return 0  # a failed ledger write must not disturb the run

    # SubagentStop CAN inject, so flag the stranding risk while it is still cheap to
    # act on — naming it now beats discovering an orphaned directory hours later.
    if unmentioned:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": (
                    f"A subagent ({payload.get('agent_type') or 'unknown'}) just "
                    f"finished and its completion is logged to "
                    f"{STATE_DIR}/{LEDGER}. These changed paths were NOT named in "
                    f"its summary: {', '.join(unmentioned[:8])}. Decide now whether "
                    f"each is an artifact to commit, to gitignore, or to delete, and "
                    f"record the decision in {STATE_DIR}/state.md. An artifact "
                    f"nobody named is the one that gets stranded."),
            }
        }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
