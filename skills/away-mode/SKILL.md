---
name: away-mode
description: Prepare this Mac to keep a Claude Code session running while the user is away and driving it from their phone through Remote Control. Runs pre-flight checks (power, battery, network, Docker, git), keeps the Mac awake with caffeinate tied to the current session, and gives a hand-off checklist; also reports status and undoes everything on stop. Use when the user types /away-mode, or says things like "I'm heading out", "going remote", "keep the laptop awake", "switch to my phone", "is away mode on", or "I'm back, turn off away mode".
---

# Away mode

The scripts live in `~/.claude/skills/away-mode/scripts/`. Run them with Bash from the session's working directory. They print one line per check, prefixed `[ok]`, `[info]`, `[warn]`, or `[fail]`.

## Choose the action

| Request | Command |
|---|---|
| Start (default). Optional duration such as `4h`, `90m`, or seconds like `3600` | `~/.claude/skills/away-mode/scripts/start.sh [duration]` |
| Status ("is away mode on?") | `~/.claude/skills/away-mode/scripts/status.sh` |
| Stop ("I'm back") | `~/.claude/skills/away-mode/scripts/stop.sh` (add `--all` to stop away mode for every session on this Mac) |

Without a duration, the Mac stays awake until this Claude Code session exits. Running start again replaces the previous timer.

## After starting

Report the result briefly, listing every `[warn]` and `[fail]` line first. Then give the user this checklist:

1. **Leave the lid open.** Closing the lid sleeps the Mac even while caffeinate runs.
2. **Run `/remote-control`** in this session and scan the QR code with the Claude app. You cannot run this yourself, because built-in commands must be typed by the user. Skip this step if the user has enabled Remote Control for all sessions in `/config`.
3. **Notifications:** permission prompts and finished tasks push to the phone when notifications are enabled.

If this session is running in bypass permissions mode (your system prompt says so), warn the user: anyone who reaches the session through their Claude account can run commands with no approval step. Suggest switching to a mode with permission prompts before leaving, by cycling modes with Shift+Tab or restarting Claude Code without `--dangerously-skip-permissions`. Mention it once; do not block on it.

## Keeping it awake with the lid closed

This skill deliberately does not disable lid-close sleep. Doing so needs admin rights, changes a system-wide setting, and can overheat a Mac in a bag. Never run `sudo` yourself. If the user explicitly asks for it, explain those risks and give them the commands to run with the `!` prefix:

- Enable: `! sudo pmset -a disablesleep 1`
- Undo: `! sudo pmset -a disablesleep 0`

`start.sh`, `status.sh`, and `stop.sh` all report when this setting is still on, and on stop you should remind the user to undo it.

## Battery health and sailing mode

Away mode automatically integrates with the `battery` CLI (`actuallymentor/battery`). When connected to wall power:
- Pre-flight verifies that `battery maintain 70-80` is active.
- It operates the Mac on **AC pass-through** while capping charge levels (70%–80%).
- This allows the laptop to remain plugged in indefinitely for autonomous Remote Control sessions without risk of sudden battery depletion or lithium battery swelling.
- If the user needs 100% charge for travel, they can toggle it with `battery maintain stop` or `battery charge 100`.

## What it does not do

- It does not start Remote Control.
- It does not keep the Mac online if Wi-Fi drops or the lid closes.
- It never touches caffeinate processes it did not start.
