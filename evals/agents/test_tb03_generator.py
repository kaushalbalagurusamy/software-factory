"""TB-03 agent file generator: golden and diagnostic cases.

Expectations come only from docs/contracts/roles-and-generation.md, docs/contracts/profile.md and
docs/prds/TB-03-agent-generator.md. The `tools` frontmatter value may be a YAML list or a comma-separated
string (not fixed by the contract; ambiguities A-10), so `tools_of()` accepts both.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from evals.agents import lib

ROLES = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]
FM_ORDER = ["name", "description", "model", "tools", "disallowedTools", "skills", "hooks"]
REVIEWERS = {"pr-review-toolkit:silent-failure-hunter", "pr-review-toolkit:pr-test-analyzer",
             "feature-dev:code-reviewer"}
GUARD_TOOLS = {"path_guard": ["Write", "Edit"], "blindness_guard": ["Read", "Grep", "Glob", "Bash"],
               "secrets_guard": ["Write", "Edit", "Bash"], "bash_guard": ["Bash"]}
SECRET_RE = re.compile(r"(sk-(ant|or)-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                       r"|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,})")
HOME_RE = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+)")


def case(cid, tier, reqs=("R-04",)):
    return pytest.mark.case(cid, tier=tier, tb="03", reqs=list(reqs))


def mods():
    prof = lib.need("factory.agents.profile", "load_profile", "ProfileError")
    roles = lib.need("factory.agents.roles", "load_roles")
    gen = lib.need("factory.agents.generate", "generate_agents", "GenerationError")
    return prof, roles, gen


def get(obj, name):
    if isinstance(obj, Mapping):
        return obj[name]
    if hasattr(obj, name):
        return getattr(obj, name)
    return obj[name]


def profile(tmp_path, data="base", sub="p"):
    prof, _, _ = mods()
    root = lib.make_project(tmp_path / sub, data)
    return prof.load_profile(root / ".factory" / "profile.yaml")


def generate(tmp_path, data="base", sub="p"):
    _, roles, gen = mods()
    return gen.generate_agents(profile(tmp_path, data, sub), roles.load_roles())


def split(text):
    assert text.startswith("---\n"), "file must open with YAML frontmatter"
    end = text.index("\n---", 4)
    fm = yaml.safe_load(text[4:end])
    body = text[end + 4:]
    return fm, body


def tools_of(fm):
    v = fm.get("tools")
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v]
    out, cur, depth = [], "", 0
    for ch in str(v):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def agent_names(tools):
    names, bare = set(), False
    for t in tools:
        if t == "Agent":
            bare = True
        elif t.startswith("Agent(") and t.endswith(")"):
            names |= {x.strip() for x in t[6:-1].split(",") if x.strip()}
    return names, bare


def hook_entries(fm):
    """List of (event, matcher, type, command) from the Claude Code hooks shape."""
    out = []
    for event, groups in (fm.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks", []) or []:
                out.append((event, g.get("matcher"), h.get("type"), h.get("command")))
    return out


def matches(matcher, tool):
    if matcher in (None, "", "*"):
        return True
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return tool in str(matcher).split("|")


def cmd(hid):
    return f"python -m factory.hooks {hid}"


def with_server(name, tools_list, override=None):
    d = lib.profile_dict("base")
    d["mcp_servers"] = {**d.get("mcp_servers", {}), name: {"read_tools": tools_list}}
    if override:
        d["agents"] = override
    return d


# ---------------------------------------------------------------- golden

@case("TB03-G-001", "golden", reqs=("R-04",))
def test_g001_seven_files_deterministic(tmp_path):
    """Behaviour 1 + contract: seven entries keyed .claude/agents/<role>.md, byte-identical across calls."""
    a = generate(tmp_path, "base", "a")
    b = generate(tmp_path, "base", "b")
    assert set(a) == {f".claude/agents/{r}.md" for r in ROLES}
    assert a == b


@case("TB03-G-002", "golden", reqs=("R-08",))
def test_g002_frontmatter_fields_and_order(tmp_path):
    """Behaviour 2 + contract: frontmatter fields only name, description, model, tools, disallowedTools,
    skills, hooks, in that order; name is the role id."""
    for path, text in generate(tmp_path).items():
        fm, _ = split(text)
        keys = list(fm)
        assert set(keys) <= set(FM_ORDER), path
        assert keys == [k for k in FM_ORDER if k in keys], path
        assert {"name", "description", "model", "tools"} <= set(keys), path
        assert fm["name"] == Path(path).stem


@case("TB03-G-003", "golden", reqs=("R-05",))
def test_g003_tools_are_core_tools_without_servers(tmp_path):
    """Behaviour 3: tools = core_tools, then per mcp entry only servers the profile provides. Implement has
    no mcp entries and no override in base, so its tools equal core_tools in order."""
    _, roles, _ = mods()
    spec = roles.load_roles()["implement"]
    fm, _ = split(generate(tmp_path)[".claude/agents/implement.md"])
    assert tools_of(fm) == [str(t) for t in get(spec, "core_tools")]


@case("TB03-G-004", "golden", reqs=("R-05",))
def test_g004_override_adds_declared_server_read_tools(tmp_path):
    """Behaviour 3 + 4: an override adding a profile-declared server lists its read_tools as
    mcp__<server>__<tool> after the core tools, and never the whole-server mcp__<server>."""
    _, roles, gen = mods()
    d = lib.profile_dict("base")
    d["agents"] = {"implement": {"mcp_servers": ["docsrv"]}}
    out = gen.generate_agents(profile(tmp_path, d), roles.load_roles())
    tools = tools_of(split(out[".claude/agents/implement.md"])[0])
    assert tools[-2:] == ["mcp__docsrv__search", "mcp__docsrv__fetch"]
    assert "mcp__docsrv" not in tools


@case("TB03-G-005", "golden", reqs=("R-05",))
def test_g005_too_many_tools_raises(tmp_path):
    """Behaviour 5: a tool list longer than max_tools raises GenerationError."""
    _, roles, gen = mods()
    d = with_server("bigsrv", [f"t{i}" for i in range(25)], {"research": {"mcp_servers": ["bigsrv"]}})
    p = profile(tmp_path, d)
    with pytest.raises(gen.GenerationError):
        gen.generate_agents(p, roles.load_roles())


@case("TB03-G-006", "golden", reqs=("R-04",))
def test_g006_implement_hooks_rendered(tmp_path):
    """Behaviour 6: hooks render as `python -m factory.hooks <id>`: blindness_guard under PreToolUse and
    stop_gate under Stop for implement."""
    entries = hook_entries(split(generate(tmp_path)[".claude/agents/implement.md"])[0])
    assert ("PreToolUse", cmd("blindness_guard")) in {(e, c) for e, _, _, c in entries}
    assert ("Stop", cmd("stop_gate")) in {(e, c) for e, _, _, c in entries}


@case("TB03-G-007", "golden", reqs=("R-01",))
def test_g007_project_name_does_not_leak(tmp_path):
    """Behaviour 7: two profiles with no MCP servers, differing only in project.name, give identical files."""
    a = lib.profile_dict("base")
    a.pop("mcp_servers", None)
    b = lib.profile_dict("base")
    b.pop("mcp_servers", None)
    b["project"] = {"name": "zeta-unrelated"}
    assert generate(tmp_path, a, "a") == generate(tmp_path, b, "b")


@case("TB03-G-008", "golden", reqs=("R-06",))
def test_g008_orchestrator_review_no_write_edit(tmp_path):
    """R-06: in the generated files, orchestrator and review have neither Write nor Edit."""
    out = generate(tmp_path)
    for r in ["orchestrator", "review"]:
        assert not {"Write", "Edit"} & set(tools_of(split(out[f".claude/agents/{r}.md"])[0])), r


# ---------------------------------------------------------------- diagnostic

@case("TB03-D-001", "diagnostic", reqs=("R-08",))
def test_d001_optional_fields_omitted_when_empty(tmp_path):
    """Behaviour 2: disallowedTools, skills and hooks are omitted when empty and present when not."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        fm, _ = split(out[f".claude/agents/{r}.md"])
        for key, field in [("disallowedTools", "disallowed_tools"), ("skills", "skills"), ("hooks", "hooks")]:
            assert (key in fm) == bool(list(get(rs[r], field))), (r, key)
            if key in fm:
                assert fm[key], (r, key)


@case("TB03-D-002", "diagnostic")
def test_d002_model_from_spec(tmp_path):
    """Contract: model comes from the role spec unless the profile overrides it."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        assert split(out[f".claude/agents/{r}.md"])[0]["model"] == get(rs[r], "model"), r


@case("TB03-D-003", "diagnostic")
def test_d003_model_override_only_that_role(tmp_path):
    """Behaviour 4: a profile override may change the model; other roles keep theirs."""
    d = lib.profile_dict("base")
    d["agents"] = {"research": {"model": "override-model-x"}}
    plain = generate(tmp_path, "base", "a")
    over = generate(tmp_path, d, "b")
    assert split(over[".claude/agents/research.md"])[0]["model"] == "override-model-x"
    for r in ROLES:
        if r != "research":
            assert over[f".claude/agents/{r}.md"] == plain[f".claude/agents/{r}.md"], r


@case("TB03-D-004", "diagnostic")
def test_d004_extra_skills_added(tmp_path):
    """Behaviour 4 + 8: override extra_skills are added to skills, and the body mentions each skill by name."""
    d = lib.profile_dict("base")
    d["agents"] = {"design": {"extra_skills": ["extra-skill-q"]}}
    fm, body = split(generate(tmp_path, d)[".claude/agents/design.md"])
    assert "extra-skill-q" in [str(s) for s in fm["skills"]]
    assert "extra-skill-q" in body


@case("TB03-D-005", "diagnostic", reqs=("R-05",))
def test_d005_absent_server_silently_omitted(tmp_path):
    """Behaviour 3 + contract: a server the profile does not provide contributes nothing (and no error)."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    d = lib.profile_dict("base")
    d.pop("mcp_servers", None)
    out = generate(tmp_path, d)
    for r in ROLES:
        tools = tools_of(split(out[f".claude/agents/{r}.md"])[0])
        for e in get(rs[r], "mcp"):
            s = get(e, "server")
            assert not any(t == f"mcp__{s}" or t.startswith(f"mcp__{s}__") for t in tools), (r, s)


@case("TB03-D-006", "diagnostic", reqs=("R-05",))
def test_d006_role_server_provided_by_profile(tmp_path):
    """Behaviour 3: for a role's own read mcp entry whose server the profile provides, the server's read_tools
    are listed as mcp__<server>__<tool>, after the core tools."""
    _, roles, gen = mods()
    rs = roles.load_roles()
    picked = [(r, get(e, "server")) for r in ROLES for e in get(rs[r], "mcp") if get(e, "access") == "read"]
    assert picked, "capability map section 3 gives Research read MCP servers"
    role, server = picked[0]
    d = lib.profile_dict("base")
    d["mcp_servers"] = {server: {"read_tools": ["alpha_tool"]}}
    out = gen.generate_agents(profile(tmp_path, d), rs)
    tools = tools_of(split(out[f".claude/agents/{role}.md"])[0])
    core = [str(t) for t in get(rs[role], "core_tools")]
    assert tools[:len(core)] == core
    assert f"mcp__{server}__alpha_tool" in tools[len(core):]
    assert f"mcp__{server}" not in tools


@case("TB03-D-007", "diagnostic", reqs=("R-05",))
def test_d007_no_whole_server_for_read_access(tmp_path):
    """R-05: only read tools of a server are listed unless the role is allowed writes; no role (all read access)
    gets a whole-server mcp__<server> entry, even when every server is provided."""
    _, roles, gen = mods()
    rs = roles.load_roles()
    servers = {get(e, "server") for r in ROLES for e in get(rs[r], "mcp")}
    d = lib.profile_dict("base")
    if servers:
        d["mcp_servers"] = {s: {"read_tools": ["one"]} for s in servers}
    out = gen.generate_agents(profile(tmp_path, d), rs)
    for r in ROLES:
        tools = tools_of(split(out[f".claude/agents/{r}.md"])[0])
        for e in get(rs[r], "mcp"):
            if get(e, "access") == "read":
                assert f"mcp__{get(e, 'server')}" not in tools, (r, e)


@case("TB03-D-008", "diagnostic", reqs=("R-05",))
def test_d008_exactly_max_tools_accepted(tmp_path):
    """Behaviour 5 boundary: a tool list of exactly max_tools is accepted; one more raises GenerationError."""
    _, roles, gen = mods()
    rs = roles.load_roles()
    spec = rs["implement"]
    room = get(spec, "max_tools") - len(list(get(spec, "core_tools")))
    if room > 0:
        d = with_server("fitsrv", [f"f{i}" for i in range(room)], {"implement": {"mcp_servers": ["fitsrv"]}})
        out = gen.generate_agents(profile(tmp_path, d, "fit"), rs)
        assert len(tools_of(split(out[".claude/agents/implement.md"])[0])) == get(spec, "max_tools")
    d = with_server("oversrv", [f"o{i}" for i in range(room + 1)], {"implement": {"mcp_servers": ["oversrv"]}})
    with pytest.raises(gen.GenerationError):
        gen.generate_agents(profile(tmp_path, d, "over"), rs)


@case("TB03-D-009", "diagnostic", reqs=("R-06",))
def test_d009_writes_override_rejected(tmp_path):
    """Behaviour 4: a profile request that would change `writes` is rejected (GenerationError; a loader that
    rejects the key first with ProfileError also satisfies 'rejected', see ambiguities A-11)."""
    prof, roles, gen = mods()
    d = lib.profile_dict("base")
    d["agents"] = {"review": {"writes": "app"}}
    root = lib.make_project(tmp_path, d)
    with pytest.raises((gen.GenerationError, prof.ProfileError)):
        gen.generate_agents(prof.load_profile(root / ".factory" / "profile.yaml"), roles.load_roles())


@case("TB03-D-010", "diagnostic", reqs=("R-01",))
def test_d010_project_name_in_template_raises(tmp_path):
    """Behaviour 7 + contract: a profile whose project.name appears inside a role template body raises
    GenerationError. The review body must mention its skill implementation-review (behaviour 8), so a project
    named that collides."""
    _, roles, gen = mods()
    d = lib.profile_dict("base")
    d["project"] = {"name": "implementation-review"}
    p = profile(tmp_path, d)
    with pytest.raises(gen.GenerationError):
        gen.generate_agents(p, roles.load_roles())


@case("TB03-D-011", "diagnostic", reqs=("R-04",))
def test_d011_guard_hooks_pretooluse_matchers(tmp_path):
    """Behaviour 6: guards render under PreToolUse with a matcher covering the tools they inspect (path_guard
    Write/Edit; blindness_guard Read/Grep/Glob/Bash; secrets_guard Write/Edit/Bash; bash_guard Bash)."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        entries = hook_entries(split(out[f".claude/agents/{r}.md"])[0])
        for hid in set(get(rs[r], "hooks")) & set(GUARD_TOOLS):
            ms = [m for e, m, _, c in entries if e == "PreToolUse" and c == cmd(hid)]
            assert ms, (r, hid)
            for tool in GUARD_TOOLS[hid]:
                assert any(matches(m, tool) for m in ms), (r, hid, tool)


@case("TB03-D-012", "diagnostic", reqs=("R-04",))
def test_d012_subagent_stop_event(tmp_path):
    """Behaviour 6: subagent_stop renders under SubagentStop for each role that lists it."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        if "subagent_stop" in set(get(rs[r], "hooks")):
            entries = hook_entries(split(out[f".claude/agents/{r}.md"])[0])
            assert ("SubagentStop", cmd("subagent_stop")) in {(e, c) for e, _, _, c in entries}, r


@case("TB03-D-013", "diagnostic", reqs=("R-04",))
def test_d013_session_start_event(tmp_path):
    """Behaviour 6: session_start renders under SessionStart (orchestrator lists it)."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        if "session_start" in set(get(rs[r], "hooks")):
            entries = hook_entries(split(out[f".claude/agents/{r}.md"])[0])
            assert ("SessionStart", cmd("session_start")) in {(e, c) for e, _, _, c in entries}, r


@case("TB03-D-014", "diagnostic", reqs=("R-04",))
def test_d014_hook_commands_match_spec(tmp_path):
    """Contract hook shape: every entry is {type: command, command: 'python -m factory.hooks <hook_id>'}, and
    the set of hook ids rendered for a role equals the role spec's hooks."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        entries = hook_entries(split(out[f".claude/agents/{r}.md"])[0])
        assert all(t == "command" for _, _, t, _ in entries), r
        assert all(c.startswith("python -m factory.hooks ") for _, _, _, c in entries), r
        ids = {c.split()[-1] for _, _, _, c in entries}
        assert ids == set(get(rs[r], "hooks")), r


@case("TB03-D-015", "diagnostic", reqs=("R-04",))
def test_d015_body_mentions_every_skill(tmp_path):
    """Behaviour 8: the body mentions each skill the role loads by name."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        _, body = split(out[f".claude/agents/{r}.md"])
        for s in get(rs[r], "skills"):
            assert str(s) in body, (r, s)


@case("TB03-D-016", "diagnostic", reqs=("R-04",))
def test_d016_skills_field_carries_spec_skills(tmp_path):
    """Contract: the skills frontmatter carries the role's skills."""
    _, roles, _ = mods()
    rs = roles.load_roles()
    out = generate(tmp_path)
    for r in ROLES:
        fm, _ = split(out[f".claude/agents/{r}.md"])
        assert {str(s) for s in get(rs[r], "skills")} <= {str(s) for s in fm.get("skills") or []}, r


@pytest.mark.parametrize("fixture", [
    pytest.param("base", marks=case("TB03-D-017", "diagnostic", reqs=("R-01", "R-23")), id="base"),
    pytest.param("alt", marks=case("TB03-D-018", "diagnostic", reqs=("R-01", "R-23")), id="alt"),
])
def test_d017_no_secret_or_home_path(tmp_path, fixture):
    """Behaviour 9: no generated file contains a secret-shaped value or an absolute home path."""
    home = str(Path.home())
    for path, text in generate(tmp_path, fixture).items():
        assert not SECRET_RE.search(text), path
        assert not HOME_RE.search(text), path
        assert home not in text, path


@case("TB03-D-019", "diagnostic", reqs=("R-01",))
def test_d019_generality_no_cross_profile_values(tmp_path):
    """R-01 generality: outputs change only through the profile. Files generated from base contain no value
    that only alt supplies, and vice versa."""
    base_out = "\n".join(generate(tmp_path, "base", "a").values())
    alt_out = "\n".join(generate(tmp_path, "alt", "b").values())
    for v in ["fixture-beta", "qa/cases", "qa/secret", "notes/research", "notes/audit", "cloudctl",
              "db-reset", "FIXTURE-KEY"]:
        assert v not in base_out, v
    for v in ["fixture-alpha", "tests/held_out", "deployctl", "docsrv"]:
        assert v not in alt_out, v


@case("TB03-D-020", "diagnostic", reqs=("R-01",))
def test_d020_independent_of_project_location(tmp_path):
    """Contract determinism: the same profile content in two different project roots gives identical output."""
    assert generate(tmp_path / "x", "alt", "one") == generate(tmp_path / "y", "alt", "two")


@case("TB03-D-021", "diagnostic", reqs=("R-07",))
def test_d021_spawn_allowlists_in_tools(tmp_path):
    """R-07: orchestrator may start only the other six roles; implement may start none; review only the three
    reviewer agents. No unrestricted bare Agent entry for these roles."""
    out = generate(tmp_path)
    t = {r: tools_of(split(out[f".claude/agents/{r}.md"])[0]) for r in ROLES}
    names, bare = agent_names(t["orchestrator"])
    assert not bare and names <= set(ROLES) - {"orchestrator"}
    names, bare = agent_names(t["review"])
    assert not bare and names <= REVIEWERS
    assert agent_names(t["implement"]) == (set(), False)


@case("TB03-D-022", "diagnostic", reqs=("R-05",))
def test_d022_at_most_20_tools(tmp_path):
    """R-05: a generated agent lists at most 20 tools (both fixtures)."""
    for fx in ["base", "alt"]:
        for path, text in generate(tmp_path, fx, fx).items():
            assert len(tools_of(split(text)[0])) <= 20, (fx, path)


@case("TB03-D-023", "diagnostic", reqs=("R-06",))
def test_d023_implement_has_write_edit(tmp_path):
    """R-06: implement is the application writer and has Write and Edit."""
    assert {"Write", "Edit"} <= set(tools_of(split(generate(tmp_path)[".claude/agents/implement.md"])[0]))


@case("TB03-D-024", "diagnostic")
def test_d024_deterministic_with_reloaded_roles(tmp_path):
    """Contract: same inputs give byte-identical output (roles loaded twice, profile loaded twice)."""
    _, roles, gen = mods()
    p1 = profile(tmp_path, "base", "a")
    p2 = profile(tmp_path, "base", "b")
    assert gen.generate_agents(p1, roles.load_roles()) == gen.generate_agents(p2, roles.load_roles())


@case("TB03-D-025", "diagnostic")
def test_d025_values_are_text(tmp_path):
    """Contract: generate_agents returns dict[str, str] of project-relative paths to file text."""
    out = generate(tmp_path)
    for k, v in out.items():
        assert isinstance(k, str) and isinstance(v, str)
        assert not k.startswith("/") and ".." not in k


@case("TB03-D-026", "diagnostic", reqs=("R-05",))
def test_d026_override_server_limited_to_that_role(tmp_path):
    """Behaviour 4: an override adding a server to one role does not add it to any other role."""
    d = lib.profile_dict("base")
    d["agents"] = {"test": {"mcp_servers": ["docsrv"]}}
    out = generate(tmp_path, d)
    for r in ROLES:
        tools = tools_of(split(out[f".claude/agents/{r}.md"])[0])
        has = any(t.startswith("mcp__docsrv") for t in tools)
        assert has == (r == "test"), r
