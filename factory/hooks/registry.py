"""Lazy hook registry (TB-04).

A guard module registers itself just by existing: hook id ``X`` resolves to the module
``factory.hooks.X`` exporting ``decide`` and optionally ``record`` and ``emit``. No edit to this
file is needed. ``register`` is also available for explicit registration (tests, plug-ins).
A hook id whose module does not exist yet resolves to a stub that fails closed.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from factory.hooks.core import HookError

HOOK_IDS: tuple[str, ...] = (
    "path_guard", "blindness_guard", "secrets_guard", "bash_guard",
    "stop_gate", "subagent_stop", "ledger_audit", "session_start",
)
_PACKAGE = "factory.hooks"


class UnknownHook(KeyError):
    """The id is not one of :data:`HOOK_IDS`."""


@dataclass(frozen=True)
class Hook:
    id: str
    decide: Callable[..., Any]
    record: Callable[..., Any] | None = None
    emit: Callable[..., Any] | None = None
    implemented: bool = True


_cache: dict[str, Hook] = {}


def _check_id(hook_id: str) -> None:
    if hook_id not in HOOK_IDS:
        raise UnknownHook(hook_id)


def register(hook_id: str, decide: Callable[..., Any], record: Callable[..., Any] | None = None,
             emit: Callable[..., Any] | None = None) -> Hook:
    _check_id(hook_id)
    hook = Hook(hook_id, decide, record, emit)
    _cache[hook_id] = hook
    return hook


def _stub(hook_id: str) -> Hook:
    def decide(payload: Any, cfg: Any) -> Any:
        raise HookError(f"hook not implemented: {hook_id}")
    return Hook(hook_id, decide, implemented=False)


def _load(hook_id: str) -> Hook:
    name = f"{_PACKAGE}.{hook_id}"
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return _stub(hook_id)
        raise
    decide = getattr(module, "decide", None)
    if not callable(decide):
        def bad(payload: Any, cfg: Any) -> Any:
            raise HookError(f"hook module {name} has no decide function")
        return Hook(hook_id, bad, implemented=False)
    return Hook(hook_id, decide, getattr(module, "record", None), getattr(module, "emit", None))


def get_hook(hook_id: str) -> Hook:
    """Resolve a hook id lazily. Raises :class:`UnknownHook` for ids outside :data:`HOOK_IDS`."""
    _check_id(hook_id)
    hook = _cache.get(hook_id)
    if hook is None:
        hook = _cache[hook_id] = _load(hook_id)
    return hook
