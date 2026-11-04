# Onboard a new Mac (Claude Code + terminal)

`device-setup/` is a snapshot of the setup; two scripts move it.

| Script | Run where | What it does |
|---|---|---|
| `scripts/export-device-setup.sh` | old Mac | Refreshes `device-setup/` (then commit and push). |
| `scripts/install-device-setup.sh` | new Mac | Installs everything below. Idempotent; replaced files are kept as `*.pre-device-setup`. |

## New Mac, one command

    xcode-select --install   # if git is missing
    git clone https://github.com/kaushalbalagurusamy/software-factory ~/Projects/software-factory
    cd ~/Projects/software-factory && git checkout docs/new-device-setup   # until merged
    scripts/install-device-setup.sh

## What is in `device-setup/`

- `Brewfile`: formulae, casks and taps (fnm, uv, gh, starship, zoxide, fzf, yazi, zellij, zsh plugins, Docker, ramp-cli, ...).
- `shell/`: `.zshrc`, `.zprofile`, `.gitconfig`, starship, yazi and zellij config, and the Terminal.app profile (imported and set as default).
- `claude/`: `CLAUDE.md`, `settings.json` (hooks, status line, plugin and marketplace list), hooks, `statusline.py`, `mcp-servers.json` (secrets blanked), the wrappers `sf`, `lsf`, `claude-lsf`, `lsf-vps`, and my own skills.
- Skills the repo already owns (`claude/skills-linked.txt`) are symlinked to `skills/` here. `ramp-*` skills come from `ramp skills install --all`.

## Not carried (by design)

Secrets and logins: Claude, `gh`, railway, ramp, vercel, gitlab, `ANTHROPIC_API_KEY`. The installer prints this list at the end.
Also not carried: conversation transcripts, other repos, `minesweeper/runs`, standalone binaries
(`gddy`, `qn`, `surfpool`, solana). MCP servers whose binary is missing on the new Mac (`supabase`, `langfuse`) are skipped and reported.
The GitHub MCP token is filled from `gh auth token`, so run `gh auth login` and re-run the installer.
