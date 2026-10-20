#!/usr/bin/env bash
# Locate an existing handoff-style document in the current git repo, if one exists,
# so a new one can update/supersede it in place rather than fork a second copy.
# Usage: find-handoff-doc.sh [repo-root]
set -euo pipefail

root="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$root"

# Common filename patterns, most-specific first. Case-insensitive.
patterns=(
  "*next-session-handoff*"
  "*session-handoff*"
  "*HANDOFF*"
  "*handoff*"
  "*next-session*"
)

found=""
for pat in "${patterns[@]}"; do
  matches=$(git ls-files | grep -iE "$(echo "$pat" | sed 's/\*/.*/g')" || true)
  if [ -n "$matches" ]; then
    found="$matches"
    break
  fi
done

if [ -n "$found" ]; then
  echo "$found"
  exit 0
fi

# Fall back: a README or docs-index file that itself points at a handoff doc.
grep -rliE "handoff|hand-off|pass.?the.?baton" --include="README*" --include="*.md" -- \
  "$root/docs" "$root" 2>/dev/null | grep -viE "node_modules|vendor|\.git/" | head -5 || true

exit 0
