# Claude Code launcher

Install with `sh skills/lsf/install.sh`. This installs both `lsf` and `claude-lsf`
under `~/.local/bin`. Requires Claude Code, Python 3.9+, git and the `away-mode`
skill; the workflow also calls the supporting skills named in SKILL.md.

For a shell that already wraps Claude, add this dispatch before its other cases:

```sh
if [ "${1:-}" = "-lsf" ]; then
  shift
  "$HOME/.local/bin/claude-lsf" "$@"
  return $?
fi
```

In a fresh terminal, inside the target repository:

```sh
claude -lsf
# Explicit interview model override:
claude -lsf --model opus
# Optional initial task:
claude -lsf 'Add the requested feature'
```

The launcher starts `/lsf`, enables Remote Control and bypass permissions,
requests the away-mode skill, and holds macOS awake with `caffeinate -ims`
for the lifetime of Claude. It defaults the main agent and subagents to Sonnet;
`--model` changes both. It strips inherited API credentials and model overrides
so Claude uses the signed-in subscription. Sign in with `claude auth login` first.
With no task it instructs Claude to wait before initializing the project clock.
A first-time workspace trust prompt can still appear.

After Claude initializes `.lsf`, the owner runs `lsf serve --open` in another
terminal and keeps it open. The local dashboard carries reports and checkpoint
approvals. Agents must not open its approval URL or release checkpoints.
Remote Control shares the Claude session; it does not expose this loopback-only
dashboard to a phone. No hosted Claude artifact is created by this launcher.
