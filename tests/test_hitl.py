"""Human stop: request/status/release, hash-chained log, tamper detection, done/next integration."""
import json
import shutil
from pathlib import Path

import pytest

from factory.hitl.__main__ import main as hitl
from factory.qa.cli import main as qa_main
from factory.slices.cli import main as slices_main

FIX = Path(__file__).resolve().parent / "fixtures"
OK, ERR, USAGE, OPEN, TAMPER, REFUSED = 0, 1, 2, 3, 4, 5


def run(root, *a):
    return hitl([a[0], "--root", str(root), *a[1:]])


def test_request_writes_file_and_status_exits_3(tmp_path, capsys):
    assert run(tmp_path, "request", "--name", "db", "--reason", "need owner", "--scope", "slice:s1") == OK
    rec = json.loads((tmp_path / ".sf/stops/db.json").read_text())
    assert {"name", "scope", "reason", "requested_at", "requested_by"} <= set(rec)
    assert rec["scope"] == "slice:s1"
    assert run(tmp_path, "status") == OPEN
    assert "db" in capsys.readouterr().out


def test_scope_matching(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "slice:s1")
    assert run(tmp_path, "status", "--scope", "slice:s2") == OK
    assert run(tmp_path, "status", "--scope", "slice:s1") == OPEN
    run(tmp_path, "request", "--name", "g", "--reason", "r", "--scope", "run")
    assert run(tmp_path, "status", "--scope", "slice:s2") == OPEN  # a run stop applies to every slice


def test_release_by_human_ends_stop(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    assert run(tmp_path, "release", "--name", "a", "--by", "human:kaushal") == OK
    assert run(tmp_path, "status") == OK


@pytest.mark.parametrize("by", ["agent:implementer", "subagent:review", "codex:x1", "claude", "human:", ""])
def test_release_by_non_human_refused(tmp_path, capsys, by):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    assert run(tmp_path, "release", "--name", "a", "--by", by) == REFUSED
    assert run(tmp_path, "status") == OPEN
    assert "human:" in capsys.readouterr().err


def test_agent_refusal_names_the_actor_kind(tmp_path, capsys):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    run(tmp_path, "release", "--name", "a", "--by", "subagent:review")
    assert "subagent" in capsys.readouterr().err


def test_editing_stop_file_cannot_release(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    (tmp_path / ".sf/stops/a.json").unlink()
    assert run(tmp_path, "status") == TAMPER


def test_rewriting_stop_file_is_tamper(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    p = tmp_path / ".sf/stops/a.json"
    p.write_text(p.read_text().replace('"run"', '"slice:zzz"'))
    assert run(tmp_path, "status") == TAMPER


def test_log_edit_and_truncation_detected(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    run(tmp_path, "request", "--name", "b", "--reason", "r")
    run(tmp_path, "release", "--name", "a", "--by", "human:x")
    log = tmp_path / ".sf/stops/log.jsonl"
    good = log.read_text()
    lines = good.splitlines()
    # editing a middle entry breaks the chain
    bad = json.loads(lines[1]); bad["by"] = "human:forged"
    log.write_text("\n".join([lines[0], json.dumps(bad), lines[2]]) + "\n")
    assert run(tmp_path, "status") == TAMPER
    # removing a middle entry breaks the chain
    log.write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert run(tmp_path, "status") == TAMPER
    log.write_text(good)
    assert run(tmp_path, "status") == OPEN  # b is still open


def test_forged_release_line_without_valid_hash_is_tamper(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    log = tmp_path / ".sf/stops/log.jsonl"
    with log.open("a") as f:
        f.write(json.dumps({"seq": 2, "event": "release", "name": "a", "by": "human:x"}) + "\n")
    assert run(tmp_path, "status") == TAMPER


def test_duplicate_open_request_and_unknown_release_are_usage_errors(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    assert run(tmp_path, "request", "--name", "a", "--reason", "again") == USAGE
    assert run(tmp_path, "release", "--name", "nope", "--by", "human:x") == USAGE


def test_bad_names_and_scopes_rejected(tmp_path):
    assert run(tmp_path, "request", "--name", "../x", "--reason", "r") == USAGE
    assert run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "weird") == USAGE


def test_rerequest_after_release(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    run(tmp_path, "release", "--name", "a", "--by", "human:x")
    assert run(tmp_path, "request", "--name", "a", "--reason", "again") == OK
    assert run(tmp_path, "status") == OPEN


# ---- integration


@pytest.fixture
def slice_dir(tmp_path):
    d = tmp_path / "docs" / "slices" / "demo-login"
    shutil.copytree(FIX / "slices" / "docs" / "slices" / "demo-login", d)
    assert slices_main(["lock", str(d)]) == 0
    for t in ("1.1", "1.2"):
        assert slices_main(["tick", str(d), t, "--role", "implementer"]) == 0
        assert slices_main(["verify", str(d), t, "--role", "qa", "--evidence", "e", "--commit", "abc"]) == 0
    return d


def test_done_passes_without_stop_and_fails_with_stop(slice_dir, tmp_path, capsys):
    assert slices_main(["done", str(slice_dir)]) == 0
    run(tmp_path, "request", "--name", "ux", "--reason", "owner must look", "--scope", "slice:demo-login")
    assert slices_main(["done", str(slice_dir)]) == 5
    assert "ux" in capsys.readouterr().out
    run(tmp_path, "release", "--name", "ux", "--by", "human:o")
    assert slices_main(["done", str(slice_dir)]) == 0


def test_done_run_scope_and_other_slice_scope(slice_dir, tmp_path):
    run(tmp_path, "request", "--name", "other", "--reason", "r", "--scope", "slice:something-else")
    assert slices_main(["done", str(slice_dir)]) == 0
    run(tmp_path, "request", "--name", "all", "--reason", "r", "--scope", "run")
    assert slices_main(["done", str(slice_dir)]) == 5


def test_done_fails_closed_on_tampered_ledger(slice_dir, tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "slice:demo-login")
    (tmp_path / ".sf/stops/a.json").unlink()
    assert slices_main(["done", str(slice_dir)]) == 5


def test_done_explicit_root(slice_dir, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    run(other, "request", "--name", "a", "--reason", "r", "--scope", "run")
    assert slices_main(["done", str(slice_dir), "--root", str(other)]) == 5


@pytest.fixture
def proj(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text("paths:\n  eval: [evals/**]\n")
    return tmp_path


def qa(proj, *a):
    return qa_main(["--root", str(proj), "--slice", "s1", *a])


def test_next_returns_human_stop_and_never_applies(proj, capsys):
    assert qa(proj, "init", "--criteria", "AC-1.1") == 0
    qa(proj, "record", "--status", "fail", "--case", "c", "--criterion", "AC-1.1", "--error", "boom", "--tier", "sonnet")
    capsys.readouterr()
    run(proj, "request", "--name", "ux", "--reason", "owner", "--scope", "slice:s1")
    capsys.readouterr()
    assert qa(proj, "next", "--apply") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "human_stop" and out["stops"] == ["ux"]
    state = json.loads((proj / ".sf/slices/s1/state.json").read_text())
    assert state["status"] not in ("blocked", "stuck", "accepted")
    run(proj, "release", "--name", "ux", "--by", "human:o")
    capsys.readouterr()
    qa(proj, "next")
    assert json.loads(capsys.readouterr().out)["action"] != "human_stop"


def test_next_human_stop_on_tamper(proj, capsys):
    qa(proj, "init", "--criteria", "AC-1.1")
    run(proj, "request", "--name", "ux", "--reason", "o", "--scope", "run")
    (proj / ".sf/stops/ux.json").unlink()
    capsys.readouterr()
    assert qa(proj, "next") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "human_stop" and "tamper" in out["reason"].lower()
