"""Project profile loader (TB-01).

Loads ``.factory/profile.yaml`` into an immutable :class:`Profile`. No network access, no
environment variables, no file other than the profile is read. Nothing project-specific is
hard-coded here; the only constants are the contract's role ids and defaults.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

ROLE_IDS: tuple[str, ...] = (
    "orchestrator", "research", "design", "audit", "implement", "test", "review",
)
GIT_HOSTS: tuple[str, ...] = ("github", "gitlab", "none")
TRACKERS: tuple[str, ...] = ("none", "linear", "notion")

DEFAULT_MAIN_SESSION_ROLE = "orchestrator"
DEFAULT_RESEARCH_DIR = "research"
DEFAULT_DESIGN_DIRS: tuple[str, ...] = ("docs/prd", "docs/spec", "docs/adr")
DEFAULT_AUDIT_DIR = "docs/audit"
DEFAULT_LEDGER_DIR = ".factory/ledger"

_TOP_LEVEL_ORDER = (
    "schema_version", "project", "main_session_role", "paths", "agents", "mcp_servers",
    "graph", "deploy", "git_host", "tracker", "checks", "one_way_door_patterns",
    "secret_allow_patterns",
)


class ProfileError(Exception):
    """An invalid profile. ``field`` is the dotted path of the first problem."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}" if field else message)
        self.field = field
        self.message = message


class FrozenMap(Mapping):
    """Read-only, hashable mapping (values must themselves be hashable)."""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping | None = None) -> None:
        object.__setattr__(self, "_data", dict(data or {}))

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        return hash(frozenset(self._data.items()))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("FrozenMap is immutable")

    def __repr__(self) -> str:
        return f"FrozenMap({self._data!r})"


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


class _Dictable:
    def to_dict(self) -> dict:
        return _plain(self)


@dataclass(frozen=True)
class Project(_Dictable):
    name: str


@dataclass(frozen=True)
class Paths(_Dictable):
    eval: tuple[str, ...]
    held_out: tuple[str, ...] = ()
    frozen_tests: tuple[str, ...] = ()
    baseline_update: tuple[str, ...] = ()
    research_dir: str = DEFAULT_RESEARCH_DIR
    design_dirs: tuple[str, ...] = DEFAULT_DESIGN_DIRS
    audit_dir: str = DEFAULT_AUDIT_DIR
    ledger_dir: str = DEFAULT_LEDGER_DIR


@dataclass(frozen=True)
class AgentOverride(_Dictable):
    model: str | None = None
    extra_skills: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpServer(_Dictable):
    read_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stage(_Dictable):
    id: str
    role: str
    gate: bool = False


@dataclass(frozen=True)
class GraphSpec(_Dictable):
    stages: tuple[Stage, ...]
    edges: tuple[tuple[str, str], ...] = ()
    loops: tuple[tuple[str, str], ...] = ()
    subsets: Mapping = FrozenMap()


@dataclass(frozen=True)
class Deploy(_Dictable):
    route: str | None = None
    platform_server: str | None = None
    checklist: str | None = None


@dataclass(frozen=True)
class Checks(_Dictable):
    test: str | None = None
    lint: str | None = None
    verify: str | None = None


@dataclass(frozen=True)
class Profile(_Dictable):
    schema_version: int
    project: Project
    paths: Paths
    main_session_role: str = DEFAULT_MAIN_SESSION_ROLE
    agents: Mapping = FrozenMap()
    mcp_servers: Mapping = FrozenMap()
    graph: GraphSpec | None = None
    deploy: Deploy | None = None
    git_host: str = "none"
    tracker: str = "none"
    checks: Checks | None = None
    one_way_door_patterns: tuple[str, ...] = ()
    secret_allow_patterns: tuple[str, ...] = ()


# ---------------------------------------------------------------- validation helpers

def _fail(field: str, message: str) -> ProfileError:
    return ProfileError(field, message)


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _need_mapping(v: Any, field: str) -> Mapping:
    if not isinstance(v, Mapping):
        raise _fail(field, "must be a mapping")
    return v


def _need_str(v: Any, field: str, *, nonempty: bool = False) -> str:
    if not _is_str(v):
        raise _fail(field, "must be a string")
    if nonempty and not v.strip():
        raise _fail(field, "must not be empty")
    return v


def _need_list(v: Any, field: str) -> list:
    if not isinstance(v, list):
        raise _fail(field, "must be a list")
    return v


def _str_list(v: Any, field: str) -> tuple[str, ...]:
    out = []
    for i, item in enumerate(_need_list(v, field)):
        if not _is_str(item):
            raise _fail(f"{field}[{i}]", "must be a string")
        out.append(item)
    return tuple(out)


_GLOB_BAD = re.compile(r"[?\[\]{}]|\*\*\*")


def _check_path(value: Any, field: str) -> str:
    if not _is_str(value):
        raise _fail(field, "must be a string")
    if not value:
        raise _fail(field, "path must not be empty")
    if value.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", value):
        raise _fail(field, "path must be relative to the project root, not absolute")
    if ".." in value.replace("\\", "/").split("/"):
        raise _fail(field, "path must not contain a '..' segment")
    if _GLOB_BAD.search(value):
        raise _fail(field, "globs may use only '*' and '**'")
    return value


def _path_list(v: Any, field: str) -> tuple[str, ...]:
    out = []
    for i, item in enumerate(_need_list(v, field)):
        out.append(_check_path(item, f"{field}[{i}]"))
    return tuple(out)


def _regex_list(v: Any, field: str) -> tuple[str, ...]:
    out = []
    for i, item in enumerate(_need_list(v, field)):
        if not _is_str(item):
            raise _fail(f"{field}[{i}]", "must be a string")
        try:
            re.compile(item)
        except re.error as exc:
            raise _fail(f"{field}[{i}]", f"invalid regular expression: {exc}") from None
        out.append(item)
    return tuple(out)


def _role(v: Any, field: str) -> str:
    if not _is_str(v) or v not in ROLE_IDS:
        raise _fail(field, f"must be one of the role ids {', '.join(ROLE_IDS)}")
    return v


# ---------------------------------------------------------------- section parsers

def _parse_project(v: Any) -> Project:
    m = _need_mapping(v, "project")
    if "name" not in m:
        raise _fail("project.name", "is required")
    return Project(name=_need_str(m["name"], "project.name", nonempty=True))


def _parse_paths(v: Any) -> Paths:
    m = _need_mapping(v, "paths")
    if "eval" not in m:
        raise _fail("paths.eval", "is required")
    ev = _path_list(m["eval"], "paths.eval")
    if not ev:
        raise _fail("paths.eval", "must not be empty")
    kw: dict[str, Any] = {"eval": ev}
    for key in ("held_out", "frozen_tests", "baseline_update"):
        if key in m:
            kw[key] = _path_list(m[key], f"paths.{key}")
    for key in ("research_dir", "audit_dir", "ledger_dir"):
        if key in m:
            kw[key] = _check_path(m[key], f"paths.{key}")
    if "design_dirs" in m:
        kw["design_dirs"] = _path_list(m["design_dirs"], "paths.design_dirs")
    return Paths(**kw)


def _parse_mcp_servers(v: Any) -> FrozenMap:
    m = _need_mapping(v, "mcp_servers")
    out = {}
    for name, spec in m.items():
        if not _is_str(name):
            raise _fail("mcp_servers", "server names must be strings")
        s = _need_mapping(spec, f"mcp_servers.{name}")
        tools = _str_list(s["read_tools"], f"mcp_servers.{name}.read_tools") if "read_tools" in s else ()
        out[name] = McpServer(read_tools=tools)
    return FrozenMap(out)


_AGENT_KEYS = ("model", "extra_skills", "mcp_servers")


def _parse_agents(v: Any, raw_servers: Any) -> FrozenMap:
    m = _need_mapping(v, "agents")
    # absent mcp_servers declares nothing; a malformed one is reported later by its own check
    declared = set(raw_servers) if isinstance(raw_servers, Mapping) else (set() if raw_servers is None else None)
    out = {}
    for role, spec in m.items():
        if not _is_str(role) or role not in ROLE_IDS:
            raise _fail(f"agents.{role}", "key must be a role id")
        base = f"agents.{role}"
        s = _need_mapping(spec, base)
        for key in s:
            if key not in _AGENT_KEYS:
                raise _fail(f"{base}.{key}", "unknown key (allowed: model, extra_skills, mcp_servers)")
        model = _need_str(s["model"], f"{base}.model", nonempty=True) if "model" in s else None
        skills = _str_list(s["extra_skills"], f"{base}.extra_skills") if "extra_skills" in s else ()
        servers = _str_list(s["mcp_servers"], f"{base}.mcp_servers") if "mcp_servers" in s else ()
        if declared is not None:
            for name in servers:
                if name not in declared:
                    raise _fail(f"{base}.mcp_servers", f"server {name!r} is not declared under mcp_servers")
        out[role] = AgentOverride(model=model, extra_skills=skills, mcp_servers=servers)
    return FrozenMap(out)


def _id_pair_list(v: Any, field: str) -> tuple[tuple[str, str], ...]:
    out = []
    for i, item in enumerate(_need_list(v, field)):
        if (not isinstance(item, list) or len(item) != 2
                or not all(_is_str(x) for x in item)):
            raise _fail(f"{field}[{i}]", "must be a list of two strings")
        out.append((item[0], item[1]))
    return tuple(out)


def _parse_graph(v: Any) -> GraphSpec:
    m = _need_mapping(v, "graph")
    if "stages" not in m:
        raise _fail("graph.stages", "is required")
    raw = _need_list(m["stages"], "graph.stages")
    if not raw:
        raise _fail("graph.stages", "must not be empty")
    stages = []
    for i, st in enumerate(raw):
        base = f"graph.stages[{i}]"
        sm = _need_mapping(st, base)
        for req in ("id", "role"):
            if req not in sm:
                raise _fail(f"{base}.{req}", "is required")
        sid = _need_str(sm["id"], f"{base}.id", nonempty=True)
        role = _need_str(sm["role"], f"{base}.role", nonempty=True)
        gate = sm.get("gate", False)
        if not isinstance(gate, bool):
            raise _fail(f"{base}.gate", "must be a boolean")
        stages.append(Stage(id=sid, role=role, gate=gate))
    edges = _id_pair_list(m["edges"], "graph.edges") if "edges" in m else ()
    loops = _id_pair_list(m["loops"], "graph.loops") if "loops" in m else ()
    subsets = {}
    if "subsets" in m:
        sm = _need_mapping(m["subsets"], "graph.subsets")
        for name, members in sm.items():
            if not _is_str(name):
                raise _fail("graph.subsets", "subset names must be strings")
            field = f"graph.subsets.{name}"
            items = _need_list(members, field)
            for j, r in enumerate(items):
                _role(r, f"{field}[{j}]")
            subsets[name] = tuple(items)
    return GraphSpec(stages=tuple(stages), edges=edges, loops=loops, subsets=FrozenMap(subsets))


def _parse_deploy(v: Any) -> Deploy:
    m = _need_mapping(v, "deploy")
    kw: dict[str, Any] = {}
    if "route" in m:
        kw["route"] = _need_str(m["route"], "deploy.route")
    if "platform_server" in m and m["platform_server"] is not None:
        kw["platform_server"] = _need_str(m["platform_server"], "deploy.platform_server")
    if "checklist" in m:
        kw["checklist"] = _check_path(m["checklist"], "deploy.checklist")
    return Deploy(**kw)


def _parse_checks(v: Any) -> Checks:
    m = _need_mapping(v, "checks")
    kw = {k: _need_str(m[k], f"checks.{k}") for k in ("test", "lint", "verify") if k in m}
    return Checks(**kw)


def _enum(v: Any, field: str, allowed: tuple[str, ...]) -> str:
    if not _is_str(v) or v not in allowed:
        raise _fail(field, f"must be one of {', '.join(allowed)}")
    return v


# ---------------------------------------------------------------- public API

def parse_profile(data: Any) -> Profile:
    """Validate a profile mapping and build an immutable :class:`Profile`."""
    if not isinstance(data, Mapping):
        raise _fail("", "profile must be a mapping at the top level")

    sv = data.get("schema_version", None)
    if "schema_version" not in data:
        raise _fail("schema_version", "is required")
    if isinstance(sv, bool) or not isinstance(sv, int) or sv != 1:
        raise _fail("schema_version", "must be the integer 1")

    if "project" not in data:
        raise _fail("project", "is required")
    project = _parse_project(data["project"])

    main_role = DEFAULT_MAIN_SESSION_ROLE
    if "main_session_role" in data:
        main_role = _role(data["main_session_role"], "main_session_role")

    if "paths" not in data:
        raise _fail("paths", "is required")
    paths = _parse_paths(data["paths"])

    agents = _parse_agents(data["agents"], data.get("mcp_servers")) if "agents" in data else FrozenMap()
    servers = _parse_mcp_servers(data["mcp_servers"]) if "mcp_servers" in data else FrozenMap()
    graph = _parse_graph(data["graph"]) if "graph" in data else None
    deploy = _parse_deploy(data["deploy"]) if "deploy" in data else None
    git_host = _enum(data["git_host"], "git_host", GIT_HOSTS) if "git_host" in data else "none"
    tracker = _enum(data["tracker"], "tracker", TRACKERS) if "tracker" in data else "none"
    checks = _parse_checks(data["checks"]) if "checks" in data else None
    otw = _regex_list(data["one_way_door_patterns"], "one_way_door_patterns") if "one_way_door_patterns" in data else ()
    allow = _regex_list(data["secret_allow_patterns"], "secret_allow_patterns") if "secret_allow_patterns" in data else ()

    for key in data:
        if key not in _TOP_LEVEL_ORDER:
            raise _fail(str(key), "unknown top-level key")

    return Profile(
        schema_version=1, project=project, paths=paths, main_session_role=main_role,
        agents=agents, mcp_servers=servers, graph=graph, deploy=deploy, git_host=git_host,
        tracker=tracker, checks=checks, one_way_door_patterns=otw, secret_allow_patterns=allow,
    )


def load_profile(path: str | Path) -> Profile:
    """Read ``path`` (YAML) and return the validated :class:`Profile`."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileError("", f"not valid YAML: {exc}") from None
    return parse_profile(data)
