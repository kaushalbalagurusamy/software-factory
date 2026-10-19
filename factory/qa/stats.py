"""Per-tier outcome statistics from attempts.jsonl, for tuning the policy from data."""
import json
from pathlib import Path


def slice_dirs(root) -> list:
    base = Path(root) / ".sf" / "slices"
    return sorted(d for d in base.iterdir() if (d / "attempts.jsonl").is_file()) if base.is_dir() else []


def tier_stats(dirs) -> dict:
    out = {}
    for d in dirs:
        for line in (Path(d) / "attempts.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            l = json.loads(line)
            t = out.setdefault(l.get("tier") or "?", {"attempts": 0, "successes": 0, "flakes": 0,
                                                      "environment": 0, "_dur": 0.0})
            o = l["outcome"]
            if o in ("pass", "fail"):
                t["attempts"] += 1
                t["successes"] += o == "pass"
                t["_dur"] += l.get("duration_s") or 0
            elif o == "flake":
                t["flakes"] += 1
            elif o == "environment":
                t["environment"] += 1
    for t in out.values():
        dur = t.pop("_dur")
        t["success_rate"] = t["successes"] / t["attempts"] if t["attempts"] else None
        t["mean_duration_s"] = dur / t["attempts"] if t["attempts"] else None
    return out
