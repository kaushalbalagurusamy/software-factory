"""Hook core (TB-04): payload parsing, decisions, protocol adapter and shared config.

Contracts: ``docs/contracts/hook-io.md`` and the TB-04 clauses of ``docs/contracts/clarifications.md``.
Deterministic: no network, no model call, no environment access. Nothing project-specific is
hard-coded; everything comes from the :class:`~factory.agents.profile.Profile`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from factory.agents.profile import Checks, Profile

DECISION_KINDS: tuple[str, ...] = ("allow", "deny", "ask", "block")
PRE_EVENTS = frozenset({"PreToolUse"})
STOP_EVENTS = frozenset({"Stop", "SubagentStop"})
PASSIVE_EVENTS = frozenset({"PostToolUse", "SessionStart"})
KNOWN_EVENTS = PRE_EVENTS | STOP_EVENTS | PASSIVE_EVENTS
ERROR_PREFIX = "hook error:"


class PayloadError(ValueError):
    """The hook's stdin is not a usable payload."""


class HookError(Exception):
    """An error a hook (or the command line) wants reported as ``hook error: <message>``."""


@dataclass(frozen=True)
class Payload:
    event: str
    tool_name: str | None
    tool_input: dict
    agent_type: str | None
    agent_id: str | None
    cwd: str
    last_assistant_message: str | None
    agent_transcript_path: str | None
    raw: dict


@dataclass(frozen=True)
class Decision:
    kind: Literal["allow", "deny", "ask", "block"]
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind not in DECISION_KINDS:
            raise ValueError(f"invalid decision kind: {self.kind!r}")
        if self.kind != "allow" and not (isinstance(self.reason, str) and self.reason):
            raise ValueError(f"a {self.kind} decision needs a non-empty reason")


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    stdout: str
    stderr: str


def _opt_str(raw: dict, key: str) -> str | None:
    v = raw.get(key)
    return v if isinstance(v, str) else None


def parse_payload(stdin_text: str) -> Payload:
    """Parse hook stdin. Raises :class:`PayloadError` on invalid JSON, a non-object, a missing
    or non-string ``hook_event_name``, or a present ``tool_input`` that is not an object."""
    try:
        raw = json.loads(stdin_text)
    except (TypeError, ValueError) as exc:
        raise PayloadError(f"invalid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise PayloadError("payload is not a JSON object")
    event = raw.get("hook_event_name")
    if not isinstance(event, str) or not event:
        raise PayloadError("missing hook_event_name")
    tool_input = raw.get("tool_input")
    if tool_input is None:
        tool_input = {}
    elif not isinstance(tool_input, dict):
        raise PayloadError("tool_input is not an object")
    return Payload(
        event=event,
        tool_name=_opt_str(raw, "tool_name"),
        tool_input=tool_input,
        agent_type=_opt_str(raw, "agent_type"),
        agent_id=_opt_str(raw, "agent_id"),
        cwd=_opt_str(raw, "cwd") or "",
        last_assistant_message=_opt_str(raw, "last_assistant_message"),
        agent_transcript_path=_opt_str(raw, "agent_transcript_path"),
        raw=raw,
    )


@dataclass(frozen=True)
class HookConfig:
    """Resolved view of the profile for hooks. ``profile`` is the full profile; the other
    fields are convenience copies. Glob lists are project-relative, as in the profile."""

    profile: Profile
    project_root: Path
    eval_globs: tuple[str, ...]
    held_out: tuple[str, ...]
    frozen_tests: tuple[str, ...]
    baseline_update: tuple[str, ...]
    research_dir: str
    design_dirs: tuple[str, ...]
    audit_dir: str
    ledger_dir: Path
    main_session_role: str
    checks: Checks
    one_way_door_patterns: tuple[str, ...]
    secret_allow_patterns: tuple[str, ...]

    @classmethod
    def from_profile(cls, profile: Profile, project_root: Path | str) -> "HookConfig":
        root = Path(project_root)
        p = profile.paths
        return cls(
            profile=profile,
            project_root=root,
            eval_globs=tuple(p.eval),
            held_out=tuple(p.held_out),
            frozen_tests=tuple(p.frozen_tests),
            baseline_update=tuple(p.baseline_update),
            research_dir=p.research_dir,
            design_dirs=tuple(p.design_dirs),
            audit_dir=p.audit_dir,
            ledger_dir=root / p.ledger_dir,
            main_session_role=profile.main_session_role,
            checks=profile.checks if profile.checks is not None else Checks(),
            one_way_door_patterns=tuple(profile.one_way_door_patterns),
            secret_allow_patterns=tuple(profile.secret_allow_patterns),
        )

    def role_for(self, payload: Payload) -> str:
        """The payload's ``agent_type``, or the profile's ``main_session_role`` for the main session."""
        return payload.agent_type if payload.agent_type else self.main_session_role


def _fail_closed(event: str | None, message: str) -> HookResult:
    """Deny/block for PreToolUse, Stop, SubagentStop and anything unknown or unparseable;
    exit 0 with stderr only for PostToolUse and SessionStart."""
    reason = f"{ERROR_PREFIX} {message}"
    if event in PASSIVE_EVENTS:
        return HookResult(0, "", reason)
    if event in STOP_EVENTS:
        return HookResult(0, json.dumps({"decision": "block", "reason": reason}, separators=(",", ":")), "")
    return HookResult(2, "", reason)


def _adapt(event: str, d: Decision) -> HookResult:
    if d.kind == "allow":
        return HookResult(0, "", "")
    if event in PASSIVE_EVENTS:
        return HookResult(0, "", d.reason)
    if event in STOP_EVENTS:
        return HookResult(0, json.dumps({"decision": "block", "reason": d.reason}, separators=(",", ":")), "")
    if d.kind == "ask":
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                      "permissionDecisionReason": d.reason}}
        return HookResult(0, json.dumps(out, separators=(",", ":")), "")
    return HookResult(2, "", d.reason)  # deny, or block treated as deny


def _describe(exc: BaseException) -> str:
    if isinstance(exc, HookError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def run_hook(decide: Callable[[Payload, Any], Decision], stdin_text: str, cfg: Any) -> HookResult:
    """Run ``decide`` on the payload and adapt the result to the Claude Code protocol.
    Never raises; the exit code is always 0 or 2."""
    event: str | None = None
    try:
        try:
            payload = parse_payload(stdin_text)
        except PayloadError as exc:
            return _fail_closed(None, str(exc))
        event = payload.event
        if event not in KNOWN_EVENTS:
            return _fail_closed(None, f"unknown event {event!r}")
        decision = decide(payload, cfg)
        if not isinstance(decision, Decision):
            return _fail_closed(event, f"decide returned {type(decision).__name__}, not a Decision")
        return _adapt(event, decision)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything
        return _fail_closed(event, _describe(exc))
