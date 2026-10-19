"""Role specs: load and validate the seven agent roles from YAML data (TB-02)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROLE_IDS = ("orchestrator", "research", "design", "audit", "implement", "test", "review")
HOOK_IDS = (
    "path_guard", "blindness_guard", "secrets_guard", "bash_guard",
    "stop_gate", "subagent_stop", "ledger_audit", "session_start",
)
WRITES = ("none", "app", "research_dir", "design_dirs", "audit_dir", "eval_paths")
BASH_MODES = ("none", "readonly", "full")
MCP_ACCESS = ("read", "write")
MAX_TOOLS_LIMIT = 20
DEFAULT_DIR = Path(__file__).resolve().parent / "roles"

_FIELDS = (
    "id", "description", "model", "core_tools", "disallowed_tools", "skills", "mcp",
    "spawns", "writes", "bash", "blind", "hooks", "max_tools",
)


class RoleError(ValueError):
    """A role spec is invalid. Carries the role id and the offending field."""

    def __init__(self, role: str, field: str, message: str):
        self.role = role
        self.field = field
        self.message = message
        super().__init__(f"role '{role}', field '{field}': {message}")


@dataclass(frozen=True)
class McpEntry:
    server: str
    access: str

    def to_dict(self) -> dict:
        return {"server": self.server, "access": self.access}


@dataclass(frozen=True)
class RoleSpec:
    id: str
    description: str
    model: str
    core_tools: tuple[str, ...]
    disallowed_tools: tuple[str, ...]
    skills: tuple[str, ...]
    mcp: tuple[McpEntry, ...]
    spawns: tuple[str, ...]
    writes: str
    bash: str
    blind: bool
    hooks: tuple[str, ...]
    max_tools: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "model": self.model,
            "core_tools": list(self.core_tools),
            "disallowed_tools": list(self.disallowed_tools),
            "skills": list(self.skills),
            "mcp": [m.to_dict() for m in self.mcp],
            "spawns": list(self.spawns),
            "writes": self.writes,
            "bash": self.bash,
            "blind": self.blind,
            "hooks": list(self.hooks),
            "max_tools": self.max_tools,
        }


def _str(role: str, field: str, v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise RoleError(role, field, "must be a non-empty string")
    return v


def _str_list(role: str, field: str, v: Any) -> tuple[str, ...]:
    if not isinstance(v, list):
        raise RoleError(role, field, "must be a list")
    out = []
    for i, x in enumerate(v):
        if not isinstance(x, str) or not x.strip():
            raise RoleError(role, field, f"entry {i} must be a non-empty string; got {x!r}")
        out.append(x)
    return tuple(out)


def _choice(role: str, field: str, v: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(v, str) or v not in allowed:
        raise RoleError(role, field, f"must be one of {', '.join(allowed)}; got {v!r}")
    return v


def _parse(role: str, data: Any) -> RoleSpec:
    if not isinstance(data, dict):
        raise RoleError(role, "id", "role file must be a mapping")
    for f in _FIELDS:
        if f not in data:
            raise RoleError(role, f, "missing field")
    for k in data:
        if k not in _FIELDS:
            raise RoleError(role, str(k), "unknown field")
    rid = _choice(role, "id", data["id"], ROLE_IDS)
    if rid != role:
        raise RoleError(role, "id", f"id {rid!r} does not match file name {role!r}")
    description = _str(role, "description", data["description"])
    model = _str(role, "model", data["model"])
    core_tools = _str_list(role, "core_tools", data["core_tools"])
    disallowed = _str_list(role, "disallowed_tools", data["disallowed_tools"])
    skills = _str_list(role, "skills", data["skills"])
    spawns = _str_list(role, "spawns", data["spawns"])
    if not isinstance(data["mcp"], list):
        raise RoleError(role, "mcp", "must be a list")
    mcp = []
    for i, m in enumerate(data["mcp"]):
        where = f"entry {i}"
        if not isinstance(m, dict) or set(m) != {"server", "access"}:
            raise RoleError(role, "mcp", f"{where} must be a mapping with exactly server and access")
        if not isinstance(m["server"], str) or not m["server"].strip():
            raise RoleError(role, "mcp", f"{where} server must be a non-empty string")
        if m["access"] not in MCP_ACCESS:
            raise RoleError(role, "mcp", f"{where} access must be one of {', '.join(MCP_ACCESS)}; got {m['access']!r}")
        mcp.append(McpEntry(m["server"], m["access"]))
    writes = _choice(role, "writes", data["writes"], WRITES)
    bash = _choice(role, "bash", data["bash"], BASH_MODES)
    blind = data["blind"]
    if not isinstance(blind, bool):
        raise RoleError(role, "blind", "must be a boolean")
    hooks = _str_list(role, "hooks", data["hooks"])
    for i, h in enumerate(hooks):
        if h not in HOOK_IDS:
            raise RoleError(role, "hooks", f"entry {i}: unknown hook id {h!r}")
    mt = data["max_tools"]
    if not isinstance(mt, int) or isinstance(mt, bool):
        raise RoleError(role, "max_tools", "must be an integer")
    if mt > MAX_TOOLS_LIMIT:
        raise RoleError(role, "max_tools", f"must be at most {MAX_TOOLS_LIMIT}; got {mt}")
    if mt < 1:
        raise RoleError(role, "max_tools", "must be at least 1")
    if len(core_tools) > mt:
        raise RoleError(role, "core_tools", f"{len(core_tools)} tools exceed max_tools {mt}")
    return RoleSpec(rid, description, model, core_tools, disallowed, skills, tuple(mcp),
                    spawns, writes, bash, blind, hooks, mt)


def load_roles(dir: str | Path | None = None) -> dict[str, RoleSpec]:
    """Load and validate all seven role specs from `dir` (default: the shipped data)."""
    base = Path(dir) if dir is not None else DEFAULT_DIR
    found: dict[str, RoleSpec] = {}
    for path in sorted(base.glob("*.yaml")):
        role = path.stem
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RoleError(role, "id", f"invalid YAML: {exc}") from exc
        if role not in ROLE_IDS:
            raise RoleError(role, "id", "not one of the seven role ids")
        found[role] = _parse(role, data)
    for role in ROLE_IDS:
        if role not in found:
            raise RoleError(role, "id", f"missing role file {role}.yaml")
    return {role: found[role] for role in ROLE_IDS}
