# Shared helpers for the away-mode scripts. Compatible with macOS /bin/bash 3.2.

STATE_DIR="${TMPDIR:-/tmp}/claude-away-mode"

# Run a command with a time limit (macOS ships no `timeout`).
with_timeout() {
  local secs="$1"; shift
  perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
}

# Walk up the process tree to the Claude Code process that owns this shell.
find_claude_pid() {
  local pid=$$ comm i=0
  while [ "${pid:-0}" -gt 1 ] && [ $i -lt 20 ]; do
    comm=$(ps -o comm= -p "$pid" 2>/dev/null) || return 1
    if [ "${comm##*/}" = "claude" ] || [ "${comm##*/}" = "claude.exe" ]; then
      echo "$pid"
      return 0
    fi
    pid=$(ps -o ppid= -p "$pid" | tr -d ' ')
    i=$((i + 1))
  done
  return 1
}

# True if the pid is alive and is still a caffeinate process (guards against pid reuse).
caffeinate_alive() {
  [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null &&
    [ "$(ps -o comm= -p "$1" 2>/dev/null | sed 's#.*/##')" = "caffeinate" ]
}

# Convert 90, 90s, 45m, or 4h to seconds.
parse_duration() {
  local n="${1%[smh]}"
  local unit="${1#"$n"}"
  case "$n" in ''|*[!0-9]*) return 1 ;; esac
  [ "$n" -gt 0 ] || return 1
  case "$unit" in
    ''|s) echo "$n" ;;
    m) echo $((n * 60)) ;;
    h) echo $((n * 3600)) ;;
    *) return 1 ;;
  esac
}

clock() {
  date -r "$1" '+%H:%M'
}

find_battery_bin() {
  if command -v battery >/dev/null 2>&1; then
    command -v battery
  elif [ -x /usr/local/bin/battery ]; then
    echo "/usr/local/bin/battery"
  elif [ -x /usr/local/co.palokaj.battery/battery ]; then
    echo "/usr/local/co.palokaj.battery/battery"
  else
    return 1
  fi
}

ensure_battery_maintain() {
  local batt_bin
  batt_bin=$(find_battery_bin) || return 0
  local maintain_pct=""
  [ -f "$HOME/.battery/maintain.percentage" ] && maintain_pct=$(cat "$HOME/.battery/maintain.percentage" 2>/dev/null | tr -d '[:space:]')

  if [ -z "$maintain_pct" ] || [ "$maintain_pct" = "stop" ] || [ "$maintain_pct" = "0" ]; then
    "$batt_bin" maintain 70-80 >/dev/null 2>&1
    echo "[ok] Enabled battery sailing mode (70-80%) to prevent battery swelling while plugged in."
  elif ! pgrep -f "battery maintain_synchronous" >/dev/null 2>&1; then
    "$batt_bin" maintain "$maintain_pct" >/dev/null 2>&1
    echo "[ok] Battery sailing mode daemon restarted ($maintain_pct)."
  fi
}

check_power() {
  local batt pct remaining batt_bin maintain_pct
  batt=$(pmset -g batt)
  pct=$(printf '%s\n' "$batt" | grep -Eo '[0-9]+%' | head -1 | tr -d '%')
  remaining=$(printf '%s\n' "$batt" | grep -Eo '[0-9]+:[0-9]+ remaining' | head -1)
  batt_bin=$(find_battery_bin) || batt_bin=""

  if printf '%s\n' "$batt" | grep -q "'AC Power'"; then
    if [ -n "$batt_bin" ]; then
      maintain_pct=""
      [ -f "$HOME/.battery/maintain.percentage" ] && maintain_pct=$(cat "$HOME/.battery/maintain.percentage" 2>/dev/null | tr -d '[:space:]')
      if [ -n "$maintain_pct" ] && [ "$maintain_pct" != "stop" ] && [ "$maintain_pct" != "0" ]; then
        echo "[ok] On AC power${pct:+ (battery $pct%)}. Battery sailing mode active ($maintain_pct, SMC safe)."
      else
        echo "[warn] On AC power${pct:+ (battery $pct%)}, but battery charge limit is inactive. Run 'battery maintain 70-80' to prevent battery swelling."
      fi
    else
      echo "[ok] On AC power${pct:+ (battery $pct%)}."
    fi
  elif [ -n "$pct" ] && [ "$pct" -lt 50 ]; then
    echo "[warn] On battery at $pct%${remaining:+, $remaining}. Plug in charger before leaving (sailing mode will protect against swelling)."
  else
    echo "[info] On battery${pct:+ at $pct%}${remaining:+, $remaining}. Plug in for long sessions."
  fi
}

check_sleep_disabled() {
  if [ "$(pmset -g | awk '/SleepDisabled/ {print $2}')" = "1" ]; then
    echo "[warn] Lid-close sleep is disabled system-wide (pmset disablesleep 1). Undo later with: sudo pmset -a disablesleep 0"
  else
    echo "[info] Lid-close sleep is normal, so keep the lid open."
  fi
}

check_network() {
  local code
  code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' https://api.anthropic.com 2>/dev/null)
  if [ -n "$code" ] && [ "$code" != "000" ]; then
    echo "[ok] Network reaches api.anthropic.com."
  else
    echo "[fail] Cannot reach api.anthropic.com. Remote Control will not work until the network is back."
  fi
}

check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[info] Docker CLI not installed; skipping."
  elif with_timeout 10 docker info >/dev/null 2>&1; then
    echo "[ok] Docker is running."
  else
    echo "[warn] Docker is not running or did not respond within 10s. Start Docker Desktop if this session needs containers."
  fi
}

check_git() {
  local branch count
  if ! with_timeout 10 git -C "$PWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[info] $PWD is not a git repository; skipping."
    return
  fi
  branch=$(git -C "$PWD" branch --show-current 2>/dev/null)
  count=$(with_timeout 20 git -C "$PWD" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [ "${count:-0}" -gt 0 ]; then
    echo "[info] Git: branch ${branch:-detached}, $count uncommitted path(s)."
  else
    echo "[ok] Git: branch ${branch:-detached}, working tree clean."
  fi
}
