#!/usr/bin/env bash
# Run pytest with a memory cap, a wall-clock cap, and a machine-wide lock so only ONE heavy run happens at a time.
#   scripts/bounded-pytest.sh [pytest args...]
# Env: SF_TEST_MEM_MB (default 4096), SF_TEST_WALL_S (default 900), SF_TEST_LOCK (default /tmp/sf-factory-pytest.lock)
# Limits are recorded to .sf/resource-limits.log; a run killed by a limit exits non-zero and is never reported as a pass.
set -uo pipefail
repo="$(git rev-parse --show-toplevel)"
mem_mb="${SF_TEST_MEM_MB:-4096}"; wall="${SF_TEST_WALL_S:-900}"; lock="${SF_TEST_LOCK:-/tmp/sf-factory-pytest.lock}"
py="${SF_PYTHON:-$repo/.venv/bin/python}"; [ -x "$py" ] || py=python3
mkdir -p "$repo/.sf"
echo "$(date -u +%FT%TZ) cwd=$PWD mem_mb=$mem_mb wall_s=$wall args=$*" >> "$repo/.sf/resource-limits.log"
SF_TEST_MEM_MB="$mem_mb" flock -w 1800 "$lock" \
  prlimit --as=$((mem_mb * 1024 * 1024)) timeout --signal=KILL "$wall" "$py" -m pytest "$@"
rc=$?
case $rc in
  137) echo "bounded-pytest: killed by the ${wall}s wall-clock limit (not a pass)" >&2 ;;
  124) echo "bounded-pytest: timed out (not a pass)" >&2 ;;
esac
exit $rc
