#!/bin/bash
if [ "$(uname -s)" = Linux ]; then
  echo "[ok] Active: Vultr VPS away mode is indefinite; cloud host does not sleep."
  echo "[info] Managed sessions persist in tmux and are restored by claude-project-sessions.service."
  echo "[info] To retire a managed session, disable its roster entry before stopping it; see ~/.claude/vultr/SESSIONS.md."
  exit 0
fi
# Pre-flight checks, then keep the Mac awake for the life of this Claude Code session.
# Usage: start.sh [duration]   e.g. start.sh 4h
set -u
. "$(dirname "$0")/common.sh"

secs=""
if [ -n "${1:-}" ]; then
  secs=$(parse_duration "$1") || {
    echo "[fail] Unrecognized duration '$1'. Use a form like 90m, 4h, or 3600."
    exit 2
  }
fi

claude_pid=$(find_claude_pid) || {
  echo "[fail] Could not find the Claude Code process above this shell, so caffeinate cannot be tied to the session."
  exit 1
}

echo "== Pre-flight"
ensure_battery_maintain
check_power
check_sleep_disabled
check_network
check_docker
check_git

echo "== Keep awake"
mkdir -p "$STATE_DIR"
state="$STATE_DIR/$claude_pid"
if [ -f "$state" ]; then
  read -r old_pid _ _ < "$state"
  if caffeinate_alive "$old_pid"; then
    kill "$old_pid"
    echo "[info] Replaced this session's previous away-mode caffeinate (pid $old_pid)."
  fi
  rm -f "$state"
fi

# -i idle sleep, -m disk idle sleep, -s system sleep on AC. The display may still sleep.
if [ -n "$secs" ]; then
  nohup caffeinate -ims -w "$claude_pid" -t "$secs" >/dev/null 2>&1 &
else
  nohup caffeinate -ims -w "$claude_pid" >/dev/null 2>&1 &
fi
caff_pid=$!

# nohup takes a moment to exec caffeinate, so poll for up to 2s before giving up.
tries=0
until caffeinate_alive "$caff_pid"; do
  tries=$((tries + 1))
  if [ $tries -ge 20 ]; then
    kill "$caff_pid" 2>/dev/null
    echo "[fail] caffeinate did not start."
    exit 1
  fi
  perl -e 'select(undef, undef, undef, 0.1)'
done

now=$(date +%s)
until_ts=0
[ -n "$secs" ] && until_ts=$((now + secs))
echo "$caff_pid $now $until_ts" > "$state"

if [ "$until_ts" -gt 0 ]; then
  echo "[ok] Mac stays awake until $(clock "$until_ts") or until this Claude Code session (pid $claude_pid) exits, whichever comes first. caffeinate pid $caff_pid."
else
  echo "[ok] Mac stays awake until this Claude Code session (pid $claude_pid) exits. caffeinate pid $caff_pid."
fi
