#!/bin/sh
# Install the lsf skill: copy it to $CLAUDE_SKILLS_DIR (default ~/.claude/skills) and link `lsf` into $LSF_BIN_DIR
# (default ~/.local/bin) as a tiny python3 wrapper. Safe to run twice: the second run changes nothing.
set -eu
SRC=$(cd "$(dirname "$0")" && pwd)
SKILLS=${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}
BIN=${LSF_BIN_DIR:-$HOME/.local/bin}
DEST=$SKILLS/lsf
changed=0

mkdir -p "$SKILLS" "$BIN"

if [ -d "$DEST" ] && diff -r "$SRC" "$DEST" >/dev/null 2>&1; then
  echo "skill: already up to date at $DEST"
else
  if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    STAMP=$(date -u +%Y%m%d%H%M%S)
    BK=$SKILLS/lsf.backup-$STAMP
    n=0
    while [ -e "$BK" ]; do n=$((n + 1)); BK=$SKILLS/lsf.backup-$STAMP$n; done
    mv "$DEST" "$BK"
    echo "skill: moved the existing different copy to $BK"
  fi
  mkdir -p "$DEST"
  cp -R "$SRC/." "$DEST/"
  chmod +x "$DEST/scripts/lsf.py" "$DEST/install.sh" 2>/dev/null || true
  echo "skill: installed $DEST"
  changed=1
fi

WRAP=$BIN/lsf
WANT="#!/bin/sh
exec python3 \"$DEST/scripts/lsf.py\" \"\$@\""
if [ -f "$WRAP" ] && [ "$(cat "$WRAP")" = "$WANT" ]; then
  echo "wrapper: already up to date at $WRAP"
else
  printf '%s\n' "$WANT" > "$WRAP"
  chmod +x "$WRAP"
  echo "wrapper: wrote $WRAP"
  changed=1
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "note: $BIN is not on your PATH; add it, or run $WRAP directly" ;;
esac
[ "$changed" = 0 ] && echo "nothing changed"
exit 0
