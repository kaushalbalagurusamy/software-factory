"""L-02 commands, L-03 stages/profile, L-04 phase clock, L-05 time budget."""
from __future__ import annotations

import json
import re

import pytest

from .conftest import (CHECKPOINTED, GROUP, PHASES, at, group_of, minutes, raw, waiting)

@pytest.fixture
def nostops(rig):
    rig.init("--checkpoints", "none")
    return rig


COMMANDS = ["init", "phase", "event", "hitl", "status", "budget", "serve", "bundle", "hooks", "doctor", "cost"]


# ---------------------------------------------------------------- L-02
@pytest.mark.parametrize("cmd", COMMANDS)
def test_L02_every_command_has_help(rig, cmd):
    p = rig.run(cmd, "--help")
    assert p.returncode == 0, p.stderr
    assert (p.stdout + p.stderr).strip()


def test_L02_top_level_help_lists_all_commands(rig):
    p = rig.run("--help")
    assert p.returncode == 0
    for c in COMMANDS:
        assert c in p.stdout


def test_L02_usage_errors_exit_2(inited):
    assert inited.run().returncode == 2
    assert inited.run("nonsense").returncode == 2
    assert inited.run("phase").returncode == 2
    assert inited.run("event", "only-one-arg").returncode == 2
    assert inited.run("status", "--no-such-flag").returncode == 2


def test_L02_root_flag_overrides_cwd(rig, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    p = rig.run("init", "--root", rig.repo, cwd=elsewhere)
    assert p.returncode == 0, p.stderr
    assert (rig.repo / ".lsf" / "profile.json").is_file()
    assert not (elsewhere / ".lsf").exists()


def test_L02_default_root_is_nearest_git_root(rig):
    sub = rig.repo / "a" / "b"
    sub.mkdir(parents=True)
    assert rig.run("init", cwd=sub).returncode == 0
    assert (rig.repo / ".lsf" / "profile.json").is_file()
    assert not (sub / ".lsf").exists()


def test_L02_default_root_without_git_is_cwd(tmp_path, rig):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert rig.run("init", cwd=plain).returncode == 0
    assert (plain / ".lsf" / "profile.json").is_file()


def test_L02_exit_3_when_refused_by_stop_and_1_on_failed_check(inited):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 5)
    assert inited.phase("start", "1-sweep", 6).returncode == 3
    assert inited.phase("end", "7-implement", 6).returncode == 1


# ---------------------------------------------------------------- L-03
def test_L03_init_writes_profile_with_defaults(inited):
    prof = inited.profile()
    assert prof["session_minutes"] == 60
    assert prof["editor"] == "vscode"
    assert prof["workspace_root"] == str(inited.repo.resolve()) or prof["workspace_root"] == str(inited.repo)
    w = prof["weights"]
    assert (w["align"], w["review"], w["build"]) == (0.6, 0.2, 0.2)
    text = (inited.lsf_dir / "profile.json").read_text()
    idx = [text.index(f'"{p}"') for p in PHASES]
    assert idx == sorted(idx), "phases must be written in order"


def test_L03_phase_groups_match_the_contract(inited):
    prof = inited.profile()
    got = {}
    for ph in prof["phases"]:
        got[ph["id"] if isinstance(ph, dict) else ph] = ph.get("group") if isinstance(ph, dict) else None
    assert got == GROUP


def test_L03_weights_sum_rule_rejects_bad_sums_with_exit_2(inited):
    def set_w(a, r, b):
        inited.edit_profile(lambda p: p.update(weights={"align": a, "review": r, "build": b}))
    set_w(0.5, 0.2, 0.2)  # 0.9
    for cmd in (("budget",), ("status",)):
        p = inited.run(*cmd, now=1)
        assert p.returncode == 2, (cmd, p.stdout, p.stderr)
    set_w(0.6, 0.2, 0.3)  # 1.1
    assert inited.run("budget", now=1).returncode == 2
    set_w(0.6, 0.2, 0.2015)  # 1.0015: outside tolerance
    assert inited.run("budget", now=1).returncode == 2


def test_L03_weights_sum_rule_accepts_within_tolerance(inited):
    inited.edit_profile(lambda p: p.update(weights={"align": 0.6, "review": 0.2, "build": 0.2005}))
    assert inited.run("budget", now=1).returncode == 0
    inited.edit_profile(lambda p: p.update(weights={"align": 0.6, "review": 0.2, "build": 0.1995}))
    assert inited.run("budget", now=1).returncode == 0


def test_L03_custom_weights_and_session_minutes_drive_the_plan(inited):
    def cfg(p):
        p["session_minutes"] = 40
        p["weights"] = {"align": 0.5, "review": 0.25, "build": 0.25}
    inited.edit_profile(cfg)
    b = inited.budget(1)
    assert minutes(group_of(b, "align"), "planned") == pytest.approx(20)
    assert minutes(group_of(b, "build"), "planned") == pytest.approx(10)
    assert minutes(group_of(b, "review"), "planned") == pytest.approx(10)


def test_L03_init_checkpoints_option_validated(rig):
    assert rig.run("init", "--checkpoints", "bogus").returncode == 2
    for v in ("align", "all", "none"):
        assert rig.run("init", "--checkpoints", v, now=0).returncode == 0


def test_L03_rerunning_init_keeps_history(inited):
    inited.phase("start", "7-implement", 1)
    before = (inited.lsf_dir / "events.jsonl").read_text()
    assert inited.run("init", now=2).returncode == 0
    assert (inited.lsf_dir / "events.jsonl").read_text().startswith(before)


def test_L03_stage_alias_map_documented_in_skill():
    from .conftest import SKILL
    text = (SKILL / "SKILL.md").read_text()
    assert "alias" in text.lower()
    for p in PHASES:
        assert p in text


# ---------------------------------------------------------------- L-04
def test_L04_phase_start_and_end_append_timestamped_events(nostops):
    assert nostops.phase("start", "7-implement", 3).returncode == 0
    assert nostops.phase("end", "7-implement", 9, "--verdict", "pass", "--note", "built").returncode == 0
    evs = nostops.phase_events("7-implement")
    assert len(evs) == 2
    assert evs[0]["at"] == at(3) and evs[1]["at"] == at(9)
    assert evs[1]["verdict"] == "pass" and "built" in evs[1]["note"]


def test_L04_starting_a_phase_closes_the_open_one_as_switched(nostops):
    nostops.phase("start", "7-implement", 0)
    assert nostops.phase("start", "8-qa", 10).returncode == 0
    ev = [e for e in nostops.phase_events("7-implement") if e.get("verdict") == "switched"]
    assert len(ev) == 1 and ev[0]["at"] == at(10)
    # the open phase is now 8-qa
    st = nostops.run("status", now=12)
    assert "8-qa" in st.stdout
    b = nostops.budget(30)
    assert minutes(group_of(b, "build"), "actual") == pytest.approx(30)


def test_L04_ending_a_phase_that_is_not_open_exits_1(nostops):
    assert nostops.phase("end", "7-implement", 1).returncode == 1  # never started
    nostops.phase("start", "7-implement", 2)
    n = len(nostops.events())
    assert nostops.phase("end", "8-qa", 3).returncode == 1  # different phase open
    assert len(nostops.events()) == n
    assert nostops.phase("end", "7-implement", 4).returncode == 0
    assert nostops.phase("end", "7-implement", 5).returncode == 1  # already ended


@pytest.mark.parametrize("bad", ["bogus", "0-INTAKE", "", "../x", "11-extra", "7"])
def test_L04_unknown_phase_names_exit_2_and_write_nothing(inited, bad):
    n = len(inited.events())
    assert inited.phase("start", bad, 1).returncode == 2
    assert inited.phase("end", bad, 1).returncode == 2
    assert len(inited.events()) == n


def test_L04_status_shows_open_phase_elapsed_and_next(nostops):
    idle = nostops.run("status", now=1)
    assert idle.returncode == 0
    nostops.phase("start", "0-intake", 0)
    st = nostops.run("status", now=12)
    assert st.returncode == 0
    assert "0-intake" in st.stdout
    assert re.search(r"\b12(\.0+)?\b", st.stdout)
    assert "1-sweep" in st.stdout  # next phase


def test_L04_status_lists_open_stops(inited):
    inited.run("hitl", "request", "needs-owner", "--question", "Is this OK?", now=1)
    st = inited.run("status", now=2)
    assert "needs-owner" in st.stdout


# ---------------------------------------------------------------- L-05
def test_L05_budget_planned_minutes_and_not_measured(inited):
    b = inited.budget(1)
    for g, planned in (("align", 36), ("build", 12), ("review", 12)):
        d = group_of(b, g)
        assert minutes(d, "planned") == pytest.approx(planned)
        act = raw(d, "actual")
        assert act is None or (isinstance(act, str) and "not measured" in act), (g, act)
    txt = inited.run("budget", now=1)
    assert txt.returncode == 0 and "not measured" in txt.stdout


def test_L05_zero_minutes_is_measured_zero_not_unknown(nostops):
    nostops.phase("start", "7-implement", 5)
    nostops.phase("end", "7-implement", 5)
    d = group_of(nostops.budget(6), "build")
    assert minutes(d, "actual") == 0
    assert isinstance(raw(d, "actual"), (int, float))


def test_L05_open_phase_counts_to_now(nostops):
    nostops.phase("start", "7-implement", 0)
    assert minutes(group_of(nostops.budget(7), "build"), "actual") == pytest.approx(7)
    assert minutes(group_of(nostops.budget(19), "build"), "actual") == pytest.approx(19)


def test_L05_percent_and_over_under_flags(nostops):
    nostops.phase("start", "7-implement", 0)
    nostops.phase("start", "0-intake", 30)  # build ran 30 of 12 planned; align open from 30
    b = nostops.budget(39)
    build, align = group_of(nostops.budget(39), "build"), group_of(b, "align")
    pct = raw(build, "percent")
    assert pct == pytest.approx(250, abs=1) or pct == pytest.approx(2.5, abs=0.01)
    assert "over" in json.dumps(build).lower().replace("overall", "")
    assert "under" in json.dumps(align).lower()
    text = nostops.run("budget", now=39).stdout.lower()
    assert any("build" in l and "over" in l for l in text.splitlines())
    assert any("align" in l and "under" in l for l in text.splitlines())


def test_L05_waiting_on_human_is_reported_separately(inited):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 10)       # stop opens at +10
    inited.run("hitl", "release", "0-intake-review", now=25)  # waited 15
    inited.phase("start", "1-sweep", 25)
    inited.phase("end", "1-sweep", 40)        # second stop opens at +40, still open at +45
    b = inited.budget(45)
    assert waiting(b) == pytest.approx(20, abs=0.1)
    # phase time is not inflated by the waiting: align = 10 + 15
    assert minutes(group_of(b, "align"), "actual") == pytest.approx(25, abs=0.1)
    out = inited.run("budget", now=45).stdout.lower()
    assert "waiting on human" in out


def test_L05_waiting_during_an_open_phase(nostops):
    nostops.phase("start", "7-implement", 0)
    nostops.run("hitl", "request", "design-q", "--question", "Which way?", now=10)
    nostops.run("hitl", "release", "design-q", now=20)
    b = nostops.budget(30)
    assert waiting(b) == pytest.approx(10, abs=0.1)
    assert 20 - 0.1 <= minutes(group_of(b, "build"), "actual") <= 30 + 0.1


def test_L05_waiting_line_always_present(inited):
    inited.phase("start", "7-implement", 0)
    out = inited.run("budget", now=5).stdout.lower()
    assert "waiting on human" in out
