"""Helpers for grading-side cases. Nothing here imports implementation code at module import time."""
from __future__ import annotations

import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROFILES = Path(__file__).parent / "profiles"
REPO = Path(__file__).resolve().parents[2]


def need(module: str, *attrs: str):
    """Import an implementation module (and check attributes); if absent the case is BLOCKED."""
    try:
        mod = importlib.import_module(module)
        for a in attrs:
            getattr(mod, a)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"BLOCKED: {module}{'.' + '/'.join(attrs) if attrs else ''} not available ({type(exc).__name__})")
    return mod


def profile_dict(name: str = "base", **overrides) -> dict:
    data = yaml.safe_load((PROFILES / f"{name}.yaml").read_text())
    data = copy.deepcopy(data)
    for key, value in overrides.items():
        data[key] = value
    return data


def make_project(tmp_path: Path, profile: str | dict = "base", files: dict | None = None, symlinks: dict | None = None) -> Path:
    """Create a fixture project under tmp_path with .factory/profile.yaml and the given files."""
    root = tmp_path / "proj"
    (root / ".factory").mkdir(parents=True)
    data = profile_dict(profile) if isinstance(profile, str) else profile
    (root / ".factory" / "profile.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    for rel, content in (files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for rel, target in (symlinks or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to(root / target)
    return root


def payload(root: Path, event: str = "PreToolUse", tool_name: str | None = None, tool_input: dict | None = None,
            agent_type: str | None = None, **extra) -> dict:
    data = {"session_id": "s1", "cwd": str(root), "hook_event_name": event, "permission_mode": "default"}
    if tool_name:
        data["tool_name"] = tool_name
        data["tool_input"] = tool_input or {}
    if agent_type:
        data["agent_type"] = agent_type
        data["agent_id"] = extra.pop("agent_id", "a1")
    data.update(extra)
    return data


def run_cli(hook_id: str, pl: dict, root: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run `python -m factory.hooks <hook_id>` with the payload on stdin, from the repo (so factory is importable)."""
    e = {k: v for k, v in os.environ.items() if k != "FACTORY_PROFILE"}
    e["PYTHONPATH"] = str(REPO) + os.pathsep + e.get("PYTHONPATH", "")
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "factory.hooks", hook_id], input=json.dumps(pl), text=True,
                          capture_output=True, cwd=str(root), env=e, timeout=60)


def run_decide(hook_module: str, pl: dict, root: Path):
    """Call `<hook_module>.decide(Payload, HookConfig)` in process. Blocked if any needed piece is missing."""
    core = need("factory.hooks.core", "parse_payload", "HookConfig")
    prof_mod = need("factory.agents.profile", "load_profile")
    hook = need(hook_module, "decide")
    profile = prof_mod.load_profile(root / ".factory" / "profile.yaml")
    cfg = core.HookConfig.from_profile(profile, root)
    return hook.decide(core.parse_payload(json.dumps(pl)), cfg)
