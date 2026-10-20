"""SFN-01 E-04, E-05, E-06 and the E-14 script regression: every sf command leaves an event, read-only ones do not."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import REPO, child_env, commit, git, read_events, sf

FIX = REPO / "tests" / "fixtures"
CONTRACT = {
    "contract_id": "C-ACC-001", "requirement_ids": ["R-ACC-1"], "symbol": "accmod:f",
    "state_scope": "pure", "semantics": "math_int", "check_method": "solver", "concurrency": "none",
    "frame": "nothing", "params": {"x": "int"}, "returns": "int",
    "intended": {"preconditions": [], "postconditions": ["result == x"], "invariants": [], "errors": []},
}


@pytest.fixture
def proj(repo):
    """A git repo with a slice, intake inputs and a contract, so delegated tools reach a real (non-usage) exit."""
    shutil.copytree(FIX / "slices" / "docs", repo / "docs", dirs_exist_ok=True)
    shutil.copytree(FIX / "intake" / "docs", repo / "docs", dirs_exist_ok=True)
    (repo / "c.json").write_text(json.dumps(CONTRACT))
    (repo / "accmod.py").write_text("def f(x):\n    return x\n")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "m.py").write_text("def a():\n    return 1\n")
    commit(repo, "fixtures", {"docs/.keep": ""})
    return repo


SL = "docs/slices/demo-login"
BRIEF = "docs/requirements/brief.md"

SWEEP = ["intake", "record-sweep", "--source", BRIEF, "--register", "docs/requirements/register.json",
         "--claims", "docs/requirements/claims.json"]
QA_INIT = ["qa", "--root", ".", "--slice", "s1", "init", "--criteria", "AC-1"]
SETUP = {"intake-signoff": [SWEEP], "qa-next": [QA_INIT], "qa-record": [QA_INIT]}  # run with events off first

# (id, argv, stage, slice id, forced verdict or None to derive from the exit code)
CASES = [
    ("intake-check", ["intake", "check", "--source", BRIEF, "--ledger", "nope.tsv"], "0-intake", "-", None),
    ("intake-record-sweep", ["intake", "record-sweep", "--source", BRIEF, "--register", "docs/requirements/register.json",
                             "--claims", "docs/requirements/claims.json"], "0-intake", "-", None),
    ("intake-signoff", ["intake", "signoff", "--source", BRIEF, "--finding", "F-002", "--by", "human:me"], "0-intake", "-", None),
    ("intake-gate", ["intake", "gate", "--source", BRIEF], "0-intake", "-", None),
    ("intake-gate-slice", ["intake", "gate", "--source", BRIEF, "--slice", SL], "0-intake", "demo-login", None),
    ("intake-seeds", ["intake", "seeds", "check"], "0-intake", "-", None),
    ("intake-experiments", ["intake", "experiments", "check"], "0-intake", "-", None),
    ("slice-check", ["slice", "check", SL], "4-slice", "demo-login", None),
    ("slice-triage", ["slice", "triage", "--root", "docs/slices"], "4-slice", "-", None),
    ("slice-lock", ["slice", "lock", SL], "5-evals", "demo-login", None),
    ("slice-tick", ["slice", "tick", SL, "1.1", "--role", "qa"], "6-implement", "demo-login", None),
    ("slice-verify", ["slice", "verify", SL, "1.1", "--role", "qa", "--evidence", "e", "--commit", "abc"], "7-qa", "demo-login", None),
    ("slice-amend", ["slice", "amend", SL, "--role", "reviewer", "--reason", "r"], "8-review", "demo-login", None),
    ("slice-done", ["slice", "done", SL], "9-drift", "demo-login", None),
    ("qa-init", ["qa", "--root", ".", "--slice", "s1", "init", "--criteria", "AC-1"], "7-qa", "s1", None),
    ("qa-next", ["qa", "--root", ".", "--slice", "s1", "next"], "7-qa", "s1", None),
    ("qa-record", ["qa", "--root", ".", "--slice", "s1", "record", "--status", "pass"], "7-qa", "s1", None),
    ("contracts-check", ["contracts", "check-contracts", "c.json"], "4c-contracts", "-", None),
    ("contracts-verify", ["contracts", "verify", "c.json", "--root", ".", "--no-cache"], "8-gate", "-", None),
    ("structure-diff", ["structure", "diff", "pkg", "pkg"], "8-gate", "-", None),
    ("structure-scan", ["structure", "scan", "pkg"], "4b-structure", "-", None),
    ("structure-model", ["structure", "model", "pkg", "-o", "m.json"], "4b-structure", "-", None),
    ("hitl-request", ["hitl", "request", "--name", "db", "--reason", "need owner", "--root", "."], "hitl", "-", "open"),
    ("ops-bundle", ["ops", "bundle"], "11-commit", "-", None),
]
IDS = [c[0] for c in CASES]


@pytest.mark.parametrize("cid,argv,stage,slice_id,verdict", CASES, ids=IDS)
def test_E04_each_listed_command_leaves_one_event(proj, cid, argv, stage, slice_id, verdict):
    head = git(proj, "rev-parse", "HEAD")
    for pre in SETUP.get(cid, []):
        assert sf(proj, *pre, env=child_env(SF_EVENTS="off")).returncode == 0
    assert read_events(proj) == []
    r = sf(proj, *argv)
    assert r.returncode != 2, f"test setup: {argv} must reach the tool, not a usage error: {r.stderr[-300:]}"
    evs = read_events(proj)
    assert len(evs) == 1, f"expected exactly one event, got {evs}"
    ev = evs[0]
    assert ev["stage"] == stage
    assert ev["slice"] == slice_id
    assert ev["sha"] == head
    assert ev["source"] == "sf"
    assert "role" not in ev or ev["role"] is None or isinstance(ev["role"], str)
    if verdict:
        assert ev["verdict"] == verdict
    else:
        assert ev["verdict"] == ("pass" if r.returncode == 0 else "fail")
        if r.returncode != 0:
            assert f"exit={r.returncode}" in ev["note"]


def test_E04_failing_tool_event_is_fail_with_the_exit_code_in_the_note(proj):
    r = sf(proj, "intake", "seeds", "check")  # research/seeds.tsv absent: exit 1
    assert r.returncode == 1
    (ev,) = read_events(proj)
    assert ev["verdict"] == "fail" and "exit=1" in ev["note"]


def test_E04_passing_tool_event_is_pass(proj):
    r = sf(proj, "slice", "triage", "--root", "docs/slices")
    assert r.returncode == 0
    (ev,) = read_events(proj)
    assert (ev["stage"], ev["verdict"]) == ("4-slice", "pass")


def test_E04_unusual_exit_code_is_recorded_exactly(proj):
    r = sf(proj, "contracts", "verify", "c.json", "--root", ".", "--no-cache")
    assert r.returncode not in (0, 2)
    (ev,) = read_events(proj)
    assert ev["verdict"] == "fail" and f"exit={r.returncode}" in ev["note"]


def test_E04_hitl_release_refused_without_a_terminal_is_recorded_as_fail(proj):
    sf(proj, "hitl", "request", "--name", "db", "--reason", "r", "--root", ".")
    r = sf(proj, "hitl", "release", "--name", "db", "--by", "human:me", "--root", ".")
    assert r.returncode == 5  # refused: no terminal in a test
    evs = read_events(proj)
    assert [e["stage"] for e in evs] == ["hitl", "hitl"]
    assert evs[0]["verdict"] == "open"
    assert evs[1]["verdict"] == "fail" and "exit=5" in evs[1]["note"]


def test_E04_slice_id_comes_from_the_dir_or_slice_argument_basename(proj):
    (proj / "docs" / "slices" / "other-one").mkdir()
    sf(proj, "slice", "check", "docs/slices/demo-login/")  # trailing slash
    sf(proj, "intake", "gate", "--source", BRIEF, "--slice", "docs/slices/other-one")
    assert [e["slice"] for e in read_events(proj)] == ["demo-login", "other-one"]


def test_E04_exit_code_is_returned_unchanged_when_events_are_off_or_broken(proj, tmp_path):
    runs = [["slice", "triage", "--root", "docs/slices"], ["intake", "seeds", "check"],
            ["contracts", "verify", "c.json", "--root", ".", "--no-cache"], ["slice", "tick", SL, "1.1", "--role", "qa"],
            ["structure", "scan", "pkg"]]
    baseline = [sf(proj, *a, env=child_env(SF_EVENTS="off")).returncode for a in runs]
    assert not (proj / "ops" / "events.jsonl").exists()
    (proj / "ops").write_text("a file where the directory should be\n")  # every emit now fails
    broken = []
    for a in runs:
        r = sf(proj, *a)
        broken.append(r.returncode)
        assert "event not recorded:" in r.stderr
        assert r.stderr.count("event not recorded:") == 1
    assert broken == baseline
    assert baseline[1] == 1 and baseline[0] == 0  # the table really spans pass and fail


def test_E04_SF_EVENTS_off_writes_no_event_and_no_ops_directory(proj):
    r = sf(proj, "slice", "triage", "--root", "docs/slices", env=child_env(SF_EVENTS="off"))
    assert r.returncode == 0 and "event not recorded" not in r.stderr
    assert not (proj / "ops").exists()


def test_E04_stdout_of_the_delegated_tool_is_not_polluted(proj):
    off = sf(proj, "slice", "triage", "--root", "docs/slices", env=child_env(SF_EVENTS="off"))
    on = sf(proj, "slice", "triage", "--root", "docs/slices")
    assert on.stdout == off.stdout


def test_E04_one_event_per_invocation_even_when_the_command_runs_twice(proj):
    sf(proj, "intake", "seeds", "check")
    sf(proj, "intake", "seeds", "check")
    assert len(read_events(proj)) == 2


def test_E04_unlisted_top_level_commands_emit_nothing(proj):
    for argv in (["verify", "--repo", "."], ["contracts", "report", "c.json"]):
        sf(proj, *argv)
    assert read_events(proj) == []


# ------------------------------------------------------------------ E-05

QUIET = [
    ("hitl-status", ["hitl", "status", "--root", "."]),
    ("sf-help", ["--help"]),
    ("slice-help", ["slice", "--help"]),
    ("ops-help", ["ops", "--help"]),
    ("hitl-help", ["hitl", "--help"]),
    ("slice-no-subcommand", ["slice"]),
    ("slice-bad-subcommand", ["slice", "no-such-command"]),
    ("slice-missing-required", ["slice", "tick", SL]),
    ("qa-bad-choice", ["qa", "--root", ".", "--slice", "s1", "bogus"]),
    ("hitl-missing-root", ["hitl", "status"]),
    ("ops-runtime", ["ops", "runtime"]),
]


@pytest.mark.parametrize("cid,argv", QUIET, ids=[q[0] for q in QUIET])
def test_E05_read_only_and_usage_commands_leave_no_event(proj, cid, argv):
    sf(proj, "hitl", "request", "--name", "x", "--reason", "r", "--root", ".")  # makes hitl status non-trivial
    assert len(read_events(proj)) == 1, "prerequisite (E-04): hitl request leaves its event"
    before = (proj / "ops" / "events.jsonl").read_text()
    r = sf(proj, *argv)
    assert (proj / "ops" / "events.jsonl").read_text() == before, f"{argv} (rc={r.returncode}) wrote an event"


def test_E05_usage_error_really_is_exit_2_and_silent(proj):
    r = sf(proj, "slice", "tick", SL)  # required args missing
    assert r.returncode == 2
    assert read_events(proj) == []
    assert not (proj / "ops").exists()


def test_E05_no_event_commands_do_not_create_the_ops_directory_via_events(proj):
    sf(proj, "hitl", "status", "--root", ".")
    assert not (proj / "ops" / "events.jsonl").exists()


# ------------------------------------------------------------------ E-06

def hook_project(root: Path) -> Path:
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "profile.yaml").write_text(
        "schema_version: 1\nproject: {name: demo}\npaths:\n  eval: [evals/**]\n", encoding="utf-8")
    from factory.ledger import create_ledger
    create_ledger(root / ".factory" / "ledger" / "T-1.md", "T-1", "demo")
    (root / ".factory" / "current_ticket").write_text("T-1\n")
    return root


def run_hook(hook: str, root: Path, agent_type: str, msg: str = "done", env=None):
    payload = {"session_id": "s", "cwd": str(root), "hook_event_name": "SubagentStop", "agent_type": agent_type,
               "agent_id": "a-1", "last_assistant_message": msg}
    return subprocess.run([sys.executable, "-m", "factory.hooks", hook], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(root), env=env or child_env(), timeout=60)


@pytest.mark.parametrize("hook", ["subagent_stop", "ledger_audit"])
def test_E06_hook_records_a_subagent_stop_event(repo, hook):
    hook_project(repo)
    r = run_hook(hook, repo, "implement")
    assert r.returncode == 0, r.stderr
    evs = [e for e in read_events(repo) if e["stage"] == "subagent-stop"]
    assert len(evs) >= 1
    ev = evs[-1]
    assert ev["source"] == "hook" and ev["role"] == "implement" and ev["verdict"] == "stopped"


@pytest.mark.parametrize("hook", ["subagent_stop", "ledger_audit"])
def test_E06_a_failing_emit_changes_neither_exit_code_nor_decision(repo, hook):
    hook_project(repo)
    base = run_hook(hook, repo, "implement", env=child_env(SF_EVENTS="off"))
    assert not (repo / "ops").exists()
    assert run_hook(hook, repo, "implement").returncode == base.returncode
    assert [e["stage"] for e in read_events(repo)] == ["subagent-stop"], "the hook must record an event when emit works"
    (repo / "ops" / "events.jsonl").unlink()
    (repo / "ops").rmdir()
    (repo / "ops").write_text("blocker\n")
    r = run_hook(hook, repo, "implement")
    assert (r.returncode, r.stdout) == (base.returncode, base.stdout)


def test_E06_rejecting_decision_of_subagent_stop_is_unchanged_by_the_event(repo):
    hook_project(repo)
    msg = "A short research report with no citations and no sources."
    off = run_hook("subagent_stop", repo, "research", msg=msg, env=child_env(SF_EVENTS="off"))
    on = run_hook("subagent_stop", repo, "research", msg=msg)
    assert "block" in off.stdout  # such a research report is rejected by the validator (decision JSON on stdout)
    assert (on.returncode, on.stdout) == (off.returncode, off.stdout)


def test_E06_each_stop_records_its_own_role(repo):
    hook_project(repo)
    run_hook("subagent_stop", repo, "implement")
    run_hook("subagent_stop", repo, "test")
    roles = [e["role"] for e in read_events(repo) if e["stage"] == "subagent-stop"]
    assert roles[-2:] == ["implement", "test"]


# ------------------------------------------------------------------ E-14 (script half; the existing suites run in test_regress.py)

SCRIPT = REPO / "scripts" / "ops-stage-event.sh"


def run_script(cwd, *args, env=None):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=str(cwd), capture_output=True, text=True,
                          env=env or child_env(), timeout=60)


def test_E14_stage_event_script_still_appends_a_well_formed_event(repo):
    head = git(repo, "rev-parse", "HEAD")
    r = run_script(repo, "7-qa", "slice-x", "pass", "all green")
    assert r.returncode == 0, r.stderr
    (ev,) = read_events(repo)
    assert {"at", "stage", "slice", "sha", "verdict", "note"} <= set(ev)
    assert (ev["stage"], ev["slice"], ev["verdict"], ev["note"], ev["sha"]) == ("7-qa", "slice-x", "pass", "all green", head)
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\+00:00|Z)$", ev["at"])


def test_E14_stage_event_script_without_note_and_usage_error(repo):
    assert run_script(repo, "7-qa", "s", "pass").returncode == 0
    assert read_events(repo)[0]["note"] == ""
    r = run_script(repo, "only-one-arg")
    assert r.returncode == 2
    assert len(read_events(repo)) == 1


def test_E14_stage_event_script_now_goes_through_emit_bounds(repo):
    r = run_script(repo, "7-qa", "s", "pass", "x" * 2001 + "\x07y")
    assert r.returncode == 0, r.stderr
    (ev,) = read_events(repo)
    assert len(ev["note"]) == 2000 and "\x07" not in ev["note"]


def test_E14_stage_event_script_runs_in_a_repo_without_commits(tmp_path):
    d = tmp_path / "fresh"
    d.mkdir()
    git(d, "init", "-q")
    assert run_script(d, "0-intake", "s", "open").returncode == 0
    assert read_events(d)[0]["sha"] == "unknown"
