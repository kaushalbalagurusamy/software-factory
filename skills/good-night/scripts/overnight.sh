#!/bin/bash
# Overnight-run state for one project checkout. Shared by good-night and good-morning.
#
#   overnight.sh start [note]        open a run (fails if one is already open)
#   overnight.sh status              print the open run, exit 1 if none
#   overnight.sh log <kind> <text>   append a journal line (kind: slice|commit|blocked|decision|spend|stall|note)
#   overnight.sh decide <text>       queue a decision for the owner (also journalled)
#   overnight.sh spend <usd> <text>  record measured spend in the shared daily ledger; exit 3 once the day is over cap
#   overnight.sh budget              print today's spend and what is left of the daily cap (all sessions)
#   overnight.sh end                 close the open run and print its directory
#   overnight.sh last                print the directory of the most recent closed run
#
# State lives in <repo root>/.claude/overnight/ and is never committed:
#   active            path of the open run directory (exists only while a run is open)
#   <stamp>/run.json  start/end time, branch, HEAD, note
#   <stamp>/journal.md, <stamp>/decisions.md
set -euo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
base="$root/.claude/overnight"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# Owner direction 2026-10-17: OpenRouter + Anthropic console share $200/month; under $10/day is fine.
# The ledger is shared by every session on the host so parallel nights cannot each spend the cap.
cap=${OVERNIGHT_DAILY_CAP_USD:-10}
spend_file="$HOME/.claude/vultr/state/spend/$(date -u +%Y-%m-%d).tsv"
day_total() { [ -f "$spend_file" ] && awk -F'\t' '{s+=$2} END {printf "%.2f", s}' "$spend_file" || echo 0.00; }
active_dir() { [ -f "$base/active" ] && cat "$base/active"; }
need_active() {
  dir=$(active_dir) || { echo "[fail] no overnight run is open in $root (run good-night first)"; exit 1; }
}

cmd=${1:-status}; shift || true
case "$cmd" in
  start)
    if dir=$(active_dir); then echo "[warn] run already open: $dir"; exit 0; fi
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    dir="$base/$stamp"; mkdir -p "$dir"
    branch=$(git -C "$root" branch --show-current 2>/dev/null || echo "")
    head=$(git -C "$root" rev-parse HEAD 2>/dev/null || echo "")
    python3 - "$dir/run.json" "$(now)" "$root" "$branch" "$head" "${*:-}" <<'PY'
import json, sys
path, started, root, branch, head, note = sys.argv[1:]
json.dump({"started_at": started, "ended_at": None, "root": root, "branch": branch,
           "start_head": head, "note": note}, open(path, "w"), indent=2)
PY
    printf '# Overnight journal (%s)\n\n' "$stamp" > "$dir/journal.md"
    printf '# Decisions queued for the owner (%s)\n\n' "$stamp" > "$dir/decisions.md"
    grep -qxF '.claude/overnight/' "$root/.git/info/exclude" 2>/dev/null \
      || echo '.claude/overnight/' >> "$root/.git/info/exclude" 2>/dev/null || true
    echo "$dir" > "$base/active"
    echo "[ok] overnight run open: $dir (branch ${branch:-none}, HEAD ${head:0:7})"
    ;;
  status)
    need_active
    echo "[ok] overnight run open: $dir"
    cat "$dir/run.json"; echo
    echo "journal lines: $(grep -c '^- ' "$dir/journal.md" || true), decisions queued: $(grep -c '^## ' "$dir/decisions.md" || true)"
    ;;
  log)
    need_active
    kind=${1:?kind}; shift
    echo "- $(now) [$kind] $*" >> "$dir/journal.md"
    ;;
  decide)
    need_active
    n=$(( $(grep -c '^## ' "$dir/decisions.md" || true) + 1 ))
    printf '## D%s (%s)\n\n%s\n\n' "$n" "$(now)" "$*" >> "$dir/decisions.md"
    echo "- $(now) [decision] D$n queued: $(printf '%s' "$*" | head -c 120)" >> "$dir/journal.md"
    echo "[ok] queued D$n"
    ;;
  spend)
    amount=${1:?usd}; shift
    mkdir -p "$(dirname "$spend_file")"
    printf '%s\t%s\t%s\t%s\n' "$(now)" "$amount" "$(basename "$root")" "$*" >> "$spend_file"
    if dir=$(active_dir); then echo "- $(now) [spend] \$$amount $*" >> "$dir/journal.md"; fi
    total=$(day_total)
    echo "[ok] today \$$total of \$$cap"
    awk -v t="$total" -v c="$cap" 'BEGIN {exit !(t >= c)}' && { echo "[fail] daily cap reached; no more paid calls today"; exit 3; }
    ;;
  budget)
    total=$(day_total)
    awk -v t="$total" -v c="$cap" 'BEGIN {printf "today $%.2f of $%.2f, $%.2f left\n", t, c, (c-t>0?c-t:0)}'
    ;;
  end)
    need_active
    head=$(git -C "$root" rev-parse HEAD 2>/dev/null || echo "")
    python3 - "$dir/run.json" "$(now)" "$head" <<'PY'
import json, sys
path, ended, head = sys.argv[1:]
run = json.load(open(path)); run["ended_at"] = ended; run["end_head"] = head
json.dump(run, open(path, "w"), indent=2)
PY
    rm -f "$base/active"
    echo "$dir"
    ;;
  last)
    ls -d "$base"/*/ 2>/dev/null | sort | tail -1 | sed 's:/$::' || { echo "[fail] no runs"; exit 1; }
    ;;
  *) echo "usage: overnight.sh start|status|log|decide|spend|budget|end|last"; exit 2 ;;
esac
