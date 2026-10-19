"""End-to-end walking skeleton (TB-14): run a scripted hook event stream against a project.

Contracts: ``docs/contracts/hook-io.md`` and clarification C-26. Documentation: ``docs/hooks/e2e.md``.

The project's profile (``<project_root>/.factory/profile.yaml``) is the only project input: the
agent files and settings are generated from it in memory, and the hooks to run for each event are
looked up from those generated settings plus the payload agent's frontmatter hooks. Every hook
runs in process through the same registry the command line uses. Deterministic; no network and no
model call; nothing is written by this module (a hook's own side effects, such as the stop gate's
counter under ``.factory/state``, still happen, as they would in a live session).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from factory.agents.generate import AGENT_PATH, generate_agents
from factory.agents.profile import load_profile
from factory.agents.roles import load_roles
from factory.agents.settings import OWN_PREFIX, emit_settings
from factory.hooks import registry
from factory.hooks.core import (
    ERROR_PREFIX, KNOWN_EVENTS, PRE_EVENTS, STOP_EVENTS, Decision, HookConfig, PayloadError,
    parse_payload,
)

PROFILE_PATH = Path(".factory") / "profile.yaml"
SETTINGS_PATH = ".claude/settings.json"
_TOOL_EVENTS = frozenset({"PreToolUse", "PostToolUse"})


@dataclass(frozen=True)
class Outcome:
    """Combined result of every hook run for one event (C-26)."""

    kind: str                                    # allow, deny, ask or block
    reasons: list[str] = field(default_factory=list)  # non-empty reasons, in hook order


def _load(project_root: Path):
    profile = load_profile(project_root / PROFILE_PATH)
    roles = load_roles()
    return profile, roles, generate_agents(profile, roles), emit_settings(profile, roles)


def generate_project(project_root: Path | str) -> dict[str, str]:
    """The agent files and ``.claude/settings.json`` text the profile alone produces (not written)."""
    _, _, agents, settings = _load(Path(project_root))
    return {**agents, SETTINGS_PATH: json.dumps(settings, indent=2) + "\n"}


def _frontmatter_hooks(text: str) -> Mapping:
    # Generated text always starts "---\n<yaml>---\n".
    return (yaml.safe_load(text.split("---\n", 2)[1]) or {}).get("hooks") or {}


def _matches(matcher: Any, event: str, tool: str | None) -> bool:
    if event not in _TOOL_EVENTS or matcher in (None, "", "*"):
        return True
    return tool is not None and re.fullmatch(matcher, tool) is not None


def _hook_ids(hooks: Mapping, event: str, tool: str | None) -> list[str]:
    out = []
    for entry in hooks.get(event) or []:
        if not _matches(entry.get("matcher"), event, tool):
            continue
        for h in entry.get("hooks") or []:
            cmd = h.get("command", "")
            # shortcut: only the factory's own hooks can run in process; foreign commands are skipped.
            if cmd.startswith(OWN_PREFIX + " "):
                out.append(cmd[len(OWN_PREFIX) + 1:].strip())
    return out


def _hooks_for(settings: dict, agents: dict[str, str], event: str, tool: str | None,
               agent_type: str | None) -> list[str]:
    ids = _hook_ids(settings.get("hooks") or {}, event, tool)
    text = agents.get(AGENT_PATH.format(role=agent_type)) if agent_type else None
    if text is not None:
        fm = _frontmatter_hooks(text)
        ids += _hook_ids(fm, event, tool)
        if event == "SubagentStop":  # a sub-agent's frontmatter Stop hook runs as SubagentStop (A-22)
            ids += _hook_ids(fm, "Stop", tool)
    return list(dict.fromkeys(ids))  # dedupe, keep first (settings) order


def _decide_fn(hook_id: str) -> tuple[Callable, Callable | None]:
    hook = registry.get_hook(hook_id)
    return hook.decide, hook.record


def _effective(event: str, kind: str) -> str:
    """The kind the protocol adapter actually enforces for this event (A-04-5)."""
    if event in STOP_EVENTS and kind != "allow":
        return "block"
    if event in PRE_EVENTS and kind == "block":
        return "deny"
    return kind


def _fail(event: str | None, message: str) -> Decision:
    return Decision("block" if event in STOP_EVENTS else "deny", f"{ERROR_PREFIX} {message}")


def _run_one(event: Any, project_root: Path, cfg: HookConfig, settings: dict,
             agents: dict[str, str]) -> Outcome:
    raw = event.get("payload") if isinstance(event, Mapping) else None
    if not isinstance(raw, Mapping):
        return Outcome("deny", [f"{ERROR_PREFIX} event has no payload object"])
    raw = dict(raw)
    if not raw.get("cwd"):
        raw["cwd"] = str(project_root)
    try:
        payload = parse_payload(json.dumps(raw))
    except (PayloadError, TypeError, ValueError) as exc:
        return Outcome("deny", [f"{ERROR_PREFIX} {exc}"])
    if payload.event not in KNOWN_EVENTS:
        return Outcome("deny", [f"{ERROR_PREFIX} unknown event {payload.event!r}"])

    decisions = []
    for hid in _hooks_for(settings, agents, payload.event, payload.tool_name, payload.agent_type):
        try:
            decide, record = _decide_fn(hid)
            d = decide(payload, cfg)
            if not isinstance(d, Decision):
                d = _fail(payload.event, f"{hid} returned {type(d).__name__}, not a Decision")
        except Exception as exc:  # noqa: BLE001 - fail closed, as run_hook does
            d, record = _fail(payload.event, f"{hid}: {type(exc).__name__}: {exc}"), None
        decisions.append(Decision(_effective(payload.event, d.kind), d.reason))
        if record is not None:
            try:
                record(payload, cfg)
            except Exception:  # noqa: BLE001 - record never changes the outcome (hook-io.md)
                pass

    reasons = [d.reason for d in decisions if d.reason]
    found = {d.kind for d in decisions}
    for kind in ("deny", "block", "ask"):
        if kind in found:
            if kind != "ask":  # deny and block share top precedence: the first one in hook order
                kind = next(d.kind for d in decisions if d.kind in ("deny", "block"))
            return Outcome(kind, reasons)
    return Outcome("allow", reasons)


def run_events(project_root: Path | str, events: list[dict]) -> list[Outcome]:
    """Decide each ``{"payload": {...}}`` event as the project's generated hooks would (C-26).

    Raises ``ProfileError`` (or ``OSError``) if the profile cannot be loaded. A malformed event or a
    failing hook never raises: it fails closed as a deny (block on Stop and SubagentStop).
    """
    root = Path(project_root)
    profile, _, agents, settings = _load(root)
    cfg = HookConfig.from_profile(profile, root)
    return [_run_one(ev, root, cfg, settings, agents) for ev in events]
