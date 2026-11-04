---
name: vultr-workflow
description: Develop and operate Claude sessions on the gauntlet-ai-kaushal Vultr VPS, with phone-accessible previews, screenshot evidence, and a configurable weekly session roster.
---

# Vultr workflow

Apply this context on Linux host `gauntlet-ai-kaushal`, home `/home/linuxuser`. Project execution and builds happen here; the owner usually controls the session from the Claude phone app. `localhost` links and filesystem paths on this VPS are not directly accessible from the phone.

Prefer the project's existing Railway deployment or an approved Railway preview for browser exploration. Read its Railway configuration and project requirements first. Respect project-specific hosting constraints, including local-only or no-paid-service requirements. Verify a deployed URL responds and exercises the changed behavior before calling it available. Provide the full clickable HTTPS URL in updates; do not claim deployment from a successful local build.

For visual development, use available Playwright screenshot tooling against the actual deployed page after meaningful changes. Return the screenshot tool's image result so it appears in the conversation, along with the deployed URL and a short account of what it demonstrates. Save screenshots as evidence when useful. A VPS file path alone is not a delivered image. Do not substitute a mockup for a screenshot of running software. If the screenshot or deployment fails, report the specific gap.

`claude -sf` combines indefinite away mode, Remote Control, the Sonnet default, and `/sf`. On this VPS away mode means a persistent tmux session with reboot recovery; it requires neither caffeinate, an open Mac lid, nor Mac power settings. The `/sf` build loop still follows each project's profile and existing human gates. If a profile is absent, establish it with the owner rather than guessing project requirements.

## Weekly roster and recovery

The authoritative roster is `~/.claude/vultr/sessions.json`; `~/.claude/vultr/SESSIONS.md` explains operations. At the beginning of a new week's planning, or when the owner changes active projects, ask which sessions should remain open, be added, or be retired. Keep the saved roster until an answer arrives, and update it only to reflect the owner's choices. Do not interrupt crash recovery waiting for an answer.

The user service `claude-project-sessions.service` restores enabled sessions after reboot or process exit, preserving each conversation UUID and resuming its transcript when present. Disabled sessions are not restarted. Changing a directory should use a new roster ID and conversation UUID. Retiring a session means disable its roster entry first, then stop its corresponding `vultr-ID` tmux session; retain conversation history and project files. Never stop other sessions or add projects merely because their folders exist.
