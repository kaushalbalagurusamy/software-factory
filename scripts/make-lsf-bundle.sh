#!/bin/sh
# Build a zip that installs lsf (and the two skills it leans on) on a Mac or Linux machine with only python3 and git.
#   scripts/make-lsf-bundle.sh [OUT_DIR]      (default OUT_DIR: ~/.cache/sf-bundles)
# The zip holds lsf, eli12-docs and mermaid-nesting-dolls plus install-bundle.sh and README-INSTALL.txt.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$HOME/.cache/sf-bundles}
sha=$(git -C "$repo" rev-parse --short HEAD)
name=lsf-bundle-$sha
stage=$out/$name
rm -rf "$stage"
mkdir -p "$stage/skills"
for s in lsf eli12-docs mermaid-nesting-dolls; do
  cp -R "$repo/skills/$s" "$stage/skills/$s"
done
find "$stage" -name __pycache__ -type d -prune -exec rm -rf {} +
rm -rf "$stage/skills/mermaid-nesting-dolls/tests"
cat > "$stage/install-bundle.sh" <<'SH'
#!/bin/sh
# Installs lsf, eli12-docs and mermaid-nesting-dolls into $CLAUDE_SKILLS_DIR (default ~/.claude/skills) and puts an
# `lsf` command in $LSF_BIN_DIR (default ~/.local/bin). A different existing copy is moved to <skills dir>/../skills-backups/<name>.backup-<time>.
# Running it twice changes nothing the second time.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SKILLS=${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}
mkdir -p "$SKILLS"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "python3 3.9 or newer is required" >&2; exit 1; }
git --version >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
for s in eli12-docs mermaid-nesting-dolls; do
  if [ -d "$SKILLS/$s" ] && diff -r "$HERE/skills/$s" "$SKILLS/$s" >/dev/null 2>&1; then
    echo "$s: already up to date"
  else
    if [ -e "$SKILLS/$s" ] || [ -L "$SKILLS/$s" ]; then
      mkdir -p "$SKILLS/../skills-backups"
      BK=$SKILLS/../skills-backups/$s.backup-$(date -u +%Y%m%d%H%M%S)
      mv "$SKILLS/$s" "$BK"; echo "$s: moved the existing different copy to $BK"
    fi
    cp -R "$HERE/skills/$s" "$SKILLS/$s"; echo "$s: installed"
  fi
done
sh "$HERE/skills/lsf/install.sh"
echo
echo "Done. Next: cd into a git project, run 'lsf init', then 'lsf serve --open'."
SH
cat > "$stage/README-INSTALL.txt" <<'TXT'
lsf bundle (lite software factory)
1. Unzip, then in the unzipped folder run:  sh install-bundle.sh
2. In your project (a git repository):      lsf init
3. Start the dashboard:                     lsf serve --open
   The terminal prints a URL ending in #token=... Open that exact URL to get the Approve buttons.
4. Optional automatic telemetry from Claude Code:   lsf hooks install --project .      (shows a diff; add --apply to write)
Needs only python3 (3.9 or newer) and git. Nothing is sent anywhere; the dashboard listens on 127.0.0.1 only.
If 'lsf' is not found, add ~/.local/bin to your PATH or run ~/.local/bin/lsf directly.
TXT
chmod +x "$stage/install-bundle.sh"
(cd "$out" && rm -f "$name.zip" && zip -qr "$name.zip" "$name")
rm -rf "$stage"
echo "$out/$name.zip"
