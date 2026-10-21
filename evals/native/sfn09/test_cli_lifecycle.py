"""SFN-09 CLI acceptance: D-1, D-2, D-3 (CLI half), D-5, D-6, D-7, D-8, D-10, D-12."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from .conftest import (PY, STALE, answer, apply_, ask, ask_ok, canon_hash, out, record, sha, state_of, to_applied,
                       walk)

STATES = {"asked", "answered", "recorded", "applied"}


# ------------------------------------------------------------------ D-2 options validation
def test_D2_no_option_is_a_plain_open_stop(inited):
    ask_ok(inited, "plain", ())
    s = inited.stop("plain")
    assert s["state"] == "asked" and not s.get("options")


@pytest.mark.parametrize("n", [1, 2, 6])
def test_D2_one_to_six_options_accepted_and_stored_in_order(inited, n):
    opts = [f"opt-{i}" for i in range(n)]
    ask_ok(inited, "pick", opts)
    assert inited.stop("pick")["options"] == opts


def test_D2_seven_options_rejected_and_nothing_written(inited):
    before = inited.stop_lines()
    p = ask(inited, "pick", [f"o{i}" for i in range(7)])
    assert p.returncode != 0
    assert inited.stop_lines() == before and inited.stop("pick") is None


@pytest.mark.parametrize("length,ok", [(1, True), (120, True), (121, False)])
def test_D2_option_length_boundary(inited, length, ok):
    before = inited.stop_lines()
    p = ask(inited, "pick", ["a" * length, "b"])
    assert (p.returncode == 0) is ok, out(p)
    if not ok:
        assert inited.stop_lines() == before
    else:
        assert inited.stop("pick")["options"][0] == "a" * length


@pytest.mark.parametrize("bad", ["", "   "])
def test_D2_blank_option_rejected(inited, bad):
    before = inited.stop_lines()
    p = ask(inited, "pick", [bad, "b"])
    assert p.returncode != 0 and inited.stop_lines() == before


def test_D2_proposal_hash_matches_canonical_json_of_question_options_and_artifact_bytes(inited):
    body = b"line one\nline two\n"
    inited.write("docs/adr/x.md", body)
    ask_ok(inited, "pick", ["Alpha", "Beta"], artifacts=["docs/adr/x.md"], question="Which?")
    want = canon_hash("Which?", ["Alpha", "Beta"], [("docs/adr/x.md", sha(body))])
    assert inited.stop("pick")["proposal_hash"] == want


def test_D2_hash_depends_on_option_order_and_question(inited):
    ask_ok(inited, "a", ["x", "y"], question="q")
    ask_ok(inited, "b", ["y", "x"], question="q")
    ask_ok(inited, "c", ["x", "y"], question="q2")
    hs = {inited.stop(n)["proposal_hash"] for n in "abc"}
    assert len(hs) == 3 and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hs)


def test_D2_hash_is_stable_for_identical_proposals(inited):
    ask_ok(inited, "a", ["x", "y"], question="q")
    ask_ok(inited, "b", ["x", "y"], question="q")
    assert inited.stop("a")["proposal_hash"] == inited.stop("b")["proposal_hash"]


@pytest.mark.parametrize("kind", ["missing", "directory", "outside", "symlink_outside", "over_1mib"])
def test_D2_request_with_unhashable_artifact_is_refused_and_opens_nothing(inited, kind):
    outside = inited.tmp / "outside.md"
    outside.write_text("secret\n")
    path = {"missing": "docs/none.md", "directory": "docs", "outside": str(outside),
            "symlink_outside": "link.md", "over_1mib": "big.md"}[kind]
    inited.write("docs/keep.md", "k\n")
    if kind == "symlink_outside":
        os.symlink(outside, inited.repo / "link.md")
    if kind == "over_1mib":
        inited.write("big.md", b"a" * (1024 * 1024 + 1))
    before = inited.stop_lines()
    p = ask(inited, "pick", ["A", "B"], artifacts=[path])
    assert p.returncode != 0, out(p)
    assert inited.stop_lines() == before and inited.stop("pick") is None
    assert inited.run("hitl", "status").returncode == 0


@pytest.mark.parametrize("kind", ["missing", "directory", "outside", "over_1mib"])
def test_D2_checkpoint_with_unhashable_artifact_still_opens_with_unbound(inited, kind):
    outside = inited.tmp / "outside.md"
    outside.write_text("secret\n")
    path = {"missing": "docs/none.md", "directory": "docs", "outside": str(outside), "over_1mib": "big.md"}[kind]
    inited.write("docs/keep.md", "k\n")
    if kind == "over_1mib":
        inited.write("big.md", b"a" * (1024 * 1024 + 1))
    inited.phase("start", "4-prd", 0)
    assert inited.phase("end", "4-prd", 5, "--ask", "Ship?", "--artifact", path).returncode == 0
    s = inited.stop("4-prd-review")
    assert s["state"] == "asked"
    assert s["proposal_hash"] == canon_hash("Ship?", [], [(path, "unbound")])


def test_D2_unbound_checkpoint_can_still_be_released(inited):
    inited.phase("start", "4-prd", 0)
    inited.phase("end", "4-prd", 5, "--artifact", "docs/none.md")
    assert inited.run("hitl", "release", "4-prd-review").returncode == 0


def test_D2_exactly_1mib_artifact_is_still_hashed(inited):
    body = b"a" * (1024 * 1024)
    inited.write("ok.md", body)
    ask_ok(inited, "pick", ["A", "B"], artifacts=["ok.md"])
    assert inited.stop("pick")["proposal_hash"] == canon_hash("Which one?", ["A", "B"], [("ok.md", sha(body))])


def test_D2_phase_end_checkpoint_uses_the_same_hash_function_without_options(inited):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 5)
    s = inited.stop("0-intake-review")
    assert s["state"] == "asked" and not s.get("options")
    assert s["proposal_hash"] == canon_hash("Approve 0-intake?", [], [])


def test_D2_phase_end_checkpoint_hashes_its_artifacts(inited):
    body = b"prd\n"
    inited.write("docs/prds/a.md", body)
    inited.phase("start", "4-prd", 0)
    assert inited.phase("end", "4-prd", 5, "--ask", "Ship it?", "--artifact", "docs/prds/a.md").returncode == 0
    assert inited.stop("4-prd-review")["proposal_hash"] == canon_hash("Ship it?", [], [("docs/prds/a.md", sha(body))])


# ------------------------------------------------------------------ D-3 answer == release (CLI)
def test_D3_answer_must_equal_an_option_exactly(inited):
    ask_ok(inited, "pick", ["Alpha", "Beta"])
    before = inited.stop_lines()
    for bad in ("Gamma", "alpha", "ALPHA", "Alph", "Alpha Beta"):
        p = answer(inited, "pick", bad)
        assert p.returncode != 0, bad
    assert inited.stop_lines() == before and state_of(inited, "pick") == "asked"
    assert inited.run("hitl", "status").returncode == 3


def test_D3_stop_with_options_refuses_release_without_answer(inited):
    ask_ok(inited, "pick", ["Alpha", "Beta"])
    before = inited.stop_lines()
    assert inited.run("hitl", "release", "pick", "--note", "just ok").returncode != 0
    assert inited.stop_lines() == before and state_of(inited, "pick") == "asked"


def test_D3_valid_answer_releases_and_is_stored_with_the_hash(inited):
    ask_ok(inited, "pick", ["Alpha", "Beta"])
    h = inited.stop("pick")["proposal_hash"]
    p = answer(inited, "pick", "Beta", "because", now=3)
    assert p.returncode == 0, out(p)
    s = inited.stop("pick")
    assert s["state"] == "answered" and s["answer"] == "Beta" and s["answered_at"]
    assert s["proposal_hash"] == h
    last = json.loads(inited.stop_lines()[-1])
    assert last.get("answer") == "Beta" and last.get("proposal_hash") == h
    assert inited.run("hitl", "status").returncode == 0


def test_D3_every_listed_option_is_answerable(inited):
    for i, o in enumerate(["x", "y", "z"]):
        ask_ok(inited, f"p{i}", ["x", "y", "z"])
        assert answer(inited, f"p{i}", o).returncode == 0
        assert inited.stop(f"p{i}")["answer"] == o


def test_D3_stop_without_options_releases_as_before(inited):
    ask_ok(inited, "plain", ())
    assert inited.run("hitl", "release", "plain", "--note", "ok").returncode == 0
    s = inited.stop("plain")
    assert s["state"] == "answered" and not s.get("answer")


def test_D3_second_release_of_an_answered_stop_is_refused(inited):
    ask_ok(inited, "pick", ["Alpha", "Beta"])
    assert answer(inited, "pick", "Alpha").returncode == 0
    before = inited.stop_lines()
    assert answer(inited, "pick", "Beta").returncode != 0
    assert inited.stop_lines() == before and inited.stop("pick")["answer"] == "Alpha"


@pytest.mark.parametrize("mutation", ["edit", "delete", "append"])
def test_D3_artifact_drift_blocks_release_and_releases_nothing(inited, mutation):
    art = "docs/adr.md"
    inited.write(art, "v1\n")
    ask_ok(inited, "pick", ["Alpha", "Beta"], artifacts=[art])
    if mutation == "edit":
        inited.write(art, "v2\n")
    elif mutation == "delete":
        (inited.repo / art).unlink()
    else:
        with open(inited.repo / art, "a") as f:
            f.write("x")
    before = inited.stop_lines()
    p = answer(inited, "pick", "Alpha")
    assert p.returncode != 0
    assert "proposal changed since it was asked; ask again" in out(p)
    assert inited.stop_lines() == before
    s = inited.stop("pick")
    assert s["state"] == "asked" and not s.get("answer")
    assert inited.run("hitl", "status").returncode == 3


def test_D3_reverting_the_artifact_makes_the_original_proposal_answerable_again(inited):
    inited.write("docs/adr.md", "v1\n")
    ask_ok(inited, "pick", ["Alpha", "Beta"], artifacts=["docs/adr.md"])
    inited.write("docs/adr.md", "v2\n")
    assert answer(inited, "pick", "Alpha").returncode != 0
    inited.write("docs/adr.md", "v1\n")
    assert answer(inited, "pick", "Alpha").returncode == 0


def test_D3_drift_in_an_unrelated_file_does_not_block(inited):
    inited.write("docs/adr.md", "v1\n")
    inited.write("docs/other.md", "o1\n")
    ask_ok(inited, "pick", ["Alpha", "Beta"], artifacts=["docs/adr.md"])
    inited.write("docs/other.md", "o2\n")
    assert answer(inited, "pick", "Alpha").returncode == 0


def test_D3_drift_blocks_option_less_stops_too(inited):
    inited.write("docs/adr.md", "v1\n")
    ask_ok(inited, "plain", (), artifacts=["docs/adr.md"])
    inited.write("docs/adr.md", "v2\n")
    p = inited.run("hitl", "release", "plain")
    assert p.returncode != 0 and "proposal changed" in out(p) and state_of(inited, "plain") == "asked"


def test_D3_phase_end_checkpoint_drift_blocks_release(inited):
    inited.write("docs/prds/a.md", "v1\n")
    inited.phase("start", "4-prd", 0)
    inited.phase("end", "4-prd", 5, "--artifact", "docs/prds/a.md")
    inited.write("docs/prds/a.md", "v2\n")
    p = inited.run("hitl", "release", "4-prd-review")
    assert p.returncode != 0 and state_of(inited, "4-prd-review") == "asked"


# ------------------------------------------------------------------ D-4 strict mode on the CLI
def test_D4_strict_mode_still_blocks_cli_release_with_an_answer(rig):
    rig.init("--strict-hitl")
    ask_ok(rig, "pick", ["Alpha", "Beta"])
    before = rig.stop_lines()
    p = answer(rig, "pick", "Alpha")
    assert p.returncode != 0
    assert rig.stop_lines() == before and state_of(rig, "pick") == "asked"
    assert rig.run("hitl", "status").returncode == 3


# ------------------------------------------------------------------ D-5 recorded
def answered(rig, name="d", options=("Alpha", "Beta"), choose="Alpha"):
    ask_ok(rig, name, options)
    assert answer(rig, name, choose).returncode == 0


def test_D5_recorded_requires_answered_state(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    before = inited.stop_lines()
    p = record(inited, "d", "docs/rec.md")
    assert p.returncode != 0 and inited.stop_lines() == before and state_of(inited, "d") == "asked"


def test_D5_recorded_unknown_stop_fails(inited):
    inited.write("docs/rec.md", "x\n")
    assert record(inited, "ghost", "docs/rec.md").returncode != 0


@pytest.mark.parametrize("target", ["docs/rec.md", "docs"])
def test_D5_recorded_accepts_file_or_directory_inside_root(inited, target):
    inited.write("docs/rec.md", "x\n")
    answered(inited)
    p = record(inited, "d", target, "--note", "written to adr")
    assert p.returncode == 0, out(p)
    s = inited.stop("d")
    assert s["state"] == "recorded" and s["recorded_where"] and s["recorded_at"]
    assert s["answer"] == "Alpha"
    assert target in str(s["recorded_where"])


def test_D5_recorded_note_is_kept(inited):
    inited.write("docs/rec.md", "x\n")
    answered(inited)
    record(inited, "d", "docs/rec.md", "--note", "NOTE-MARKER-77")
    assert "NOTE-MARKER-77" in inited.stop_lines()[-1]


@pytest.mark.parametrize("kind", ["missing", "dotdot", "abs_outside", "symlink_file_out", "symlink_dir_out",
                                  "dotdot_via_dir", "empty"])
def test_D5_recorded_rejects_missing_and_escaping_paths(inited, kind):
    outside_dir = inited.tmp / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "f.txt").write_text("s\n")
    (inited.tmp / "outside.txt").write_text("s\n")
    inited.write("docs/rec.md", "x\n")
    os.symlink(inited.tmp / "outside.txt", inited.repo / "link_f")
    os.symlink(outside_dir, inited.repo / "link_d")
    path = {"missing": "docs/nope.md", "dotdot": "../outside.txt", "abs_outside": str(inited.tmp / "outside.txt"),
            "symlink_file_out": "link_f", "symlink_dir_out": "link_d", "dotdot_via_dir": "docs/../../outside.txt",
            "empty": ""}[kind]
    answered(inited)
    before = inited.stop_lines()
    p = record(inited, "d", path)
    assert p.returncode != 0, out(p)
    assert inited.stop_lines() == before and state_of(inited, "d") == "answered"


def test_D5_symlink_staying_inside_the_root_is_allowed(inited):
    inited.write("docs/rec.md", "x\n")
    os.symlink("docs/rec.md", inited.repo / "link_in")
    answered(inited)
    assert record(inited, "d", "link_in").returncode == 0


def test_D5_recorded_twice_is_refused(inited):
    inited.write("docs/rec.md", "x\n")
    answered(inited)
    assert record(inited, "d", "docs/rec.md").returncode == 0
    before = inited.stop_lines()
    assert record(inited, "d", "docs/rec.md").returncode != 0
    assert inited.stop_lines() == before


def test_D5_recorded_after_applied_is_refused(inited):
    to_applied(inited)
    before = inited.stop_lines()
    assert record(inited, "d", "docs/rec.md").returncode != 0
    assert inited.stop_lines() == before and state_of(inited, "d") == "applied"


# ------------------------------------------------------------------ D-6 applied
def recorded(rig, name="d"):
    rig.write("docs/rec.md", "x\n")
    answered(rig, name)
    assert record(rig, name, "docs/rec.md").returncode == 0


@pytest.mark.parametrize("upto", ["asked", "answered"])
def test_D6_applied_requires_recorded_state(inited, upto):
    ask_ok(inited, "d")
    if upto == "answered":
        assert answer(inited, "d", "Alpha").returncode == 0
    before = inited.stop_lines()
    p = apply_(inited, "d", "all good")
    assert p.returncode != 0 and inited.stop_lines() == before and state_of(inited, "d") == upto


def test_D6_applied_unknown_stop_fails(inited):
    assert apply_(inited, "ghost", "x").returncode != 0


@pytest.mark.parametrize("ev", ["", "   ", "\t\n"])
def test_D6_blank_evidence_is_refused(inited, ev):
    recorded(inited)
    before = inited.stop_lines()
    assert apply_(inited, "d", ev).returncode != 0
    assert inited.stop_lines() == before and state_of(inited, "d") == "recorded"


def test_D6_evidence_flag_is_required(inited):
    recorded(inited)
    before = inited.stop_lines()
    assert inited.run("hitl", "applied", "d").returncode != 0
    assert inited.stop_lines() == before


def test_D6_applied_with_evidence_completes_the_lifecycle(inited):
    recorded(inited)
    p = apply_(inited, "d", "pytest 12 passed; commit abc123", now=9)
    assert p.returncode == 0, out(p)
    s = inited.stop("d")
    assert s["state"] == "applied" and "commit abc123" in s["applied_evidence"] and s["applied_at"]
    assert s["answer"] == "Alpha" and s["recorded_where"]
    assert inited.run("hitl", "status").returncode == 0


def test_D6_applied_twice_is_refused(inited):
    to_applied(inited)
    before = inited.stop_lines()
    assert apply_(inited, "d", "again").returncode != 0
    assert inited.stop_lines() == before


def test_D6_neither_command_releases_a_stop(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    record(inited, "d", "docs/rec.md")
    apply_(inited, "d", "e")
    assert inited.stop("d")["state"] == "asked"
    assert inited.run("hitl", "status").returncode == 3


def test_D6_recorded_and_applied_emit_hitl_events(inited):
    to_applied(inited)
    evs = [e for e in inited.events() if e.get("stage") == "hitl"]
    verdicts = [e.get("verdict") for e in evs]
    assert "recorded" in verdicts and "applied" in verdicts
    assert verdicts.index("recorded") < verdicts.index("applied")


def test_D6_failed_transitions_emit_no_event(inited):
    ask_ok(inited, "d")
    n = len(inited.events())
    apply_(inited, "d", "x")
    record(inited, "d", "README.md")
    assert len(inited.events()) == n


# ------------------------------------------------------------------ D-1 / D-7 derived fields and states
def test_D7_state_walks_asked_answered_recorded_applied_and_fields_accumulate(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    keys = {"id", "state", "options", "proposal_hash", "answer", "answered_at", "recorded_where", "recorded_at",
            "applied_evidence", "applied_at"}
    s = inited.stop("d")
    assert keys <= set(s) and s["state"] == "asked" and s["id"] == "d" == s["name"]
    assert s["answer"] is None and s["recorded_where"] is None and s["applied_evidence"] is None
    answer(inited, "d", "Beta")
    s = inited.stop("d")
    assert s["state"] == "answered" and s["answered_at"] and s["recorded_at"] is None
    record(inited, "d", "docs/rec.md")
    s = inited.stop("d")
    assert s["state"] == "recorded" and s["applied_at"] is None
    apply_(inited, "d", "proof")
    s = inited.stop("d")
    assert s["state"] == "applied" and s["applied_evidence"] == "proof" and s["answer"] == "Beta"


def test_D7_every_stop_in_status_json_has_a_valid_state(inited):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 1)
    ask_ok(inited, "m")
    _, data = inited.hitl()
    stops = [d for d in walk(data) if "name" in d and "question" in d]
    assert len(stops) >= 2 and all(d["state"] in STATES for d in stops)


def test_D7_chain_survives_the_whole_lifecycle_and_status_verifies(inited):
    to_applied(inited)
    ask_ok(inited, "second")
    p = inited.run("hitl", "status")
    assert p.returncode == 3 and "failed verification" not in out(p)
    lines = inited.stop_lines()
    assert len(lines) == 5
    entries = [json.loads(l) for l in lines]
    hexes = [set(v for v in e.values() if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)) for e in entries]
    for prev, cur in zip(hexes, entries[1:]):
        assert any(h in json.dumps(cur) for h in prev), "each new entry kind chains to its predecessor"


@pytest.mark.parametrize("which,needle,repl", [
    (1, "Alpha", "Beta"),          # the answer in the release entry
    (2, "docs/rec.md", "README.md"),  # recorded location
    (3, "tests pass", "forged"),   # applied evidence
])
def test_D7_tampering_with_new_entries_fails_verification(inited, which, needle, repl):
    to_applied(inited)
    f = inited.lsf_dir / "stops.jsonl"
    lines = f.read_text().splitlines()
    target = lines[which]
    assert needle in target, target
    lines[which] = target.replace(needle, repl, 1)
    f.write_text("\n".join(lines) + "\n")
    for cmd in (("hitl", "status"), ("status",)):
        p = inited.run(*cmd)
        assert p.returncode == 1 and "stop ledger failed verification" in out(p), (cmd, out(p))


def test_D7_tampering_with_options_or_hash_in_the_open_entry_fails(inited):
    ask_ok(inited, "d", ["Alpha", "Beta"])
    answer(inited, "d", "Alpha")
    f = inited.lsf_dir / "stops.jsonl"
    f.write_text(f.read_text().replace("Beta", "Gamma", 1))
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in out(p)


def test_D7_dropping_the_final_applied_entry_is_detected(inited):
    to_applied(inited)
    f = inited.lsf_dir / "stops.jsonl"
    lines = f.read_text().splitlines()
    f.write_text("\n".join(lines[:-1]) + "\n")
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in out(p)


def test_D7_deleting_the_recorded_entry_between_answer_and_applied_is_detected(inited):
    to_applied(inited)
    f = inited.lsf_dir / "stops.jsonl"
    lines = f.read_text().splitlines()
    f.write_text("\n".join(lines[:2] + lines[3:]) + "\n")
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in out(p)


def test_D7_hand_forged_applied_line_is_rejected(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    answer(inited, "d", "Alpha")
    f = inited.lsf_dir / "stops.jsonl"
    forged = {"kind": "applied", "type": "applied", "name": "d", "evidence": "x", "applied_evidence": "x",
              "at": "2026-10-20T10:00:00Z", "hash": STALE, "prev": STALE}
    with open(f, "a") as fh:
        fh.write(json.dumps(forged) + "\n")
    p = inited.run("hitl", "status")
    assert p.returncode == 1 and "stop ledger failed verification" in out(p)


def test_D1_old_ledger_entries_without_new_fields_still_verify_and_derive(rig, old_lsf):
    rig.init()
    env = dict(rig.env)

    def old(*a):
        return subprocess.run([PY, str(old_lsf), *a], cwd=str(rig.repo), env=env, capture_output=True, text=True)

    assert old("hitl", "request", "legacy-open", "--question", "q1").returncode == 0
    assert old("hitl", "request", "legacy-done", "--question", "q2").returncode == 0
    assert old("hitl", "release", "legacy-done", "--note", "fine", "--by", "me").returncode == 0
    lines = rig.stop_lines()
    assert len(lines) == 3 and "proposal_hash" not in "".join(lines)
    p, data = rig.hitl()
    assert p.returncode == 3, out(p)
    assert rig.stop("legacy-open")["state"] == "asked"
    done = rig.stop("legacy-done")
    assert done["state"] == "answered" and done["id"] == "legacy-done"
    # new commands extend an old chain
    assert rig.run("hitl", "release", "legacy-open").returncode == 0
    rig.write("docs/rec.md", "x\n")
    assert record(rig, "legacy-done", "docs/rec.md").returncode == 0
    assert apply_(rig, "legacy-done", "ok").returncode == 0
    p = rig.run("hitl", "status")
    assert p.returncode == 0 and "failed verification" not in out(p)
    assert rig.stop("legacy-done")["state"] == "applied" and rig.stop("legacy-open")["state"] == "answered"
    assert rig.stop_lines()[:3] == lines


# ------------------------------------------------------------------ D-8 status text and exit code
def test_D8_status_text_prints_state_per_stop(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "one")
    ask_ok(inited, "two")
    ask_ok(inited, "three")
    answer(inited, "two", "Alpha")
    answer(inited, "three", "Alpha")
    record(inited, "three", "docs/rec.md")
    p = inited.run("hitl", "status")
    assert p.returncode == 3
    lines = {n: next(l for l in p.stdout.splitlines() if n in l) for n in ("one", "two", "three")}
    assert "asked" in lines["one"].lower()
    assert "answered" in lines["two"].lower()
    assert "recorded" in lines["three"].lower()


@pytest.mark.parametrize("upto,code", [("asked", 3), ("answered", 0), ("recorded", 0), ("applied", 0)])
def test_D8_exit_3_only_while_asked(inited, upto, code):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    if upto != "asked":
        answer(inited, "d", "Alpha")
    if upto in ("recorded", "applied"):
        record(inited, "d", "docs/rec.md")
    if upto == "applied":
        apply_(inited, "d", "ok")
    assert inited.run("hitl", "status").returncode == code
    assert inited.run("hitl", "status", "--json").returncode == code


def test_D8_exit_3_while_any_one_stop_is_asked_among_finished_ones(inited):
    to_applied(inited)
    assert inited.run("hitl", "status").returncode == 0
    ask_ok(inited, "next")
    assert inited.run("hitl", "status").returncode == 3
    answer(inited, "next", "Beta")
    assert inited.run("hitl", "status").returncode == 0


def test_D8_phase_start_is_blocked_only_by_asked_stops(inited):
    ask_ok(inited, "d")
    assert inited.phase("start", "0-intake", 0).returncode == 3
    answer(inited, "d", "Alpha")
    assert inited.phase("start", "0-intake", 1).returncode == 0


# ------------------------------------------------------------------ D-10 never claim applied early
def test_D10_no_cli_output_says_applied_before_an_applied_entry(inited):
    inited.write("docs/rec.md", "x\n")
    outputs = []
    outputs.append(ask_ok(inited, "d", ["Alpha", "Beta"]))
    outputs.append(inited.run("hitl", "status"))
    outputs.append(inited.run("status"))
    outputs.append(answer(inited, "d", "Alpha"))
    outputs.append(inited.run("hitl", "status"))
    outputs.append(inited.run("status"))
    outputs.append(record(inited, "d", "docs/rec.md", "--note", "stored"))
    outputs.append(inited.run("hitl", "status"))
    outputs.append(inited.run("status"))
    for p in outputs:
        # "not applied yet" is the honest wording D-9 requires; only a claim of being applied is forbidden
        assert "applied" not in out(p).lower().replace("not applied", ""), out(p)


def test_D10_no_early_applied_in_events_or_state(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    answer(inited, "d", "Alpha")
    record(inited, "d", "docs/rec.md")
    assert not [e for e in inited.events() if "applied" in json.dumps(e).lower()]
    assert inited.stop("d")["state"] != "applied" and not inited.stop("d")["applied_evidence"]
    apply_(inited, "d", "proof")
    assert [e for e in inited.events() if e.get("verdict") == "applied"]


def test_D10_failed_apply_attempts_never_flip_state(inited):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    apply_(inited, "d", "premature")
    answer(inited, "d", "Alpha")
    apply_(inited, "d", "premature")
    record(inited, "d", "docs/rec.md")
    apply_(inited, "d", "")
    assert inited.stop("d")["state"] == "recorded"


# ------------------------------------------------------------------ D-12 pending comes from the live ledger
def test_D12_bundle_snapshot_never_resurrects_a_pending_decision(inited):
    ask_ok(inited, "d")
    inited.run("bundle", "--json", timeout=30)
    answer(inited, "d", "Alpha")
    assert inited.run("hitl", "status").returncode == 0
    inited.run("bundle", "--json", timeout=30)
    assert inited.stop("d")["state"] == "answered"
    assert inited.run("hitl", "status").returncode == 0
