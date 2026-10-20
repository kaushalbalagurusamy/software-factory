"""Unit tests for factory.ops.events.emit and the hook events (SFN-01). Unit coverage, not the gate."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from factory.ops.events import emit  # noqa: E402


def lines(root):
    p = Path(root) / "ops" / "events.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "c"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


@pytest.fixture(autouse=True)
def _events_on(monkeypatch):
    monkeypatch.delenv("SF_EVENTS", raising=False)


def test_emit_writes_one_line_with_keys(tmp_path):
    sha = git_repo(tmp_path)
    assert emit(tmp_path, "7-qa", "s1", "pass", "n", role="qa") is True
    (e,) = lines(tmp_path)
    assert set(e) == {"at", "stage", "slice", "sha", "verdict", "note", "source", "role"}
    assert e["sha"] == sha and e["source"] == "sf" and e["role"] == "qa"
    assert e["at"].endswith("+00:00") and "." not in e["at"]


def test_role_omitted_and_unknown_sha(tmp_path):
    assert emit(tmp_path, "a", "b", "c") is True
    (e,) = lines(tmp_path)
    assert "role" not in e and e["sha"] == "unknown"


def test_note_bounds_controls_surrogates_secrets(tmp_path):
    emit(tmp_path, "a", "b", "c", "x" * 5000)
    emit(tmp_path, "a", "b", "c", "l1\nl2\t\x00end \ud800 ok")
    emit(tmp_path, "a", "b", "c", "key sk-ant-" + "a1" * 20)
    n, c, s = lines(tmp_path)
    assert len(n["note"]) == 2000
    assert c["note"].startswith("l1 l2  end") and "\n" not in c["note"] and "\ud800" not in c["note"]
    assert "sk-ant-" not in s["note"] and "[REDACTED]" in s["note"]


def test_symlink_outside_refused_inside_allowed(tmp_path, capsys):
    root, out = tmp_path / "r", tmp_path / "elsewhere"
    root.mkdir(); out.mkdir()
    (root / "ops").symlink_to(out)
    assert emit(root, "a", "b", "c") is False
    assert not (out / "events.jsonl").exists()
    assert capsys.readouterr().err.startswith("event not recorded: ")
    root2, real = tmp_path / "r2", tmp_path / "r2" / "real"
    real.mkdir(parents=True)
    (root2 / "ops").symlink_to(real)
    assert emit(root2, "a", "b", "c") is True


def test_failure_returns_false_with_one_stderr_line(tmp_path, capsys):
    (tmp_path / "ops").write_text("a file, not a directory")
    assert emit(tmp_path, "a", "b", "c") is False
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("event not recorded: ")


def test_off_switch_is_silent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SF_EVENTS", "off")
    assert emit(tmp_path, "a", "b", "c") is False
    assert not (tmp_path / "ops").exists() and capsys.readouterr().err == ""


def test_missing_trailing_newline_is_repaired(tmp_path):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "events.jsonl").write_text('{"old": 1}')
    emit(tmp_path, "a", "b", "c")
    assert [list(x)[0] for x in lines(tmp_path)] == ["old", "at"]


def test_concurrent_writers_never_interleave(tmp_path):
    def work(i):
        for _ in range(25):
            emit(tmp_path, "s", str(i), "pass", "y" * 500)
    ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(lines(tmp_path)) == 150


def test_shell_script_goes_through_emit(tmp_path):
    git_repo(tmp_path)
    r = subprocess.run([str(REPO / "scripts" / "ops-stage-event.sh"), "10-docs", "sl", "done", "hi"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    (e,) = lines(tmp_path)
    assert (e["stage"], e["slice"], e["verdict"], e["note"]) == ("10-docs", "sl", "done", "hi")
    assert subprocess.run([str(REPO / "scripts" / "ops-stage-event.sh"), "x"], capture_output=True).returncode == 2
