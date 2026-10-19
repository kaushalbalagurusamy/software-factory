"""``python -m factory.hooks <hook_id>``: read a payload on stdin, run the hook, exit 0 or 2."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from factory.agents.profile import ProfileError, load_profile
from factory.hooks import registry
from factory.hooks.core import (
    ERROR_PREFIX, HookConfig, HookError, HookResult, PayloadError, parse_payload, run_hook,
)

DEFAULT_PROFILE = Path(".factory") / "profile.yaml"


def _load_config(cwd: str) -> HookConfig:
    root = Path(cwd) if cwd else Path.cwd()
    env = os.environ.get("FACTORY_PROFILE")
    if env:
        path = Path(env)
        if not path.is_absolute():
            path = root / path
    else:
        path = root / DEFAULT_PROFILE
    try:
        profile = load_profile(path)
    except ProfileError as exc:
        raise HookError(f"invalid profile {path}: {exc}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise HookError(f"cannot read profile {path}: {exc}") from None
    return HookConfig.from_profile(profile, root)


def _report(stderr: str, message: str) -> str:
    line = f"{ERROR_PREFIX} {message}"
    return f"{stderr}\n{line}" if stderr else line


def _execute(hook_id: str, stdin_text: str) -> HookResult:
    try:
        hook = registry.get_hook(hook_id)
    except registry.UnknownHook:
        return HookResult(2, "", f"unknown hook: {hook_id}")
    except Exception as exc:  # noqa: BLE001 - e.g. an import error inside a guard module
        def failing(payload, cfg, _exc=exc):
            raise HookError(f"cannot load hook {hook_id}: {type(_exc).__name__}: {_exc}")
        return run_hook(failing, stdin_text, None)

    try:
        payload = parse_payload(stdin_text)
    except PayloadError:
        return run_hook(hook.decide, stdin_text, None)  # fails closed

    try:
        cfg = _load_config(payload.cwd)
    except Exception as exc:  # noqa: BLE001
        def failing(p, c, _exc=exc):
            raise _exc if isinstance(_exc, HookError) else HookError(str(_exc))
        return run_hook(failing, stdin_text, None)

    result = run_hook(hook.decide, stdin_text, cfg)
    stdout, stderr = result.stdout, result.stderr
    if hook.record is not None:
        try:
            hook.record(payload, cfg)
        except Exception as exc:  # noqa: BLE001 - never changes the exit code
            stderr = _report(stderr, f"record failed: {type(exc).__name__}: {exc}")
    if (hook.emit is not None and payload.event == "SessionStart"
            and not result.stderr.startswith(ERROR_PREFIX)):
        try:
            text = hook.emit(payload, cfg)
            if text:
                stdout += text
        except Exception as exc:  # noqa: BLE001
            stderr = _report(stderr, f"emit failed: {type(exc).__name__}: {exc}")
    return HookResult(result.exit_code, stdout, stderr)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("unknown hook: (expected exactly one hook id)")
        return 2
    try:
        stdin_text = sys.stdin.read()
    except Exception:  # noqa: BLE001
        stdin_text = ""
    result = _execute(args[0], stdin_text)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    return result.exit_code if result.exit_code in (0, 2) else 2


if __name__ == "__main__":
    sys.exit(main())
