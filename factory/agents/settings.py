"""Project settings emitter (TB-13): profile + roles -> the ``hooks`` section of ``settings.json``.

Pure and deterministic: no file access, clock, randomness, network or model call (the caller reads
the existing settings and writes the result). Only project-level settings are in scope.
Nothing project-specific is hard-coded; the hook ids come from the roles.
"""
from __future__ import annotations

import copy
import difflib
import json
from collections.abc import Mapping
from typing import Any

from factory.agents.generate import _HOME_RE, _SECRET_RE, HOOK_COMMAND, HOOK_REGISTRATION

OWN_PREFIX = "python -m factory.hooks"
# Events in emission order. ``stop_gate`` is registered under SubagentStop here (A-22).
_SETTINGS_EVENT = {"stop_gate": "SubagentStop"}


class SettingsError(ValueError):
    """The settings could not be emitted (malformed ``existing``, secret-shaped or home-path text)."""


def _is_own(hook: Any) -> bool:
    return isinstance(hook, Mapping) and isinstance(hook.get("command"), str) \
        and hook["command"].startswith(OWN_PREFIX)


def _hook_ids(roles: Mapping[str, Any]) -> list[str]:
    used: set[str] = set()
    for role in roles.values():
        used.update(role.hooks)
    unknown = sorted(used - set(HOOK_REGISTRATION))
    if unknown:
        raise SettingsError(f"unknown hook id {unknown[0]!r}")
    return [h for h in HOOK_REGISTRATION if h in used]  # canonical order


def _own_entries(hook_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for hid in hook_ids:
        event, matcher = HOOK_REGISTRATION[hid]
        event = _SETTINGS_EVENT.get(hid, event)
        entry: dict[str, Any] = {}
        if matcher:
            entry["matcher"] = matcher
        entry["hooks"] = [{"type": "command", "command": HOOK_COMMAND.format(hook_id=hid)}]
        out.setdefault(event, []).append(entry)
    return out


def _strip_own(entries: Any, event: str) -> list:
    if not isinstance(entries, list):
        raise SettingsError(f"hooks.{event} must be a list")
    kept = []
    for entry in entries:
        inner = entry.get("hooks") if isinstance(entry, Mapping) else None
        if not isinstance(inner, list) or not any(_is_own(h) for h in inner):
            kept.append(entry)
            continue
        rest = [h for h in inner if not _is_own(h)]
        if rest:
            kept.append({**entry, "hooks": rest})
    return kept


def emit_settings(profile: Any, roles: Mapping[str, Any], existing: Mapping | None = None) -> dict:
    """Return project settings registering the hooks used by ``roles``, merged over ``existing``.

    ``existing`` is never mutated. Entries whose command starts ``python -m factory.hooks`` are
    replaced to match the roles; everything else is preserved. No ``permissions`` rule is added.
    """
    if existing is None:
        existing = {}
    if not isinstance(existing, Mapping):
        raise SettingsError("existing settings must be a mapping")
    out = copy.deepcopy(dict(existing))
    old_hooks = out.get("hooks", {})
    if old_hooks is None:
        old_hooks = {}
    if not isinstance(old_hooks, Mapping):
        raise SettingsError("hooks must be a mapping")
    own = _own_entries(_hook_ids(roles))
    merged: dict[str, list] = {}
    for event, entries in old_hooks.items():
        kept = _strip_own(entries, event)
        if kept:
            merged[event] = kept
    for event, entries in own.items():
        merged[event] = merged.get(event, []) + entries
    out["hooks"] = merged
    text = json.dumps(out)
    if _SECRET_RE.search(text):
        raise SettingsError("settings contain a secret-shaped value")
    if _HOME_RE.search(text):
        raise SettingsError("settings contain an absolute home path")
    return out


def _dump(settings: Mapping | None) -> list[str]:
    return json.dumps(settings or {}, indent=2, sort_keys=True, ensure_ascii=False).splitlines()


def diff_settings(old: Mapping | None, new: Mapping | None) -> str:
    """Stable unified diff of two settings objects; empty when they are equal."""
    a, b = _dump(old), _dump(new)
    if a == b:
        return ""
    return "\n".join(difflib.unified_diff(a, b, "settings.json (current)", "settings.json (emitted)",
                                          lineterm="", n=3)) + "\n"
