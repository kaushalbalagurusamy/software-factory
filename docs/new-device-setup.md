# Onboard a new Mac to the Claude Code + Software Factory setup

Two parts: the old Mac exports what git does not carry, then Claude Code on the new Mac
does the install from this repo.

## 1. On the old Mac

    scripts/export-claude-setup.sh        # writes ~/Desktop/claude-migration.tgz (no secrets)

AirDrop it to the new Mac's `~/Downloads/`. It carries the skills that exist only in
`~/.claude/skills` (a local git repo with no remote), settings, hooks, memory notes and a
secret-stripped MCP list. Push this repo first so the clone has everything.

## 2. On the new Mac

Install Claude Code, log in, then:

    mkdir -p ~/Projects && git clone https://github.com/kaushalbalagurusamy/software-factory ~/Projects/software-factory
    cd ~/Projects/software-factory && git checkout docs/new-device-setup   # until merged to main
    claude

and paste:

> Follow docs/new-device-setup.md section "Agent steps". Verify each step, report failures
> instead of guessing, and ask me before anything needing a password or browser login.

## Agent steps

1. Prereqs: install Homebrew if missing; `brew install fnm uv gh jq github-mcp-server railway`;
   `brew install --cask docker-desktop`. Add `eval "$(fnm env --use-on-cd)"` to `~/.zshrc`,
   install Node 24 with fnm, make sure `claude` is current.
2. Extract: `mkdir -p ~/migration && tar -xzf ~/Downloads/claude-migration.tgz -C ~/migration`,
   then `rsync -a --exclude mcp-servers.export.json ~/migration/ ~/`. If `$USER` is not `kaushal`,
   replace `/Users/kaushal` with `$HOME` in `~/.claude/settings.json` and `~/.local/bin/*`.
   Skills symlinked into `Projects/software-factory/skills/` resolve after the clone. Two
   (`eli12-docs`, `mermaid-nesting-dolls`) point at a sync snapshot; replace them with the
   copies in the repo's `skills/` or report them missing.
3. Factory runtime: in the repo, `uv venv .venv && uv pip install -r requirements.txt && uv pip install -e .`
   (add anything pyproject.toml needs for Unity, Z3, Tree-sitter). Put `~/.local/bin` on PATH in
   `~/.zprofile` and `~/.zshrc`. Run `sf install doctor --project ~/Projects/software-factory`.
   This only checks; do not start a task or install into other projects.
4. Plugins: `claude plugin marketplace add` each entry in `extraKnownMarketplaces` of
   `~/.claude/settings.json` plus `anthropics/claude-plugins-official`; `claude plugin install
   <name>@<marketplace>` for each `enabledPlugins` entry set to true.
5. MCP: for each entry in `~/migration/.claude/mcp-servers.export.json`, `claude mcp add-json
   --scope user <name> '<json>'`. Secrets are blank: list which servers need a token or login
   (github PAT, vercel, gitlab, railway) and leave them to me. `supabase` (~/.gemini path) and
   `langfuse` (~/Projects/ai-red-team venv) point at things that will not exist: report, skip.
6. Shell: add this to `~/.zshrc` (replacing any `claude()`). Do not set `ANTHROPIC_API_KEY`;
   I add it myself if I want pay-as-you-go billing.

       claude() {
         if [ "${1:-}" = "-lsf" ]; then
           shift
           "$HOME/.local/bin/claude-lsf" "$@"
         elif [ "${1:-}" = "-sf" ]; then
           shift
           caffeinate -ims -w $$ > /dev/null 2>&1 &|
           command -v battery > /dev/null 2>&1 && battery maintain 70-80 > /dev/null 2>&1
           command claude --dangerously-skip-permissions --remote-control "sf-${PWD:t}" --name "sf-${PWD:t}" "$@" "/sf"
         else
           command claude "$@"
         fi
       }

7. Verify: `claude mcp list`, `claude plugin list`, `ls ~/.claude/skills`; run each hook in
   `settings.json` once with `echo '{}' |`. End with a checklist: works, needs me, not migrated.

Not migrated: conversation transcripts, other repos and worktrees, standalone binaries
(`gddy`, `qn`, `surfpool`, `codex`, `ramp`, solana), the Claude login and API key.
