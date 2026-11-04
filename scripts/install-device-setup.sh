#!/bin/bash
# One-command setup of Claude Code + terminal on a new Mac from device-setup/.
# Idempotent. Existing files are moved to <name>.pre-device-setup, never deleted.
# Usage: scripts/install-device-setup.sh   (run from the cloned software-factory repo)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd); S="$REPO/device-setup"; H="$HOME"
step() { printf '\n==> %s\n' "$*"; }
place() {  # place SRC DST: copy with __HOME__ substituted, backing up any different existing file
  mkdir -p "$(dirname "$2")"
  sed "s#__HOME__#$H#g" "$1" > "$2.new"
  if [ -e "$2" ] && ! cmp -s "$2" "$2.new"; then mv "$2" "$2.pre-device-setup"; fi
  mv "$2.new" "$2"
}
TODO=()

step "Homebrew + packages"
command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
brew bundle --file "$S/Brewfile" || TODO+=("some Brewfile items failed; re-run: brew bundle --file $S/Brewfile")

step "Node 24 + Claude Code"
eval "$(fnm env)"; fnm install 24 >/dev/null; fnm default 24; fnm use 24
command -v claude >/dev/null || npm i -g @anthropic-ai/claude-code

step "Shell + terminal config"
place "$S/shell/zshrc" "$H/.zshrc"; place "$S/shell/zprofile" "$H/.zprofile"
place "$S/shell/gitconfig" "$H/.gitconfig"; place "$S/shell/starship.toml" "$H/.config/starship.toml"
for f in "$S"/shell/yazi/*.toml; do place "$f" "$H/.config/yazi/$(basename "$f")"; done
rsync -a "$S/shell/zellij/" "$H/.config/zellij/"
[ -f "$H/.config/yazi/package.toml" ] && (ya pkg install >/dev/null 2>&1 || TODO+=("yazi plugins: run 'ya pkg install'"))
open -g "$S/shell/Terminal-profile.terminal" && sleep 2   # imports the profile into Terminal.app
P=$(/usr/libexec/PlistBuddy -c 'Print :name' "$S/shell/Terminal-profile.terminal" 2>/dev/null || python3 -c "import plistlib,sys;print(plistlib.load(open('$S/shell/Terminal-profile.terminal','rb'))['name'])")
defaults write com.apple.Terminal "Default Window Settings" "$P"; defaults write com.apple.Terminal "Startup Window Settings" "$P"

step "Claude Code config"
C="$H/.claude"
for f in settings.json CLAUDE.md statusline.py; do place "$S/claude/$f" "$C/$f"; done
for f in "$S"/claude/hooks/*.py; do place "$f" "$C/hooks/$(basename "$f")"; done
chmod +x "$C/statusline.py"
rsync -a "$S/claude/skills/" "$C/skills/"
while read -r n; do  # skills the factory repo owns are symlinked so repo updates reach Claude
  [ -n "$n" ] && [ -d "$REPO/skills/$n" ] && ln -sfn "$REPO/skills/$n" "$C/skills/$n" || echo "  missing in repo: $n"
done < "$S/claude/skills-linked.txt"
if command -v ramp >/dev/null; then ramp skills install --all --target "$C/skills" || TODO+=("ramp skills: run 'ramp skills install --all' after 'ramp login'"); fi

step "Plugins + marketplaces"
python3 - "$C/settings.json" > /tmp/plugin-plan.$$ <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print("marketplace anthropics/claude-plugins-official")
for m in s.get("extraKnownMarketplaces", {}).values(): print("marketplace", m["source"]["repo"])
for p, on in s.get("enabledPlugins", {}).items():
    if on: print("plugin", p)
PY
while read -r kind arg; do
  if [ "$kind" = marketplace ]; then claude plugin marketplace add "$arg" || TODO+=("marketplace $arg failed")
  else claude plugin install "$arg" || TODO+=("plugin $arg failed"); fi
done < /tmp/plugin-plan.$$; rm -f /tmp/plugin-plan.$$

step "MCP servers"
TOKEN=$(gh auth token 2>/dev/null || true)
python3 - "$S/claude/mcp-servers.json" "$H" "$TOKEN" > /tmp/mcp-plan.$$ <<'PY'
import json, os, sys
src, home, token = sys.argv[1:]
for name, s in json.loads(open(src).read().replace("__HOME__", home)).items():
    cmd = s.get("command", "")
    if cmd.startswith("/") and not os.path.exists(cmd):
        print("SKIP", name, f"(command not on this Mac: {cmd})"); continue
    j = json.dumps(s)
    if name == "github" and token: j = j.replace('"GITHUB_PERSONAL_ACCESS_TOKEN": ""', f'"GITHUB_PERSONAL_ACCESS_TOKEN": "{token}"')
    print("ADD", name, j)
PY
while read -r kind name rest; do
  if [ "$kind" = ADD ]; then claude mcp add-json --scope user "$name" "$rest" >/dev/null && echo "  added $name" || TODO+=("MCP $name failed to add")
  else TODO+=("MCP $name skipped $rest"); fi
done < /tmp/mcp-plan.$$; rm -f /tmp/mcp-plan.$$

step "Software Factory runtime"
( cd "$REPO" && uv venv .venv && uv pip install -q -r requirements.txt && uv pip install -q -e . ) || TODO+=("factory venv install failed; see requirements.txt / pyproject.toml")
mkdir -p "$H/.local/bin"; for f in sf lsf claude-lsf lsf-vps; do [ -f "$S/claude/bin/$f" ] && place "$S/claude/bin/$f" "$H/.local/bin/$f" && chmod +x "$H/.local/bin/$f"; done
"$H/.local/bin/sf" install doctor --project "$REPO" || TODO+=("sf install doctor reported problems")

step "Done. Do these by hand"
TODO+=("claude: log in (run 'claude')" "gh auth login (then re-run this script to fill the GitHub MCP token)" "railway login; ramp login; vercel + gitlab MCP: /mcp in Claude to authenticate" "optional: export ANTHROPIC_API_KEY in ~/.zshrc for pay-as-you-go billing" "open Docker.app once")
printf ' - %s\n' "${TODO[@]}"
