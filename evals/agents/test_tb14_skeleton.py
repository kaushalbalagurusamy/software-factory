"""TB-14: End-to-end walking skeleton and shadow routing log (R-19, R-20, R-01).

Expectations come only from docs/prds/TB-14-walking-skeleton.md, the requirements it cites and the published
contracts. The input/output shape of `simulate.run_events` is not published (coverage/ambiguities-C.md, C-26), so
the scripted event stream is driven through the published seams instead: the profile loader, `generate_agents`,
`emit_settings` (TB-13), and the hook command line `python -m factory.hooks <id>` for every hook the emitted
settings register for the event and tool, combined by the PRD b1 rule (any deny or block wins, else any ask, else
allow). Every case also requires `factory.agents.simulate.run_events` to exist, so all resolve to blocked until the
TB-14 slice lands.

Shadow results are duck-typed objects carrying the attributes `factory.routing.jev_client.log_record` reads.
"""
from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.agents import lib

HOOK_IDS = {"path_guard", "blindness_guard", "secrets_guard", "bash_guard", "stop_gate", "subagent_stop",
            "ledger_audit", "session_start"}
ROLES = ["orchestrator", "research", "design", "audit", "implement", "test", "review"]
LOG_FIELDS = ["decision", "state_digest", "policy_version", "source", "band", "choice", "action", "top_prob",
              "margin", "probabilities", "fault", "latency_ms"]
CMD_RE = re.compile(r"factory\.hooks\s+([a-z_]+)")
FILES = {"evals/cases/c1.yaml": "case: 1\n", "qa/cases/c1.yaml": "case: 1\n", "qa/secret/h1.yaml": "h: 1\n",
         "src/app.py": "X = 1\n", "README.md": "fixture\n"}
KEY = "ghp" + "_" + "Ab3Xy9" * 6            # built at runtime: no secret-shaped literal in the repo (R-23)
FIXTURE_ASSIGN = 'export API_TOKEN="FIXTURE-KEY-12345678901"'


def case(cid: str, tier: str = "diagnostic", reqs=None):
    return pytest.mark.case(cid, tier=tier, tb="14", reqs=reqs or ["R-20"])


def base_no_mcp() -> dict:
    """PRD b2: 'a small profile ... no MCP servers' - the base fixture profile with `mcp_servers` removed."""
    data = lib.profile_dict("base")
    data.pop("mcp_servers", None)
    return data


# ---------------------------------------------------------------- pipeline

def need_pipeline():
    lib.need("factory.agents.simulate", "run_events")
    prof = lib.need("factory.agents.profile", "load_profile")
    roles = lib.need("factory.agents.roles", "load_roles")
    gen = lib.need("factory.agents.generate", "generate_agents")
    st = lib.need("factory.agents.settings", "emit_settings")
    lib.need("factory.hooks.core", "run_hook", "parse_payload", "HookConfig")
    lib.need("factory.hooks.registry")
    return prof, roles, gen, st


def stack(tmp_path: Path, profile="base"):
    prof, roles, gen, st = need_pipeline()
    root = lib.make_project(tmp_path, base_no_mcp() if profile == "base" else profile, files=FILES)
    p = prof.load_profile(root / ".factory" / "profile.yaml")
    rs = roles.load_roles()
    return root, gen.generate_agents(p, rs), st.emit_settings(p, rs)


def registered(settings: dict, event: str, tool: str | None) -> list[str]:
    """Hook ids the settings register for an event and tool (Claude Code matcher: empty/'*'/absent matches all,
    otherwise a regex matched against the tool name; matchers apply to tool events only)."""
    ids: list[str] = []
    for group in (settings.get("hooks") or {}).get(event, []):
        m = group.get("matcher")
        if event in ("PreToolUse", "PostToolUse") and m not in (None, "", "*"):
            if not re.fullmatch(m, tool or ""):
                continue
        for h in group.get("hooks", []):
            mm = CMD_RE.search(h.get("command", ""))
            if mm and mm.group(1) not in ids:
                ids.append(mm.group(1))
    return ids


def outcome(proc) -> str:
    """hook-io adapter table, read back: exit 2 deny; exit 0 + decision block; exit 0 + permissionDecision ask;
    exit 0 + empty stdout allow."""
    if proc.returncode == 2:
        return "deny"
    assert proc.returncode == 0, f"illegal exit {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    if not out:
        return "allow"
    data = json.loads(out)
    if data.get("decision") == "block":
        return "block"
    if (data.get("hookSpecificOutput") or {}).get("permissionDecision") == "ask":
        return "ask"
    raise AssertionError(f"unrecognised hook output: {out}")


def combine(kinds) -> str:
    """PRD b1: 'any deny or block wins, else any ask, else allow'."""
    kinds = list(kinds)
    for k in ("deny", "block"):
        if k in kinds:
            return k
    return "ask" if "ask" in kinds else "allow"


def run_event(root: Path, settings: dict, pl: dict, env: dict | None = None) -> str:
    ids = registered(settings, pl["hook_event_name"], pl.get("tool_name"))
    assert ids, f"no hook registered for {pl['hook_event_name']} {pl.get('tool_name')}"
    for i in ids:
        lib.need(f"factory.hooks.{i}", "decide")
    return combine(outcome(lib.run_cli(i, pl, root, env=env)) for i in ids)


def run_event_inprocess(root: Path, settings: dict, pl: dict) -> str:
    ids = registered(settings, pl["hook_event_name"], pl.get("tool_name"))
    assert ids
    return combine(lib.run_decide(f"factory.hooks.{i}", pl, root).kind for i in ids)


# ---------------------------------------------------------------- payloads

def read(root, agent, rel):
    return lib.payload(root, tool_name="Read", tool_input={"file_path": str(root / rel)}, agent_type=agent)


def write(root, agent, rel, content="X = 2\n"):
    return lib.payload(root, tool_name="Write", tool_input={"file_path": str(root / rel), "content": content},
                       agent_type=agent)


def bash(root, agent, command):
    return lib.payload(root, tool_name="Bash", tool_input={"command": command}, agent_type=agent)


def research_stop(root, message):
    return lib.payload(root, event="SubagentStop", agent_type="research", agent_id="r-1",
                       agent_transcript_path=str(root.parent / "t.jsonl"), last_assistant_message=message,
                       stop_hook_active=False)


NO_SOURCES = "Batching is supported by the upstream API and it is fast.\n"
WITH_SOURCES = "Batching is supported.\n\n## Sources\n- https://docs.example.org/api/batching\n"


def script(root):
    """The PRD b2 scripted stream, with the expected outcome for each event."""
    return [
        (read(root, "implement", "evals/cases/c1.yaml"), "deny"),
        (read(root, "test", "evals/cases/c1.yaml"), "allow"),
        (write(root, "review", "src/app.py"), "deny"),
        (bash(root, "implement", f"echo {KEY}"), "deny"),
        (bash(root, "orchestrator", "git push --force origin main"), "ask"),
        (research_stop(root, NO_SOURCES), "block"),
    ]


# ---------------------------------------------------------------- golden: PRD b2 on the base fixture

@case("TB14-G-001", "golden", ["R-20", "R-01"])
def test_g001_agents_and_settings_from_profile(tmp_path):
    """PRD b2: 'the generated agents and settings are produced from the profile alone' - seven
    `.claude/agents/<role>.md` files, and settings whose hooks are `python -m factory.hooks <id>` for contract ids,
    with the implement blindness guard on Read and the sub-agent validator on SubagentStop."""
    root, agents, settings = stack(tmp_path)
    assert set(agents) == {f".claude/agents/{r}.md" for r in ROLES}
    assert "blindness_guard" in registered(settings, "PreToolUse", "Read")
    assert "subagent_stop" in registered(settings, "SubagentStop", None)


@case("TB14-G-002", "golden")
def test_g002_implement_read_of_eval_denied(tmp_path):
    """PRD b2: 'an `implement` read of an eval file is denied'."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, read(root, "implement", "evals/cases/c1.yaml")) == "deny"


@case("TB14-G-003", "golden")
def test_g003_test_read_of_eval_allowed(tmp_path):
    """PRD b2: 'a `test` read of it is allowed' (negative control)."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, read(root, "test", "evals/cases/c1.yaml")) == "allow"


@case("TB14-G-004", "golden")
def test_g004_review_write_denied(tmp_path):
    """PRD b2: 'a `review` Write is denied'."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, write(root, "review", "src/app.py")) == "deny"


@case("TB14-G-005", "golden")
def test_g005_secret_bash_denied(tmp_path):
    """PRD b2: 'a secret-shaped Bash command is denied'."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, bash(root, "implement", f"echo {KEY}")) == "deny"


@case("TB14-G-006", "golden")
def test_g006_orchestrator_force_push_asks(tmp_path):
    """PRD b2: 'an `orchestrator` `git push --force` asks'."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, bash(root, "orchestrator", "git push --force origin main")) == "ask"


@case("TB14-G-007", "golden")
def test_g007_research_without_sources_blocked(tmp_path):
    """PRD b2: 'a research report without sources is blocked at stop'."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, research_stop(root, NO_SOURCES)) == "block"


@case("TB14-G-008", "golden")
def test_g008_whole_stream(tmp_path):
    """PRD b2 / R-20: the scripted event stream as a whole is decided exactly as the requirements say."""
    root, _, settings = stack(tmp_path)
    events = script(root)
    assert [run_event(root, settings, pl) for pl, _ in events] == [want for _, want in events]


@case("TB14-G-009", "golden", ["R-19"])
def test_g009_shadow_record_appends_one_line(tmp_path):
    """PRD b4: `shadow.record(result, actual_choice, ledger_dir) -> None` appends one JSON line to
    `<ledger_dir>/routing.jsonl` with the `log_record` fields plus `actual_choice` and `agrees` (bool)."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    assert sh.record(routing(), "route-a", led) is None
    lines = (led / "routing.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert set(LOG_FIELDS) <= set(rec)
    assert rec["actual_choice"] == "route-a" and isinstance(rec["agrees"], bool)


# ---------------------------------------------------------------- diagnostic: PRD b3, profile alone changes outcomes

ALT_CASES = [
    # (id, profile, payload builder, expected, clause)
    ("TB14-D-001", "alt", lambda r: read(r, "implement", "qa/cases/c1.yaml"), "deny", "alt eval path qa/cases/** is protected"),
    ("TB14-D-002", "alt", lambda r: read(r, "implement", "evals/cases/c1.yaml"), "allow", "evals/** is not an eval path under alt"),
    ("TB14-D-003", "base", lambda r: read(r, "implement", "qa/cases/c1.yaml"), "allow", "qa/cases/** is not an eval path under base"),
    ("TB14-D-004", "alt", lambda r: bash(r, "orchestrator", "db-reset --all"), "ask", "alt one-way-door pattern db-reset"),
    ("TB14-D-005", "base", lambda r: bash(r, "orchestrator", "db-reset --all"), "allow", "db-reset is not a base one-way door"),
    ("TB14-D-006", "base", lambda r: bash(r, "orchestrator", "migrate --drop users"), "ask", "base one-way-door pattern migrate --drop"),
    ("TB14-D-007", "alt", lambda r: bash(r, "orchestrator", "migrate --drop users"), "allow", "migrate --drop is not an alt one-way door"),
    ("TB14-D-008", "alt", lambda r: bash(r, "orchestrator", "cloudctl release v2"), "ask", "alt deploy route"),
    ("TB14-D-009", "alt", lambda r: bash(r, "orchestrator", "deployctl push v2"), "allow", "base deploy route is not a door under alt"),
    ("TB14-D-010", "base", lambda r: bash(r, "orchestrator", "deployctl push v2"), "ask", "base deploy route"),
    ("TB14-D-011", "base", lambda r: bash(r, "implement", FIXTURE_ASSIGN), "deny", "quoted 16+ char value assigned to a token name"),
    ("TB14-D-012", "alt", lambda r: bash(r, "implement", FIXTURE_ASSIGN), "allow", "alt secret_allow_patterns FIXTURE-KEY-[0-9]+"),
    ("TB14-D-013", "alt", lambda r: write(r, "test", "qa/cases/c2.yaml", "case: 2\n"), "allow", "test writes the alt eval path before the freeze"),
    ("TB14-D-014", "base", lambda r: write(r, "test", "qa/cases/c2.yaml", "case: 2\n"), "deny", "qa/cases is outside the base eval path"),
    ("TB14-D-015", "alt", lambda r: read(r, "implement", "qa/secret/h1.yaml"), "deny", "alt held_out qa/secret/** is protected"),
]


@pytest.mark.parametrize("profile,build,want,clause", [
    pytest.param(p, b, w, c, marks=case(i, reqs=["R-20", "R-01"]), id=i) for i, p, b, w, c in ALT_CASES])
def test_d_profile_changes_outcomes(tmp_path, profile, build, want, clause):
    """PRD b3: 'Changing only the profile (a second fixture with different eval paths and a different one-way-door
    pattern) changes the outcomes accordingly'. Each row pairs a base/alt outcome that follows from the profile
    values (eval, held_out, one_way_door_patterns, deploy.route, secret_allow_patterns) and the guard PRDs."""
    root, _, settings = stack(tmp_path, profile)
    assert run_event(root, settings, build(root)) == want, clause


@case("TB14-D-016", reqs=["R-20", "R-01"])
def test_d016_same_hooks_registered_for_both_profiles(tmp_path):
    """PRD b3: 'role and hook code paths are the same' - for every event and tool in the stream, base and alt
    register the same hook ids."""
    rb, _, sb = stack(tmp_path / "b")
    ra, _, sa = stack(tmp_path / "a", "alt")
    for event, tool in [("PreToolUse", "Read"), ("PreToolUse", "Write"), ("PreToolUse", "Bash"),
                        ("SubagentStop", None)]:
        assert sorted(registered(sb, event, tool)) == sorted(registered(sa, event, tool)), (event, tool)


# ---------------------------------------------------------------- diagnostic: more of the stream (b2)

@case("TB14-D-017")
def test_d017_main_session_force_push_asks(tmp_path):
    """PRD b2 + hook-io: a payload with no `agent_type` is the main session, mapped to `orchestrator` by default,
    so its `git push --force` asks."""
    root, _, settings = stack(tmp_path)
    pl = lib.payload(root, tool_name="Bash", tool_input={"command": "git push --force origin main"})
    assert run_event(root, settings, pl) == "ask"


@case("TB14-D-018")
def test_d018_implement_cat_of_eval_denied(tmp_path):
    """R-11 in the stream: implement's `cat evals/cases/c1.yaml` is denied."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, bash(root, "implement", "cat evals/cases/c1.yaml")) == "deny"


@case("TB14-D-019")
def test_d019_research_with_sources_allowed(tmp_path):
    """Negative control for PRD b2: a research report with a Sources section is not blocked at stop."""
    root, _, settings = stack(tmp_path)
    assert run_event(root, settings, research_stop(root, WITH_SOURCES)) == "allow"


@case("TB14-D-020", reqs=["R-01", "R-20"])
def test_d020_agents_deterministic_and_project_free(tmp_path):
    """R-01 + roles contract: generation is deterministic and no generated agent file names the project
    (`fixture-alpha`); project facts come from the profile only."""
    prof, roles, gen, _ = need_pipeline()
    root = lib.make_project(tmp_path, base_no_mcp(), files=FILES)
    p = prof.load_profile(root / ".factory" / "profile.yaml")
    a1, a2 = gen.generate_agents(p, roles.load_roles()), gen.generate_agents(p, roles.load_roles())
    assert a1 == a2
    assert all("fixture-alpha" not in text for text in a1.values())


@case("TB14-D-021")
def test_d021_settings_only_contract_hooks(tmp_path):
    """hook-io command line + TB-13 b1: every registered command is `python -m factory.hooks <id>` for an id in the
    contract's list."""
    _, _, settings = stack(tmp_path)
    commands = [h.get("command", "") for groups in (settings.get("hooks") or {}).values() for g in groups
                for h in g.get("hooks", [])]
    assert commands
    for c in commands:
        m = CMD_RE.search(c)
        assert m and m.group(1) in HOOK_IDS and c.strip().startswith("python -m factory.hooks"), c


# ---------------------------------------------------------------- diagnostic: b5 no network, no model call

SITECUSTOMIZE = '''
import os, socket
_marker = os.environ.get("NO_NET_MARKER")
def _deny(*a, **k):
    if _marker:
        with open(_marker, "a") as fh:
            fh.write("network attempt\\n")
    raise OSError("network disabled in eval")
socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny
'''


@case("TB14-D-022", reqs=["R-20", "R-09"])
def test_d022_stream_with_network_disabled_subprocess(tmp_path):
    """PRD b5: 'The whole simulation runs with the network disabled and makes no model call.' Every hook process
    runs with sockets patched to fail (sitecustomize); outcomes are unchanged and no connection is attempted."""
    root, _, settings = stack(tmp_path)
    sc = tmp_path / "nonet"
    sc.mkdir()
    (sc / "sitecustomize.py").write_text(SITECUSTOMIZE)
    marker = tmp_path / "net_attempts.txt"
    env = {"PYTHONPATH": f"{sc}{os.pathsep}{lib.REPO}", "NO_NET_MARKER": str(marker)}
    events = script(root)
    assert [run_event(root, settings, pl, env=env) for pl, _ in events] == [w for _, w in events]
    assert not marker.exists()


@pytest.fixture
def no_network(monkeypatch):
    attempts = []

    def deny(*a, **k):
        attempts.append(a)
        raise OSError("network disabled in eval")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    return attempts


@case("TB14-D-023", reqs=["R-20", "R-09"])
def test_d023_pipeline_in_process_without_network(tmp_path, no_network):
    """PRD b5: generation, settings and every hook decision of the stream run in process with sockets disabled,
    give the scripted outcomes, and attempt no connection."""
    root, _, settings = stack(tmp_path)
    events = script(root)
    assert [run_event_inprocess(root, settings, pl) for pl, _ in events] == [w for _, w in events]
    assert no_network == []


@case("TB14-D-024", reqs=["R-19", "R-20"])
def test_d024_shadow_without_network(tmp_path, no_network):
    """PRD b4 + b5: the shadow log is written with the network disabled and attempts no connection."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    sh.record(routing(), "route-a", led)
    assert (led / "routing.jsonl").read_text().strip()
    assert no_network == []


# ---------------------------------------------------------------- diagnostic: b4 shadow routing log

def shadow():
    lib.need("factory.agents.simulate", "run_events")
    return lib.need("factory.routing.shadow", "record")


def routing(choice: str = "route-a", **extra):
    """Duck-typed routing result with every attribute `log_record` reads; decision, choice and action all carry the
    same value so `agrees` is unambiguous whichever of them is compared."""
    base = dict(decision=choice, policy_version="policy-1", source="model", band="high", choice=choice,
                action=choice, top_prob=0.9, margin=0.5, probabilities={"route-a": 0.9, "route-b": 0.1},
                fault=None, latency_ms=12, state_digest="digest-abc")
    base.update(extra)
    return SimpleNamespace(**base)


def lines(led: Path) -> list[dict]:
    return [json.loads(x) for x in (led / "routing.jsonl").read_text().splitlines() if x.strip()]


@case("TB14-D-025", reqs=["R-19"])
def test_d025_one_line_per_call(tmp_path):
    """PRD b4: each call 'appends one JSON line'."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    sh.record(routing(), "route-a", led)
    sh.record(routing(), "route-b", led)
    assert len(lines(led)) == 2


@case("TB14-D-026", reqs=["R-19"])
def test_d026_agrees_true(tmp_path):
    """PRD b4: `agrees` (bool) is true when the actual choice matches the routing result."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    sh.record(routing("route-a"), "route-a", led)
    assert lines(led)[0]["agrees"] is True


@case("TB14-D-027", reqs=["R-19"])
def test_d027_agrees_false(tmp_path):
    """PRD b4: `agrees` is false when the actual choice differs from the routing result."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    sh.record(routing("route-a"), "route-b", led)
    rec = lines(led)[0]
    assert rec["agrees"] is False and rec["actual_choice"] == "route-b"


@case("TB14-D-028", reqs=["R-19"])
def test_d028_never_raises_on_none_result(tmp_path):
    """PRD b4: record 'never raises into the caller' - a None result returns None without an exception."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    assert sh.record(None, "route-a", led) is None


@case("TB14-D-029", reqs=["R-19"])
def test_d029_never_raises_on_incomplete_result(tmp_path):
    """PRD b4: never raises - a result object missing every expected attribute."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    assert sh.record(object(), "route-a", led) is None


@case("TB14-D-030", reqs=["R-19"])
def test_d030_never_raises_when_ledger_dir_is_a_file(tmp_path):
    """PRD b4: never raises - `ledger_dir` names an existing regular file, so the log cannot be written."""
    sh = shadow()
    bad = tmp_path / "not_a_dir"
    bad.write_text("x")
    assert sh.record(routing(), "route-a", bad) is None


@case("TB14-D-031", reqs=["R-19"])
def test_d031_never_raises_on_unwritable_log(tmp_path):
    """PRD b4: never raises - `routing.jsonl` is a directory, so appending fails."""
    sh = shadow()
    led = tmp_path / "ledger"
    (led / "routing.jsonl").mkdir(parents=True)
    assert sh.record(routing(), "route-a", led) is None


@case("TB14-D-032", reqs=["R-19"])
def test_d032_record_is_content_free(tmp_path):
    """PRD b4: the line carries the *content-free* record; content attached to the result (a prompt) is not
    written."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    sh.record(routing(prompt="PROMPT-CONTENT-7731 please refactor", ticket_text="TICKET-TEXT-5512"), "route-a", led)
    raw = (led / "routing.jsonl").read_text()
    assert raw.strip()
    assert "PROMPT-CONTENT-7731" not in raw and "TICKET-TEXT-5512" not in raw


@case("TB14-D-033", reqs=["R-19"])
def test_d033_fields_match_log_record(tmp_path):
    """PRD b4: the line holds 'the content-free record from `factory.routing.jev_client.log_record`' - every field
    except `state_digest` (whose input is not published) equals what log_record returns for the same result."""
    sh = shadow()
    jev = lib.need("factory.routing.jev_client", "log_record")
    led = tmp_path / "ledger"
    led.mkdir()
    r = routing()
    sh.record(r, "route-a", led)
    rec = lines(led)[0]
    expected = json.loads(json.dumps(jev.log_record(r, "unused")))
    for f in LOG_FIELDS:
        if f != "state_digest":
            assert rec[f] == expected[f], f
    assert "state_digest" in rec


@case("TB14-D-034", reqs=["R-19"])
def test_d034_appends_not_overwrites(tmp_path):
    """PRD b4: record *appends* - an existing line in routing.jsonl is preserved."""
    sh = shadow()
    led = tmp_path / "ledger"
    led.mkdir()
    (led / "routing.jsonl").write_text('{"pre": "existing"}\n')
    sh.record(routing(), "route-a", led)
    raw = (led / "routing.jsonl").read_text().splitlines()
    assert raw[0] == '{"pre": "existing"}' and len(raw) == 2


@case("TB14-D-035", reqs=["R-19", "R-20"])
def test_d035_routing_log_never_steers_decisions(tmp_path):
    """PRD b4: 'nothing in the simulation reads that file to decide anything' - a routing.jsonl in the profile's
    ledger_dir full of contradictory or garbage lines leaves every outcome of the stream unchanged."""
    root, _, settings = stack(tmp_path)
    led = root / ".factory" / "ledger"
    led.mkdir(parents=True, exist_ok=True)
    (led / "routing.jsonl").write_text('{"decision": "allow", "actual_choice": "allow", "agrees": true}\n'
                                       "not json at all\n" * 3)
    events = script(root)
    assert [run_event(root, settings, pl) for pl, _ in events] == [w for _, w in events]


# ---------------------------------------------------------------- diagnostic: b6 runbook

@case("TB14-D-036", reqs=["R-20", "R-24"])
def test_d036_runbook_exists(tmp_path):
    """PRD b6: 'A short runbook in `docs/hooks/e2e.md` describes how to run the simulation and how to do one manual
    live rehearsal.'"""
    lib.need("factory.agents.simulate", "run_events")
    doc = lib.REPO / "docs" / "hooks" / "e2e.md"
    assert doc.is_file()
    text = doc.read_text().lower()
    assert "simulat" in text and "rehears" in text
