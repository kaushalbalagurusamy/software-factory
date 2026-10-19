"""Human stop: request/status/release, hash-chained log, tamper detection, done/next integration."""
import json
import shutil
from pathlib import Path

import pytest

from factory.hitl import store
from factory.hitl.__main__ import main as hitl
from factory.qa.cli import main as qa_main
from factory.slices.cli import main as slices_main

FIX = Path(__file__).resolve().parent / "fixtures"
OK, ERR, USAGE, OPEN, TAMPER, REFUSED = 0, 1, 2, 3, 4, 5


@pytest.fixture(autouse=True)
def _tty(monkeypatch):
    """Pytest has no terminal; tests of the release path pretend there is one (the gate has its own tests)."""
    monkeypatch.setattr(store, "interactive_terminal", lambda: True)


def run(root, *a):
    return hitl([a[0], "--root", str(root), *a[1:]])


def test_request_writes_file_and_status_exits_3(tmp_path, capsys):
    assert run(tmp_path, "request", "--name", "db", "--reason", "need owner", "--scope", "slice:s1") == OK
    rec = json.loads((tmp_path / ".factory/stops/db.json").read_text())
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
    (tmp_path / ".factory/stops/a.json").unlink()
    assert run(tmp_path, "status") == TAMPER


def test_rewriting_stop_file_is_tamper(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    p = tmp_path / ".factory/stops/a.json"
    p.write_text(p.read_text().replace('"run"', '"slice:zzz"'))
    assert run(tmp_path, "status") == TAMPER


def test_log_edit_and_truncation_detected(tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    run(tmp_path, "request", "--name", "b", "--reason", "r")
    run(tmp_path, "release", "--name", "a", "--by", "human:x")
    log = tmp_path / ".factory/stops/log.jsonl"
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
    log = tmp_path / ".factory/stops/log.jsonl"
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
    (tmp_path / ".factory/stops/a.json").unlink()
    assert slices_main(["done", str(slice_dir)]) == 5


def test_done_rejects_root_that_is_not_an_ancestor(slice_dir, tmp_path, capsys):
    run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "run")
    empty = tmp_path.parent / (tmp_path.name + "-empty")
    empty.mkdir()
    assert slices_main(["done", str(slice_dir), "--root", str(empty)]) == 5  # the bypass attempt
    assert "not an ancestor" in capsys.readouterr().out


def test_done_ancestor_root_cannot_hide_the_real_ledger(slice_dir, tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "run")
    assert slices_main(["done", str(slice_dir), "--root", str(tmp_path.parent)]) == 5


def test_empty_ledger_planted_deeper_does_not_shadow(slice_dir, tmp_path):
    run(tmp_path, "request", "--name", "a", "--reason", "r", "--scope", "run")
    (slice_dir / ".factory" / "stops").mkdir(parents=True)
    assert slices_main(["done", str(slice_dir)]) == 5


def test_done_fails_closed_on_unreadable_ledger(slice_dir, tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "stops").write_text("a file, not a directory")
    assert slices_main(["done", str(slice_dir)]) == 5


def test_qa_next_sees_ledger_above_state_root(proj, capsys):
    sub = proj / "work"
    sub.mkdir()
    run(proj, "request", "--name", "a", "--reason", "r", "--scope", "run")
    assert qa_main(["--root", str(sub), "--slice", "s1", "init", "--criteria", "AC-1"]) == 0
    capsys.readouterr()
    qa_main(["--root", str(sub), "--slice", "s1", "next"])
    assert json.loads(capsys.readouterr().out)["action"] == "human_stop"


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
    (proj / ".factory/stops/ux.json").unlink()
    capsys.readouterr()
    assert qa(proj, "next") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "human_stop" and "tamper" in out["reason"].lower()


# ---- terminal gate

def test_release_refused_without_tty_probe(tmp_path):
    store.request(tmp_path, "a", "r")
    for probe in (lambda: False,):
        with pytest.raises(store.ReleaseRefused, match="released by a person at a terminal"):
            store.release(tmp_path, "a", "human:o", tty_probe=probe)
    assert store.blocking(tmp_path)
    store.release(tmp_path, "a", "human:o", tty_probe=lambda: True)
    assert not store.blocking(tmp_path)


def test_cli_release_exit_5_when_not_a_terminal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "interactive_terminal", lambda: False)
    run(tmp_path, "request", "--name", "a", "--reason", "r")
    assert run(tmp_path, "release", "--name", "a", "--by", "human:o") == REFUSED
    assert "released by a person at a terminal" in capsys.readouterr().err
    assert run(tmp_path, "status") == OPEN


def test_real_stdio_under_pytest_is_not_a_terminal(monkeypatch):
    monkeypatch.undo()
    import sys
    if sys.stdin.isatty() and sys.stdout.isatty():
        pytest.skip("run from a terminal with -s")  # the probe is exercised by the pty test below
    assert store.interactive_terminal() is False


def test_real_pty_is_accepted_known_limit(tmp_path):
    """Known limit: a pty passes the gate, so an agent could allocate one. Friction, not proof."""
    import os
    import pty
    import subprocess
    import sys
    store.request(tmp_path, "a", "r")
    master, slave = pty.openpty()
    try:
        r = subprocess.run([sys.executable, "-m", "factory.hitl", "release", "--root", str(tmp_path),
                            "--name", "a", "--by", "human:o"], stdin=slave, stdout=slave,
                           stderr=subprocess.PIPE, env=dict(os.environ, PYTHONPATH=str(Path(store.__file__).parents[2])),
                           timeout=60)
    finally:
        os.close(master); os.close(slave)
    assert r.returncode == 0, r.stderr
    assert not store.blocking(tmp_path)


# ---- store location and legacy entries

def test_store_lives_under_factory_and_never_writes_sf(tmp_path):
    store.request(tmp_path, "a", "r")
    assert (tmp_path / ".factory/stops/log.jsonl").is_file() and not (tmp_path / ".sf").exists()


def _legacy(tmp_path, scope="run"):
    leg = tmp_path / "legacy"
    store.request(leg, "old", "r", scope)
    (tmp_path / ".sf").mkdir(exist_ok=True)
    (leg / ".factory/stops").rename(tmp_path / ".sf/stops")
    shutil.rmtree(leg)


def test_legacy_stop_is_read_reported_and_blocks(tmp_path, capsys):
    _legacy(tmp_path)
    assert run(tmp_path, "status") == OPEN
    assert "legacy" in capsys.readouterr().out
    before = sorted(x.name for x in (tmp_path / ".sf/stops").iterdir())
    assert run(tmp_path, "request", "--name", "old", "--reason", "x") == USAGE  # name already open
    assert run(tmp_path, "release", "--name", "old", "--by", "human:o") == USAGE  # read-only
    assert run(tmp_path, "request", "--name", "new", "--reason", "x") == OK
    assert not (tmp_path / ".sf/stops/new.json").exists()
    assert sorted(x.name for x in (tmp_path / ".sf/stops").iterdir()) == before


def test_tampered_legacy_ledger_fails_closed(tmp_path):
    _legacy(tmp_path)
    (tmp_path / ".sf/stops/old.json").unlink()
    assert run(tmp_path, "status") == TAMPER


def test_qa_next_sees_legacy_stop(proj, capsys):
    qa(proj, "init", "--criteria", "AC-1.1")
    _legacy(proj, "slice:s1")
    capsys.readouterr()
    qa(proj, "next")
    assert json.loads(capsys.readouterr().out)["action"] == "human_stop"
