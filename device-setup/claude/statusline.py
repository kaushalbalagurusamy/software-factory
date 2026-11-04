#!/usr/bin/env python3
"""Claude Code statusLine script.

Prints a compact status line AND caches the official `rate_limits` object
Claude Code passes on stdin (five-hour session window, seven-day/weekly cap)
to a small JSON file, so any session or script can read real usage
percentages without asking a human to run /usage and paste it.

Only Pro/Max subscribers get `rate_limits` in the payload, and only after
the first API response of a session -- the cache simply keeps whatever it
last saw, so an agent reading it may see a value that is a few minutes
stale, but it is server-reported ground truth, not a token-count estimate.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

CACHE_PATH = pathlib.Path.home() / ".claude" / "state" / "rate_limits.json"


def _pct(bucket: dict) -> str:
    value = bucket.get("used_percentage")
    return f"{value:.0f}%" if isinstance(value, (int, float)) else "?"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("claude")
        return

    model = (payload.get("model") or {}).get("display_name") or "claude"
    cwd = (payload.get("workspace") or {}).get("current_dir") or ""
    cwd_short = pathlib.Path(cwd).name or cwd

    rate_limits = payload.get("rate_limits") or {}
    five_hour = rate_limits.get("five_hour") or {}
    seven_day = rate_limits.get("seven_day") or {}

    if rate_limits:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(
                    {
                        "captured_at": datetime.datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                        "rate_limits": rate_limits,
                    },
                    indent=2,
                )
            )
        except OSError:
            pass  # Status line must never fail the render over a cache write.

    parts = [model]
    if cwd_short:
        parts.append(cwd_short)
    if five_hour:
        parts.append(f"5h:{_pct(five_hour)}")
    if seven_day:
        parts.append(f"wk:{_pct(seven_day)}")

    print(" | ".join(parts))


if __name__ == "__main__":
    main()
