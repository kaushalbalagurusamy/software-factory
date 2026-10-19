"""Slice format checker, role-gated ticks, hash-chained verification, criteria lock, triage."""
import json
import re
import shutil
from pathlib import Path

import pytest

from factory.slices.cli import main

FIX = Path(__file__).resolve().parent / "fixtures" / "slices" / "docs" / "slices" / "demo-login"
OK, CHECK_FAIL, USAGE, GATE, REFUSED = 0, 1, 2, 3, 4


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "docs" / "slices"
    shutil.copytree(FIX, r / "demo-login")
    return r


@pytest.fixture
def sl(root):
    return root / "demo-login"


def edit(path, old, new):
    t = path.read_text()
    assert old in t
    path.write_text(t.replace(old, new, 1))


def run(*argv):
    return main([str(a) for a in argv])


def verify_all(sl, tasks=("1.1", "1.2")):
    for t in tasks:
        assert run("tick", sl, t, "--role", "implementer") == OK
        assert run("verify", sl, t, "--role", "qa", "--evidence", "ran visible tests", "--commit", "abc123") == OK


def test_good_slice_passes(sl):
    assert run("check", sl) == OK


def test_ux_stories_after_what_changes_fails(sl, capsys):
    p = sl / "proposal.md"
    t = p.read_text()
    ux = t[t.index("## UX stories"):t.index("## What Changes")]
    wc = t[t.index("## What Changes"):t.index("## Out of scope")]
    p.write_text(t.replace(ux + wc, wc + ux))
    assert run("check", sl) == CHECK_FAIL
    assert "order" in capsys.readouterr().out.lower()


def test_ac_without_serves_fails(sl, capsys):
    edit(sl / "specs/auth/spec.md", "Serves: US-1\n\n#### Scenario: AC-1.1", "\n#### Scenario: AC-1.1")
    assert run("check", sl) == CHECK_FAIL
    out = capsys.readouterr().out
    assert "AC-1" in out and "Serves" in out


def test_ac_serves_unknown_story_fails(sl):
    edit(sl / "specs/auth/spec.md", "Serves: US-1\n", "Serves: US-9\n")
    assert run("check", sl) == CHECK_FAIL


def test_ac_without_scenario_fails(sl):
    p = sl / "specs/auth/spec.md"
    t = p.read_text()
    p.write_text(t[:t.index("#### Scenario: AC-2.1")])
    assert run("check", sl) == CHECK_FAIL


def test_ac_without_task_fails(sl):
    edit(sl / "tasks.md", "(AC-2)", "(AC-1.1)")
    assert run("check", sl) == CHECK_FAIL


def test_task_citing_unknown_ac_fails(sl):
    edit(sl / "tasks.md", "(AC-2)", "(AC-2, AC-77)")
    assert run("check", sl) == CHECK_FAIL


def test_dependency_cycle_fails(root, sl):
    other = root / "other"
    shutil.copytree(sl, other)
    edit(other / "proposal.md", "id: demo-login", "id: other")
    edit(other / "proposal.md", "depends_on: []", "depends_on: [demo-login]")
    edit(sl / "proposal.md", "depends_on: []", "depends_on: [other]")
    assert run("check", sl) == CHECK_FAIL


def test_unknown_dependency_fails(sl):
    edit(sl / "proposal.md", "depends_on: []", "depends_on: [ghost]")
    assert run("check", sl) == CHECK_FAIL


def test_bad_priority_fails(sl):
    edit(sl / "proposal.md", "priority: P1", "priority: P7")
    assert run("check", sl) == CHECK_FAIL


def test_usage_error_exit_code(tmp_path):
    assert run("check", tmp_path / "nope") == USAGE
    assert run("frobnicate") == USAGE


def test_implementer_cannot_verify(sl):
    run("tick", sl, "1.1", "--role", "implementer")
    assert run("verify", sl, "1.1", "--role", "implementer", "--evidence", "x", "--commit", "c") == REFUSED
    assert not (sl / "verification.json").exists()


def test_qa_cannot_tick(sl):
    assert run("tick", sl, "1.1", "--role", "qa") == REFUSED
    assert run("tick", sl, "1.1", "--role", "reviewer") == REFUSED
    assert "[x]" not in (sl / "tasks.md").read_text()


def test_verify_refuses_unticked_task(sl):
    assert run("verify", sl, "1.1", "--role", "qa", "--evidence", "x", "--commit", "c") == REFUSED


def test_tampered_chain_detected(sl, capsys):
    run("lock", sl)
    verify_all(sl)
    assert run("done", sl) == OK
    v = sl / "verification.json"
    data = json.loads(v.read_text())
    data["entries"][0]["evidence"] = "forged"
    v.write_text(json.dumps(data))
    assert run("done", sl) == GATE
    assert "chain" in capsys.readouterr().out.lower()


def test_weakened_criterion_without_approval_rejected(sl):
    run("lock", sl)
    edit(sl / "specs/auth/spec.md", "SHALL open a session", "MAY open a session")
    assert run("check", sl) == CHECK_FAIL


def test_amend_weakening_needs_approval(sl):
    run("lock", sl)
    edit(sl / "specs/auth/spec.md", "SHALL open a session", "SHALL sometimes open a session")
    assert run("amend", sl, "--role", "reviewer", "--reason", "relax", "--changed", "AC-1") == REFUSED
    assert run("amend", sl, "--role", "reviewer", "--reason", "relax", "--changed", "AC-1",
               "--approved-by", "nobody") == REFUSED
    assert run("amend", sl, "--role", "reviewer", "--reason", "relax", "--changed", "AC-1",
               "--approved-by", "human:ticket-5") == OK
    assert run("check", sl) == OK
    assert "human:ticket-5" in (sl / "amendments.md").read_text()


def test_removal_without_approval_rejected(sl):
    run("lock", sl)
    p = sl / "specs/auth/spec.md"
    t = p.read_text()
    p.write_text(t[:t.index("### Requirement: AC-2")])
    edit(sl / "tasks.md", "(AC-2)", "(AC-1.1)")
    assert run("check", sl) == CHECK_FAIL
    assert run("amend", sl, "--role", "slice-author", "--reason", "drop", "--removed", "AC-2") == REFUSED


def test_additive_amendment_accepted(sl):
    run("lock", sl)
    with (sl / "specs/auth/spec.md").open("a") as f:
        f.write("\n### Requirement: AC-3 Lockout\nThe system SHALL lock after five failures.\nServes: US-2\n\n"
                "#### Scenario: AC-3.1 Sixth try\n- GIVEN five failures\n- WHEN a sixth is made\n- THEN it is refused\n")
    with (sl / "tasks.md").open("a") as f:
        f.write("\n## 2. Lockout\n\n- [ ] 2.1 Lock after failures (AC-3). Verified by: visible acceptance test.\n")
    assert run("check", sl) == CHECK_FAIL  # unrecorded addition
    assert run("amend", sl, "--role", "reviewer", "--reason", "gap found in review",
               "--added", "AC-3", "--added", "AC-3.1") == OK
    assert run("check", sl) == OK
    assert run("amend", sl, "--role", "implementer", "--reason", "x", "--added", "AC-9") == USAGE


def test_lock_mismatch_on_story_change(sl):
    run("lock", sl)
    edit(sl / "proposal.md", "see my saved work", "see something")
    assert run("check", sl) == CHECK_FAIL


def test_done_refused_with_unverified_task(sl, capsys):
    run("lock", sl)
    run("tick", sl, "1.1", "--role", "implementer")
    run("verify", sl, "1.1", "--role", "qa", "--evidence", "e", "--commit", "c")
    assert run("done", sl) == GATE
    out = capsys.readouterr().out
    assert "1.2" in out


def test_done_refused_without_lock(sl):
    verify_all(sl)
    assert run("done", sl) == GATE


def test_done_refused_if_task_text_changed_after_verify(sl):
    run("lock", sl)
    verify_all(sl)
    edit(sl / "tasks.md", "Show failure reasons", "Show some failure reasons")
    assert run("done", sl) == GATE


def test_done_accepted_when_complete(sl):
    run("lock", sl)
    verify_all(sl)
    assert run("done", sl) == OK


def test_ledger_blocks_rejected_open_critical(sl, tmp_path, capsys):
    led = tmp_path / "ledger.tsv"
    led.write_text("req_id\ttrust\tstatus\nR-01\ttrusted\tok\nR-02\tconditioned (F-3)\topen Critical\n")
    assert run("check", sl, "--ledger", led) == CHECK_FAIL
    assert "R-02" in capsys.readouterr().out


def test_ledger_closed_critical_and_missing_row(sl, tmp_path):
    led = tmp_path / "ledger.tsv"
    led.write_text("req_id\ttrust\tstatus\nR-01\ttrusted\tok\nR-02\trejected (F-3)\tclosed\n")
    assert run("check", sl, "--ledger", led) == OK
    led.write_text("req_id\ttrust\tstatus\nR-01\ttrusted\tok\n")
    assert run("check", sl, "--ledger", led) == CHECK_FAIL


def test_triage_orders_dependency_before_priority(root, sl, capsys):
    for sid, prio, deps in (("a-low", "P3", []), ("b-high", "P0", ["a-low"]), ("c-mid", "P1", [])):
        d = root / sid
        shutil.copytree(sl, d)
        t = (d / "proposal.md").read_text()
        t = re.sub(r"id: demo-login", f"id: {sid}", t)
        t = re.sub(r"priority: P1", f"priority: {prio}", t)
        t = re.sub(r"depends_on: \[\]", f"depends_on: {deps}".replace("'", ""), t)
        (d / "proposal.md").write_text(t)
    shutil.rmtree(sl)
    assert run("triage", "--root", root) == OK
    out = json.loads(capsys.readouterr().out)
    order = [s["id"] for s in out["order"]]
    assert order.index("a-low") < order.index("b-high")
    assert order[0] == "c-mid"  # ready P1 beats ready P3; b-high waits on a-low
    assert out["cycles"] == []
    blocked = {b["id"]: b["waiting_on"] for b in out["blocked"]}
    assert blocked == {"b-high": ["a-low"]}


def test_triage_reports_cycle(root, sl, capsys):
    other = root / "other"
    shutil.copytree(sl, other)
    edit(other / "proposal.md", "id: demo-login", "id: other")
    edit(other / "proposal.md", "depends_on: []", "depends_on: [demo-login]")
    edit(sl / "proposal.md", "depends_on: []", "depends_on: [other]")
    assert run("triage", "--root", root) == CHECK_FAIL
    out = json.loads(capsys.readouterr().out)
    assert out["cycles"]
