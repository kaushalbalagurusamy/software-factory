#!/usr/bin/env bash
# Append one stage event to ops/events.jsonl (append-only), through factory.ops.events.emit.
# Usage: scripts/ops-stage-event.sh <stage> <slice> <verdict> [note]
# Always exits 0 once the arguments are valid: a failed write prints "event not recorded: <reason>" on stderr.
set -euo pipefail
if [ "$#" -lt 3 ]; then
  echo "usage: $0 <stage> <slice> <verdict> [note]" >&2
  exit 2
fi
root="$(git rev-parse --show-toplevel)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import sys
from factory.ops.events import emit
root, stage, slice_, verdict, note = sys.argv[1:6]
emit(root, stage, slice_, verdict, note, source="script")
' "$root" "$1" "$2" "$3" "${4:-}"
