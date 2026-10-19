"""Agent file generator (TB-03): role specs plus a profile -> ``.claude/agents/<role>.md`` text.

Deterministic and pure: no clock, randomness, network or file access. Nothing project-specific
is hard-coded; project facts come from the profile and role facts from the role specs.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

import yaml

from factory.agents.roles import MAX_TOOLS_LIMIT, ROLE_IDS, RoleSpec

AGENT_PATH = ".claude/agents/{role}.md"
HOOK_COMMAND = "python -m factory.hooks {hook_id}"

# hook id -> (event, matcher or None); matchers per clarification A-34, events per TB-03 item 6
# and A-21 / A-22.
HOOK_REGISTRATION: dict[str, tuple[str, str | None]] = {
    "path_guard": ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash"),
    "secrets_guard": ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash"),
    "blindness_guard": ("PreToolUse", "Read|Grep|Glob|Bash"),
    "bash_guard": ("PreToolUse", "Bash"),
    "stop_gate": ("Stop", None),
    "subagent_stop": ("SubagentStop", None),
    "ledger_audit": ("SubagentStop", None),
    "session_start": ("SessionStart", None),
}

_OVERRIDE_KEYS = ("model", "extra_skills", "mcp_servers")
_SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{10,}|gh[ousr]_[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,}"
    r"|AIza[0-9A-Za-z_-]{20,}|xox[abprs]-[A-Za-z0-9-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
_HOME_RE = re.compile(r"(?<![\w.])(?:/home/|/Users/|/root(?:/|\b)|~/|[A-Za-z]:\\Users\\)")


class GenerationError(ValueError):
    """Generation was refused. ``role`` is the role involved (may be empty)."""

    def __init__(self, message: str, role: str = "") -> None:
        self.role = role
        self.message = message
        super().__init__(f"role '{role}': {message}" if role else message)


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):  # indent sequences
        return super().increase_indent(flow, False)


def _frontmatter(data: dict) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, default_flow_style=False,
                     allow_unicode=True, width=10**9)


# ------------------------------------------------------------------ override handling

def _override_parts(role: str, ov: Any) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    if ov is None:
        return None, (), ()
    if isinstance(ov, Mapping):
        present = dict(ov)
    elif is_dataclass(ov) and not isinstance(ov, type):
        present = {f.name: getattr(ov, f.name) for f in fields(ov)}
        present.update({k: v for k, v in getattr(ov, "__dict__", {}).items() if k not in present})
    else:
        present = dict(getattr(ov, "__dict__", {}))
        present.update({k: getattr(ov, k) for k in _OVERRIDE_KEYS if hasattr(ov, k)})
    extra = [k for k in present if k not in _OVERRIDE_KEYS]
    if extra:
        raise GenerationError(
            f"override may only set model, extra_skills and mcp_servers (write access and "
            f"'writes' cannot be changed); got {', '.join(sorted(map(str, extra)))}", role)
    return (present.get("model"), tuple(present.get("extra_skills") or ()),
            tuple(present.get("mcp_servers") or ()))


# ------------------------------------------------------------------ tools

def _server_tools(profile: Any, server: str, access: str) -> list[str]:
    spec = profile.mcp_servers.get(server) if profile.mcp_servers else None
    if spec is None:
        return []
    if access == "write":
        return [f"mcp__{server}"]
    return [f"mcp__{server}__{t}" for t in spec.read_tools]


def _resolve_server(profile: Any, server: str) -> str | None:
    if server == "$deploy":
        return profile.deploy.platform_server if profile.deploy else None
    if server == "$git_host":
        return profile.git_host if profile.git_host in ("github", "gitlab") else None
    return server


def _build_tools(profile: Any, role: RoleSpec, override_servers: tuple[str, ...]) -> list[str]:
    tools: list[str] = list(role.core_tools)
    for entry in role.mcp:
        name = _resolve_server(profile, entry.server)
        if name:
            tools.extend(_server_tools(profile, name, entry.access))
    for name in override_servers:
        if name not in (profile.mcp_servers or {}):
            raise GenerationError(f"override names server {name!r} that the profile does not declare",
                                  role.id)
        tools.extend(_server_tools(profile, name, "read"))
    seen: set[str] = set()
    out = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ------------------------------------------------------------------ hooks

def _hooks_block(role: RoleSpec) -> dict:
    block: dict[str, list] = {}
    for hid in role.hooks:
        if hid not in HOOK_REGISTRATION:
            raise GenerationError(f"unknown hook id {hid!r}", role.id)
        event, matcher = HOOK_REGISTRATION[hid]
        entry: dict[str, Any] = {}
        if matcher is not None:
            entry["matcher"] = matcher
        entry["hooks"] = [{"type": "command", "command": HOOK_COMMAND.format(hook_id=hid)}]
        block.setdefault(event, []).append(entry)
    return block


# ------------------------------------------------------------------ body

def _folders(profile: Any, role: RoleSpec) -> list[str]:
    p = profile.paths
    return {
        "none": [],
        "app": [],
        "research_dir": [p.research_dir],
        "design_dirs": list(p.design_dirs),
        "audit_dir": [p.audit_dir],
        "eval_paths": list(p.eval),
    }[role.writes]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


def _may_write(profile: Any, role: RoleSpec) -> str:
    if role.writes == "none":
        return "Nothing. This role has no write access to any file."
    if role.writes == "app":
        return ("Application code and its unit tests, within the files named in your brief. "
                "The factory control folders `.factory/` and `.claude/` and the protected "
                "evaluation paths are never yours to write.")
    folders = ", ".join(f"`{f}`" for f in _folders(profile, role))
    extra = " Only before the freeze, except for the baseline-update paths." if role.writes == "eval_paths" else ""
    return f"Only under {folders}.{extra}"


def _never(role: RoleSpec) -> str:
    items = []
    if role.writes == "none":
        items.append("Create, write or edit any file.")
    else:
        items.append("Write outside the locations listed above.")
    if role.blind:
        items.append("Read, list, search or run anything under the evaluation or held-out paths.")
    if role.bash == "none":
        items.append("Run shell commands.")
    elif role.bash == "readonly":
        items.append("Run shell commands other than the read-only commands the path guard allows.")
    if role.spawns:
        items.append("Start any agent other than: " + ", ".join(role.spawns) + ".")
    else:
        items.append("Start any other agent.")
    if role.disallowed_tools:
        items.append("Use these tools: " + ", ".join(role.disallowed_tools) + ".")
    items.append("Write a secret value or an absolute home path into any file or message.")
    return _bullets(items)


def _body(profile: Any, role: RoleSpec, skills: list[str]) -> str:
    skill_text = (_bullets([f"`{s}`" for s in skills]) if skills
                  else "No skills are preloaded for this role.")
    return (
        f"## Purpose\n\n{role.description}\n\n"
        f"## You may write\n\n{_may_write(profile, role)}\n\n"
        f"## You must never\n\n{_never(role)}\n\n"
        f"## Skills\n\n{skill_text}\n"
    )


# ------------------------------------------------------------------ checks

def _check_name(profile: Any, role: str, body: str) -> None:
    name = profile.project.name.strip()
    if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", body, re.I):
        raise GenerationError(f"project name {name!r} appears in the role text", role)


def _check_clean(role: str, text: str) -> None:
    if _SECRET_RE.search(text):
        raise GenerationError("generated text contains a secret-shaped value", role)
    if _HOME_RE.search(text):
        raise GenerationError("generated text contains an absolute home path", role)


# ------------------------------------------------------------------ public

def _generate_one(profile: Any, role: RoleSpec) -> str:
    model, extra_skills, servers = _override_parts(role.id, (profile.agents or {}).get(role.id))
    tools = _build_tools(profile, role, servers)
    limit = min(role.max_tools, MAX_TOOLS_LIMIT)
    if len(tools) > limit:
        raise GenerationError(f"{len(tools)} tools exceed max_tools {limit}", role.id)
    skills = list(role.skills)
    skills.extend(s for s in extra_skills if s not in skills)
    fm: dict[str, Any] = {
        "name": role.id,
        "description": role.description,
        "model": model or role.model,
        "tools": ", ".join(tools),
    }
    if role.disallowed_tools:
        fm["disallowedTools"] = ", ".join(role.disallowed_tools)
    if skills:
        fm["skills"] = skills
    hooks = _hooks_block(role)
    if hooks:
        fm["hooks"] = hooks
    body = _body(profile, role, skills)
    _check_name(profile, role.id, body)
    text = f"---\n{_frontmatter(fm)}---\n\n{body}"
    _check_clean(role.id, text)
    return text


def generate_agents(profile: Any, roles: Mapping[str, RoleSpec]) -> dict[str, str]:
    """Return ``{'.claude/agents/<role>.md': text}`` for all seven roles, byte-identical per input."""
    if set(roles) != set(ROLE_IDS):
        raise GenerationError("roles must contain exactly the seven role ids")
    out: dict[str, str] = {}
    for rid in ROLE_IDS:
        spec = roles[rid]
        if spec.id != rid:
            raise GenerationError(f"role key {rid!r} holds spec {spec.id!r}", rid)
        out[AGENT_PATH.format(role=rid)] = _generate_one(profile, spec)
    return out
