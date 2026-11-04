#!/bin/bash
if [ "$(uname -s)" = Linux ]; then
  echo "[ok] Active: Vultr VPS away mode is indefinite; cloud host does not sleep."
  echo "[info] Managed sessions persist in tmux and are restored by claude-project-sessions.service."
  echo "[info] To retire a managed session, disable its roster entry before stopping it; see ~/.claude/vultr/SESSIONS.md."
  exit 0
fi
# Stop away mode for this session, or for every session with --all.
set -u
. "$(dirname "$0")/common.sh"

all=0
[ "${1:-}" = "--all" ] && all=1
claude_pid=$(find_claude_pid) || claude_pid=""

if [ $all -eq 0 ] && [ -z "$claude_pid" ]; then
  echo "[fail] Could not find this Claude Code session. Use --all to stop away mode everywhere."
  exit 1
fi

stopped=0
for state in "$STATE_DIR"/*; do
  [ -f "$state" ] || continue
  owner="${state##*/}"
  [ $all -eq 1 ] || [ "$owner" = "$claude_pid" ] || continue
  read -r caff_pid _ _ < "$state"
  if caffeinate_alive "$caff_pid"; then
    kill "$caff_pid"
    echo "[ok] Stopped caffeinate pid $caff_pid (session pid $owner)."
    stopped=1
  fi
  rm -f "$state"
done
[ $stopped -eq 0 ] && echo "[info] No active away-mode caffeinate to stop."

if [ "$(pmset -g | awk '/SleepDisabled/ {print $2}')" = "1" ]; then
  echo "[warn] Lid-close sleep is still disabled. Undo with: ! sudo pmset -a disablesleep 0"
else
  echo "[ok] Normal sleep behavior restored."
fi
