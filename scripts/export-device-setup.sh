#!/bin/sh
# Snapshot this Mac's Claude Code + terminal setup into device-setup/ (re-run, then commit).
# Secrets never leave: MCP env/header values are blanked, the API-key line is stripped from .zshrc,
# ~/.config/gh, gcloud and ~/.claude.json are not read.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd); D="$REPO/device-setup"; H="$HOME"
rm -rf "$D"; mkdir -p "$D/claude/skills" "$D/shell"
home() { sed "s#$H#__HOME__#g"; }   # installer swaps __HOME__ back to the new $HOME

# --- Claude Code
home < "$H/.claude/settings.json" > "$D/claude/settings.json"
home < "$H/.claude/CLAUDE.md" > "$D/claude/CLAUDE.md"
cp "$H/.claude/statusline.py" "$D/claude/"
mkdir -p "$D/claude/hooks" && cp "$H"/.claude/hooks/*.py "$D/claude/hooks/"
python3 - "$H/.claude.json" "$D/claude/mcp-servers.json" "$H" <<'PY'
import json, sys
src, dst, home = sys.argv[1:]
servers = json.load(open(src)).get("mcpServers", {})
for s in servers.values():
    for k in ("env", "headers"):
        if k in s: s[k] = {n: "" for n in s[k]}
open(dst, "w").write(json.dumps(servers, indent=2).replace(home, "__HOME__"))
PY
mkdir -p "$D/claude/bin"; for b in sf lsf claude-lsf lsf-vps; do home < "$H/.local/bin/$b" > "$D/claude/bin/$b"; done
# Skills: real dirs are copied; symlinks into the factory repo are listed (installer re-links them);
# ramp-* come from `ramp skills install`; langfuse-skills is a clone, synced/ is claude.ai-managed.
: > "$D/claude/skills-linked.txt"
for s in "$H"/.claude/skills/*; do
  n=$(basename "$s")
  case "$n" in ramp-*|langfuse-skills|synced) continue;; esac
  if [ -L "$s" ]; then echo "$n" >> "$D/claude/skills-linked.txt"
  else rsync -a --exclude='__pycache__' --exclude='.DS_Store' --exclude='runs' "$s" "$D/claude/skills/"; fi
done

# --- Shell + terminal
grep -v '^export ANTHROPIC_API_KEY=' "$H/.zshrc" | grep -v 'Anthropic API key for Claude Code' | home > "$D/shell/zshrc"
home < "$H/.zprofile" > "$D/shell/zprofile"
cp "$H/.gitconfig" "$D/shell/gitconfig"
cp "$H/.config/starship.toml" "$D/shell/"
mkdir -p "$D/shell/yazi" "$D/shell/zellij"
cp "$H"/.config/yazi/*.toml "$D/shell/yazi/"            # flavors/plugins come back via `ya pkg install`
rsync -a "$H/.config/zellij/" "$D/shell/zellij/"
# Terminal.app default profile as an importable .terminal file
python3 - "$D/shell/Terminal-profile.terminal" <<'PY'
import plistlib, subprocess, sys
d = plistlib.loads(subprocess.check_output(["defaults", "export", "com.apple.Terminal", "-"]))
name = d["Default Window Settings"]
p = dict(d["Window Settings"][name]); p["name"] = name; p["type"] = "Window Settings"
plistlib.dump(p, open(sys.argv[1], "wb"))
PY
brew bundle dump --file=- | grep -vE '^(vscode|go|cargo) ' > "$D/Brewfile"
echo "snapshot written to $D"
