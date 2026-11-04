#!/usr/bin/env python3
"""Persist the mechanically-knowable part of working state before compaction.

THE PROBLEM THIS ADDRESSES

Framed as Turing-completeness, a long agent session has conditionals and iteration
working well and **dynamic memory deficient**. Compaction summarises away working
state; the agent then re-derives facts it had already established, and asynchronous
subagent results get forgotten or stranded.

THE DIVISION OF LABOUR, WHICH IS THE WHOLE DESIGN

A hook cannot know the *semantic* state — what is in flight, what a reviewer found,
what the next action is. Only the agent knows that, and only the agent can write it.
So this hook does not try. It captures the **mechanical** state that is cheap to read
and expensive to reconstruct from a summary:

  * git branch, recent commits, and what is uncommitted or untracked
  * the test count and whether the suite currently passes
  * files changed recently, so work-in-progress is visible
  * whether the semantic state file exists and how stale it is

and then tells the agent to reconcile the semantic half. The mechanical snapshot is
the part a hook can guarantee; the reminder is the part it cannot.

STALENESS IS THE MAIN FAILURE MODE

A state file that drifts from reality is worse than none, because it is trusted. So
every snapshot is timestamped, the age of the semantic file is reported explicitly,
and the mechanical facts are re-read fresh each time rather than accumulated — an
append-only log would grow unboundedly and bury the current state in history.

Never fails loudly, never blocks, exits 0 regardless.
"""

import json
import os
import subprocess
import sys
import time

STATE_DIR = ".claude"
SEMANTIC = "state.md"          # the agent maintains this
MECHANICAL = "state-snapshot.json"   # this hook maintains this


def run(args, cwd, timeout=8):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def find_root(start):
    """Nearest ancestor containing .claude/, so this works from a subdirectory."""
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


def collect(root):
    snapshot = {
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "captured_epoch": int(time.time()),
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root),
        "head": run(["git", "log", "-1", "--format=%h %s"], root),
        "recent_commits": run(
            ["git", "log", "-8", "--format=%h %s"], root).splitlines(),
        "uncommitted": run(["git", "status", "--porcelain"], root).splitlines(),
        "recently_changed": run(
            ["git", "diff", "--name-only", "HEAD~3", "--"], root).splitlines()[:25],
    }

    # Test state, if the venv and suite exist. Counting collected tests is cheap;
    # running them is not, so this records the count and defers the verdict.
    pytest = os.path.join(root, ".venv", "bin", "python")
    if os.path.exists(pytest) and os.path.isdir(os.path.join(root, "tests")):
        collected = run([pytest, "-m", "pytest", "tests/", "--collect-only", "-q"],
                        root, timeout=45)
        tail = [line for line in collected.splitlines() if "test" in line.lower()]
        snapshot["tests_collected"] = tail[-1] if tail else "unknown"

    snapshot.update(_staleness(root))
    return snapshot


def _staleness(root):
    """Decide whether the semantic state file has drifted, structurally.

    Wall-clock age is the wrong signal and the first version of this used it: it
    false-positives on an idle session and false-negatives on a fast one, and any
    trivial edit resets mtime for the whole file regardless of what changed.

    Two structural tests instead:
      * commits landed after the file was last written that do not themselves touch
        it — work has happened that the state file cannot know about
      * uncommitted or untracked paths not named anywhere in the file — artifacts
        exist with no committed-or-ignored decision recorded
    """
    semantic = os.path.join(root, STATE_DIR, SEMANTIC)
    if not os.path.exists(semantic):
        return {"semantic_state_exists": False, "semantic_state_stale": True,
                "stale_because": ["state.md does not exist"]}

    mtime = os.path.getmtime(semantic)
    reasons = []

    since = run(["git", "log", f"--since=@{int(mtime)}", "--format=%h %s",
                 "--", "."], root).splitlines()
    touching = run(["git", "log", f"--since=@{int(mtime)}", "--format=%h",
                    "--", os.path.join(STATE_DIR, SEMANTIC)], root).splitlines()
    unrecorded = [c for c in since if c.split()[0] not in touching]
    if unrecorded:
        reasons.append(f"{len(unrecorded)} commit(s) landed after state.md was "
                       f"written without updating it: "
                       + "; ".join(c[:60] for c in unrecorded[:3]))

    try:
        body = open(semantic).read()
    except OSError:
        body = ""
    unnamed = []
    for line in run(["git", "status", "--porcelain"], root).splitlines():
        path = line.split(maxsplit=1)[-1].rstrip("/")
        if path and os.path.basename(path) not in body and path not in body:
            unnamed.append(path)
    if unnamed:
        reasons.append("uncommitted or untracked path(s) named nowhere in state.md: "
                       + ", ".join(unnamed[:5]))

    return {"semantic_state_exists": True,
            "semantic_state_stale": bool(reasons),
            "stale_because": reasons,
            "semantic_state_written_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    root = find_root(payload.get("cwd") or os.getcwd())
    if not root:
        return 0

    snapshot = collect(root)
    event = payload.get("hook_event_name") or ""

    # PreCompact CANNOT inject context — additionalContext from that event is
    # discarded by the harness, verified by dry-running it. So on PreCompact this
    # hook writes the snapshot to disk and says nothing; SessionStart with
    # source="compact" fires immediately afterwards and is where the read-back
    # actually lands. Emitting context here would be pure latency.
    if event == "PreCompact":
        try:
            with open(os.path.join(root, STATE_DIR, MECHANICAL), "w") as fh:
                json.dump(snapshot, fh, indent=2)
        except OSError:
            pass
        return 0
    try:
        with open(os.path.join(root, STATE_DIR, MECHANICAL), "w") as fh:
            json.dump(snapshot, fh, indent=2)
    except OSError:
        pass  # a failed snapshot must not block compaction

    lines = [
        "WORKING STATE — mechanical snapshot written to "
        f"{STATE_DIR}/{MECHANICAL} at {snapshot['captured_utc']}.",
        f"  branch: {snapshot.get('branch') or 'unknown'} | "
        f"head: {snapshot.get('head') or 'unknown'}",
    ]
    if snapshot.get("tests_collected"):
        lines.append(f"  tests: {snapshot['tests_collected']}")
    uncommitted = snapshot.get("uncommitted") or []
    if uncommitted:
        # git porcelain status is XY plus a space, but a single-character status is
        # printed with one leading space, so a fixed slice eats the first character
        # of the path. Split on whitespace instead.
        paths = [line.split(maxsplit=1)[-1] for line in uncommitted[:6]]
        lines.append(f"  uncommitted: {len(uncommitted)} path(s) — "
                     + ", ".join(paths))

    if snapshot.get("semantic_state_stale"):
        why = "; ".join(snapshot.get("stale_because") or ["unknown"])
        lines.append(
            f"  ACTION REQUIRED: {STATE_DIR}/{SEMANTIC} has drifted — {why}. "
            f"Before continuing, "
            f"write or refresh it with the state only you know: what is IN FLIGHT "
            f"(including every subagent dispatched and not yet reported), what "
            f"independent reviewers found and whether it is fixed, the next concrete "
            f"action, and any decision made but not yet recorded in an ADR. A "
            f"mechanical snapshot cannot recover those, and re-deriving them after "
            f"compaction is how bookkeeping drifts.")
    else:
        lines.append(f"  {STATE_DIR}/{SEMANTIC} is current — read it before "
                     f"continuing, and update it as work lands.")

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": payload.get("hook_event_name") or "PreCompact",
            "additionalContext": "\n".join(lines),
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
