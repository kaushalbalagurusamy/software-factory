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
# the factory venv has the dependencies (yaml); the system python3 may not
py="$here/.venv/bin/python"; [ -x "$py" ] || py=python3
# -I: no current directory, PYTHONPATH or user site on sys.path, so an untrusted cwd cannot shadow `factory`.
"$py" -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from factory.ops.events import emit
here, root, stage, slice_, verdict, note = sys.argv[1:7]
emit(root, stage, slice_, verdict, note, source=None)
' "$here" "$root" "$1" "$2" "$3" "${4:-}"
