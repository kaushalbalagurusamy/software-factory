#!/bin/bash
if [ "$(uname -s)" = Linux ]; then
  echo "[ok] Active: Vultr VPS away mode is indefinite; cloud host does not sleep."
  echo "[info] Managed sessions persist in tmux and are restored by claude-project-sessions.service."
  echo "[info] To retire a managed session, disable its roster entry before stopping it; see ~/.claude/vultr/SESSIONS.md."
  exit 0
fi
# Report away-mode state for this session and any others on this Mac.
set -u
. "$(dirname "$0")/common.sh"

claude_pid=$(find_claude_pid) || claude_pid=""

echo "== Away mode"
found=0
for state in "$STATE_DIR"/*; do
  [ -f "$state" ] || continue
  found=1
  owner="${state##*/}"
  read -r caff_pid started until_ts < "$state"
  label="session pid $owner"
  [ "$owner" = "$claude_pid" ] && label="this session (pid $owner)"
  if caffeinate_alive "$caff_pid"; then
    detail="since $(clock "$started")"
    [ "${until_ts:-0}" -gt 0 ] && detail="$detail, until $(clock "$until_ts")"
    echo "[ok] Active for $label: caffeinate pid $caff_pid, $detail."
  else
    echo "[info] Ended for $label (session exited or timer ran out); cleaning up."
    rm -f "$state"
  fi
done
[ $found -eq 0 ] && echo "[info] Away mode is not active for any session."

echo "== Machine"
check_power
check_sleep_disabled
other=$(pmset -g assertions | grep -c 'PreventUserIdleSystemSleep named' | tr -d ' ')
echo "[info] $other process assertion(s) currently preventing idle sleep (all sources)."
