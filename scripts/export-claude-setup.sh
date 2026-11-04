#!/bin/sh
# Bundle the parts of this Mac's Claude Code setup that git does not carry.
# Secrets are never bundled: MCP env/header values are blanked, ~/.claude.json is not copied.
# shortcut: skips ~/.claude/projects transcripts (1+ GB) and non-factory repos; add paths if you want them.
set -eu
OUT="${1:-$HOME/Desktop/claude-migration.tgz}"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
python3 - "$HOME/.claude.json" "$W/mcp-servers.json" <<'PY'
import json, sys
src, dst = sys.argv[1:]
servers = json.load(open(src)).get("mcpServers", {})
for s in servers.values():
    for k in ("env", "headers"):
        if k in s: s[k] = {n: "" for n in s[k]}
json.dump(servers, open(dst, "w"), indent=2)
PY
cd "$HOME"
cp "$W/mcp-servers.json" .claude/mcp-servers.export.json
tar -czf "$OUT" --exclude='__pycache__' --exclude='.DS_Store' \
  --exclude='.claude/skills/synced' --exclude='.claude/skills/langfuse-skills' \
  .claude/CLAUDE.md .claude/settings.json .claude/statusline.py .claude/hooks \
  .claude/skills .claude/mcp-servers.export.json \
  $(ls -d .claude/projects/*/memory 2>/dev/null) \
  .local/bin/sf .local/bin/lsf .local/bin/claude-lsf .local/bin/lsf-vps
rm .claude/mcp-servers.export.json
echo "wrote $OUT ($(du -h "$OUT" | cut -f1)); AirDrop it to the new Mac's ~/Downloads"
