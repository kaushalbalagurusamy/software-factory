"""L-06 events, L-07 human checkpoints, L-12 cost log."""
from __future__ import annotations

import json
import re
import shutil

import pytest

from .conftest import CHECKPOINTED, PHASES, at, parse_ts, walk

SECRETS = {
    "openai": "sk-" + "A1b2C3d4" * 4,
    "github": "ghp_" + "Zy9x8w7v" * 4,
    "aws": "AKIA" + "ABCDEFGH12345678"[:16],
    "gitlab": "glpat-" + "q1w2e3r4t5y6u7i8o9p0",
    "slack": "xoxb-" + "1234567890-abcdefghijkl",
    "bearer": "Bearer " + "abcdefghij0123456789ABCDEFGH",
    "assign": "password=" + "hunter2hunter2xyz",
    "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "abcdefghijk1234567",
}
SECRET_VALUE = {k: (v.split("=", 1)[1] if k == "assign" else v.split(" ", 1)[-1]) for k, v in SECRETS.items()}


def ev(rig, *args, now=0, **kw):
    p = rig.run("event", *args, now=now, **kw)
    assert p.returncode == 0, p.stdout + p.stderr
    return rig.events()[-1]


# ---------------------------------------------------------------- L-06
def test_L06_event_has_the_contract_fields(inited):
    e = ev(inited, "7-implement", "pass", "--note", "hello", "--role", "implement", now=7)
    for k in ("at", "stage", "slice", "phase", "verdict", "note", "source"):
        assert k in e, k
    assert e["stage"] == "7-implement" and e["verdict"] == "pass" and e["note"] == "hello"
    assert e["role"] == "implement"
    assert e["at"] == at(7)
    assert e["source"] in ("lsf", "hook", "agent")
    head = inited.git("rev-parse", "HEAD")
    assert len(e["sha"]) >= 7 and head.startswith(e["sha"])


def test_L06_sha_is_unknown_outside_git(rig, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert rig.run("init", cwd=plain).returncode == 0
    assert rig.run("event", "7-implement", "pass", cwd=plain).returncode == 0
    last = [json.loads(l) for l in (plain / ".lsf" / "events.jsonl").read_text().splitlines()][-1]
    assert last["sha"] == "unknown"


def test_L06_file_is_append_only_jsonl(inited):
    for i in range(3):
        ev(inited, "7-implement", "pass", "--note", f"n{i}", now=i)
    text = (inited.lsf_dir / "events.jsonl").read_text()
    assert text.endswith("\n")
    first = text.splitlines()[0]
    ev(inited, "7-implement", "fail", now=9)
    assert (inited.lsf_dir / "events.jsonl").read_text().splitlines()[0] == first
    for l in text.splitlines():
        json.loads(l)


@pytest.mark.parametrize("n,expect", [(1999, 1999), (2000, 2000), (2001, 2000), (5000, 2000)])
def test_L06_note_truncated_at_2000(inited, n, expect):
    e = ev(inited, "7-implement", "pass", "--note", "a" * n)
    assert e["note"] == "a" * expect


def test_L06_control_characters_are_replaced(inited):
    note = "a\x07b\x1bc\nd\re\tf\x7fg"  # a NUL cannot be passed in argv; it is covered through the hook payload
    e = ev(inited, "7-implement", "pass", "--note", note)
    assert not [c for c in e["note"] if ord(c) < 32 or ord(c) == 127]
    for ch in "abcdefg":
        assert ch in e["note"]
    raw_lines = (inited.lsf_dir / "events.jsonl").read_text().splitlines()
    assert len(raw_lines) == 1  # an embedded newline must not split the record


@pytest.mark.parametrize("kind", sorted(SECRETS))
def test_L06_secret_shaped_values_are_redacted(inited, kind):
    ev(inited, "7-implement", "pass", "--note", f"before {SECRETS[kind]} after")
    text = (inited.lsf_dir / "events.jsonl").read_text()
    assert SECRET_VALUE[kind] not in text
    assert "before" in text and "after" in text


def test_L06_secret_in_role_and_verdict_is_not_stored(inited):
    s = SECRETS["github"]
    inited.run("event", "7-implement", s, "--role", s)
    assert s not in (inited.lsf_dir / "events.jsonl").read_text()


def test_L06_concurrent_writers_lose_nothing(inited):
    procs = [inited.popen("event", "7-implement", "pass", "--note", f"w{i}", now=i) for i in range(8)]
    for p in procs:
        p.communicate(timeout=20)
        assert p.returncode == 0
    evs = inited.events()
    assert sorted(e["note"] for e in evs) == sorted(f"w{i}" for i in range(8))


def test_L06_failed_write_reports_on_stderr_and_keeps_exit_code(inited):
    (inited.lsf_dir / "events.jsonl").unlink(missing_ok=True)
    (inited.lsf_dir / "events.jsonl").mkdir()  # a directory: the append cannot succeed
    p = inited.run("event", "7-implement", "pass")
    assert p.returncode == 0
    assert "event not recorded:" in p.stderr
    assert "Traceback" not in p.stderr
    # exit code of a failing command is unchanged by the failed write
    q = inited.run("phase", "end", "9-review")
    assert q.returncode == 1


def test_L06_events_off_switches(inited):
    for var in ("SF_EVENTS", "LSF_EVENTS"):
        before = (inited.lsf_dir / "events.jsonl").read_text() if (inited.lsf_dir / "events.jsonl").exists() else ""
        p = inited.run("event", "7-implement", "pass", env={var: "off"})
        assert p.returncode == 0
        after = (inited.lsf_dir / "events.jsonl").read_text() if (inited.lsf_dir / "events.jsonl").exists() else ""
        assert after == before, var
    ev(inited, "7-implement", "pass")  # still writes when not off


def test_L06_phase_commands_also_write_events(inited):
    inited.phase("start", "7-implement", 1)
    assert [e["at"] for e in inited.phase_events("7-implement")] == [at(1)]


# ---------------------------------------------------------------- L-07
def stop_names(rig):
    p, data = rig.hitl()
    return p, [d["name"] for d in walk(data) if "name" in d] if data is not None else []


@pytest.mark.parametrize("phase", CHECKPOINTED)
def test_L07_phase_end_opens_a_review_stop(inited, phase):
    inited.phase("start", phase, 0)
    assert inited.phase("end", phase, 5).returncode == 0
    p, names = stop_names(inited)
    assert p.returncode == 3
    assert f"{phase}-review" in names
    s = inited.stop(f"{phase}-review")
    assert s["question"] == f"Approve {phase}?"
    assert str(s.get("reason", "")).strip()


@pytest.mark.parametrize("phase", PHASES[7:])
def test_L07_build_and_review_phases_have_no_default_stop(inited, phase):
    inited.phase("start", phase, 0)
    inited.phase("end", phase, 5)
    assert inited.run("hitl", "status").returncode == 0


def test_L07_ask_and_artifacts_are_recorded(inited):
    inited.phase("start", "4-prd", 0)
    r = inited.phase("end", "4-prd", 5, "--ask", "Ship the tracer PRD?", "--artifact", "docs/prds/a.md",
                     "--artifact", "docs/prds/b.md")
    assert r.returncode == 0, r.stderr
    s = inited.stop("4-prd-review")
    assert s["question"] == "Ship the tracer PRD?"
    arts = s.get("artifact") or s.get("artifacts")
    assert list(arts) == ["docs/prds/a.md", "docs/prds/b.md"]


def test_L07_checkpoints_all_and_none(rig):
    rig.init("--checkpoints", "all")
    rig.phase("start", "7-implement", 0)
    rig.phase("end", "7-implement", 1)
    assert rig.run("hitl", "status").returncode == 3
    assert rig.stop("7-implement-review") is not None


def test_L07_checkpoints_none_opens_nothing(rig):
    rig.init("--checkpoints", "none")
    rig.phase("start", "0-intake", 0)
    rig.phase("end", "0-intake", 1)
    assert rig.run("hitl", "status").returncode == 0


def test_L07_profile_can_switch_a_phase_off(inited):
    inited.edit_profile(lambda p: p.update(checkpoints={"1-sweep": False}))
    inited.phase("start", "1-sweep", 0)
    inited.phase("end", "1-sweep", 1)
    assert inited.run("hitl", "status").returncode == 0
    inited.phase("start", "0-intake", 2)
    inited.phase("end", "0-intake", 3)
    assert inited.run("hitl", "status").returncode == 3


def test_L07_phase_start_refused_while_a_stop_is_open(inited):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 5)
    n = len(inited.events())
    p = inited.phase("start", "1-sweep", 6)
    assert p.returncode == 3
    assert "0-intake-review" in p.stdout + p.stderr
    assert len(inited.events()) == n
    assert inited.run("hitl", "release", "0-intake-review", now=7).returncode == 0
    assert inited.phase("start", "1-sweep", 8).returncode == 0


def test_L07_manual_request_status_release_roundtrip(inited):
    p = inited.run("hitl", "request", "pick-db", "--question", "SQLite or Postgres?", "--artifact", "docs/adr/x.md",
                   "--artifact", "research/db.md", now=1)
    assert p.returncode == 0, p.stderr
    assert inited.run("hitl", "status", now=2).returncode == 3
    assert inited.stop("pick-db")["question"] == "SQLite or Postgres?"
    r = inited.run("hitl", "release", "pick-db", "--note", "SQLite", "--by", "owner@example.com", now=3)
    assert r.returncode == 0, r.stderr
    assert inited.run("hitl", "status", now=4).returncode == 0
    last = json.loads(inited.stop_lines()[-1])
    blob = json.dumps(last)
    assert "owner@example.com" in blob and "SQLite" in blob and at(3) in blob


def test_L07_release_refuses_unknown_and_already_released(inited):
    assert inited.run("hitl", "release", "ghost").returncode in (1, 2)
    inited.run("hitl", "request", "once", "--question", "q")
    assert inited.run("hitl", "release", "once").returncode == 0
    n = len(inited.stop_lines())
    assert inited.run("hitl", "release", "once").returncode in (1, 2)
    assert len(inited.stop_lines()) == n


def test_L07_ledger_is_append_only_and_hash_chained(inited):
    inited.run("hitl", "request", "a", "--question", "qa")
    inited.run("hitl", "request", "b", "--question", "qb")
    inited.run("hitl", "release", "a")
    lines = inited.stop_lines()
    assert len(lines) == 3
    entries = [json.loads(l) for l in lines]
    hexes = [set(v for v in e.values() if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)) for e in entries]
    assert all(hexes), "each entry carries a SHA-256 hex"
    for prev, cur in zip(hexes, entries[1:]):
        assert any(h in json.dumps(cur) for h in prev), "entry must reference the previous entry's hash"
    inited.run("hitl", "release", "b")
    assert inited.stop_lines()[:3] == lines


def test_L07_tampered_line_fails_verification_not_empty(inited):
    inited.run("hitl", "request", "a", "--question", "original question")
    inited.run("hitl", "request", "b", "--question", "second")
    f = inited.lsf_dir / "stops.jsonl"
    f.write_text(f.read_text().replace("original question", "edited question"))
    for cmd in (("hitl", "status"), ("status",)):
        p = inited.run(*cmd)
        out = p.stdout + p.stderr
        assert p.returncode == 1, (cmd, out)
        assert "stop ledger failed verification" in out
        assert "no stops" not in out.lower()
    assert inited.phase("start", "1-sweep", 1).returncode != 0


def test_L07_deleted_middle_line_fails_verification(inited):
    for n in "abc":
        inited.run("hitl", "request", n, "--question", n)
    f = inited.lsf_dir / "stops.jsonl"
    lines = f.read_text().splitlines()
    f.write_text("\n".join([lines[0], lines[2]]) + "\n")
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in p.stdout + p.stderr


def test_L07_malformed_ledger_line_fails_verification(inited):
    inited.run("hitl", "request", "a", "--question", "q")
    with open(inited.lsf_dir / "stops.jsonl", "a") as f:
        f.write("this is not json\n")
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in p.stdout + p.stderr


def test_L07_release_is_documented_as_a_procedure_not_identity(inited):
    from .conftest import SKILL
    inited.run("hitl", "request", "a", "--question", "q")
    out = inited.run("hitl", "release", "a").stdout
    text = (out + (SKILL / "SKILL.md").read_text()).lower()
    assert "not proof of identity" in text or "not a proof of identity" in text


# ---------------------------------------------------------------- L-12
def test_L12_cost_add_and_summary_by_model(inited):
    assert inited.run("cost", "add", "--usd", "1.5", "--tokens", "1000", "--model", "m-one", "--note", "r1").returncode == 0
    assert inited.run("cost", "add", "--usd", "0.5", "--model", "m-one").returncode == 0
    assert inited.run("cost", "add", "--usd", "0.25", "--model", "m-two").returncode == 0
    costs = [e for e in inited.events() if "cost" in json.dumps({k: e.get(k) for k in ("stage", "verdict")})]
    assert len(costs) == 3
    blob = json.dumps(costs[0])
    assert "1.5" in blob and "1000" in blob and "m-one" in blob and "manual" in blob.lower()
    s = inited.run("cost", "summary")
    assert s.returncode == 0
    lines = s.stdout.splitlines()
    one = next(l for l in lines if "m-one" in l)
    two = next(l for l in lines if "m-two" in l)
    assert re.search(r"\b2(\.0+)?\b", one) and re.search(r"0\.25", two)
    assert "manual" in s.stdout.lower()


def test_L12_cost_requires_a_stated_amount(inited):
    n = len(inited.events())
    assert inited.run("cost", "add", "--model", "m").returncode == 2
    assert inited.run("cost", "add", "--usd", "abc").returncode == 2
    assert inited.run("cost", "add", "--usd", "-1").returncode == 2
    assert len(inited.events()) == n


def test_L12_cost_note_is_redacted(inited):
    inited.run("cost", "add", "--usd", "1", "--note", SECRETS["openai"])
    assert SECRETS["openai"] not in (inited.lsf_dir / "events.jsonl").read_text()


def test_L12_summary_with_no_costs_does_not_invent_a_total(inited):
    s = inited.run("cost", "summary")
    assert s.returncode == 0
    assert not re.search(r"[1-9]\d*(\.\d+)?\s*(usd|\$)|\$\s*[1-9]", s.stdout.lower())
