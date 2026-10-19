#!/usr/bin/env bash
# Append one stage event to ops/events.jsonl (append-only): {at, stage, slice, sha, verdict, note}.
# Usage: scripts/ops-stage-event.sh <stage> <slice> <verdict> [note]
set -euo pipefail
if [ "$#" -lt 3 ]; then
  echo "usage: $0 <stage> <slice> <verdict> [note]" >&2
  exit 2
fi
root="$(git rev-parse --show-toplevel)"
sha="$(git -C "$root" rev-parse HEAD 2>/dev/null || echo unknown)"
mkdir -p "$root/ops"
python3 - "$1" "$2" "$3" "${4:-}" "$sha" >>"$root/ops/events.jsonl" <<'PY'
import json, sys
from datetime import datetime, timezone
stage, slice_, verdict, note, sha = sys.argv[1:6]
print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage,
                  "slice": slice_, "sha": sha, "verdict": verdict, "note": note}, ensure_ascii=False))
PY
