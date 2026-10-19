#!/usr/bin/env bash
# Create a git worktree for a BLIND implementer: protected paths are absent from the working tree.
#
#   scripts/implementer-worktree.sh <name> [base-ref] [--protect PATH ...] [--root DIR]
#
# Creates DIR/<name> (default DIR: ../sf-worktrees next to the repo) on a new branch sf/<name> from base-ref
# (default HEAD), then uses sparse checkout so the protected paths (default: evals/) are not materialised.
# It also writes a project-local Claude settings file denying Read on those paths as a second layer.
# Known limit: a shell command can still `git show <rev>:evals/...` from the object database, so the PreToolUse
# blindness guard (TB-06) and the OS sandbox remain the backstops; this script removes the easy path only.
set -euo pipefail

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -ge 1 ] || usage
name="$1"; shift
base="HEAD"; root=""; protect=()
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then base="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --protect) protect+=("${2:?--protect needs a path}"); shift 2 ;;
    --root) root="${2:?--root needs a directory}"; shift 2 ;;
    *) usage ;;
  esac
done
[ ${#protect[@]} -gt 0 ] || protect=("evals/")
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad worktree name: $name" >&2; exit 2; }

repo="$(git rev-parse --show-toplevel)"
root="${root:-$(dirname "$repo")/sf-worktrees}"
dest="$root/$name"
[ ! -e "$dest" ] || { echo "already exists: $dest" >&2; exit 1; }
mkdir -p "$root"

for p in "${protect[@]}"; do
  case "$p" in /*|..|../*|*/../*|*/..) echo "protected path must be relative and inside the repo: $p" >&2; exit 2 ;; esac
done

created=0
cleanup() {  # a failed run must never leave a usable worktree that still has protected content
  if [ "$created" = 1 ]; then
    git -C "$repo" worktree remove --force "$dest" >/dev/null 2>&1 || true
    git -C "$repo" branch -D "sf/$name" >/dev/null 2>&1 || true
    echo "failed: removed $dest and branch sf/$name" >&2
  fi
}
trap cleanup EXIT

git -C "$repo" worktree add -q --no-checkout -b "sf/$name" "$dest" "$base"
created=1
# '!/path' (no trailing slash) excludes a file or a directory with its contents
patterns=('/*')
for p in "${protect[@]}"; do p="${p#./}"; patterns+=("!/${p%/}"); done
git -C "$dest" sparse-checkout init --no-cone
git -C "$dest" sparse-checkout set --no-cone "${patterns[@]}"
git -C "$dest" checkout -q "sf/$name"

# second layer: deny reads of protected paths for sessions started in the worktree
mkdir -p "$dest/.claude"
python3 - "$dest/.claude/settings.local.json" "${protect[@]}" <<'PY'
import json, sys
out, paths = sys.argv[1], sys.argv[2:]
deny = [f"Read(./{p.rstrip('/')}/**)" for p in paths] + [f"Read(./{p.rstrip('/')})" for p in paths]
json.dump({"permissions": {"deny": deny}}, open(out, "w"), indent=2)
PY
# keep the local settings out of commits without touching tracked ignore files
exclude="$(git -C "$dest" rev-parse --path-format=absolute --git-path info/exclude)"
mkdir -p "$(dirname "$exclude")"
grep -qxF '.claude/settings.local.json' "$exclude" 2>/dev/null \
  || echo '.claude/settings.local.json' >> "$exclude"

for p in "${protect[@]}"; do
  if [ -e "$dest/${p%/}" ]; then echo "protected path still present: $p" >&2; exit 1; fi
done
created=0
echo "implementer worktree: $dest (branch sf/$name); absent: ${protect[*]}"
