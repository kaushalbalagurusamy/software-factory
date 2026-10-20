"""SFN-03 unit tests: `qa promote-notes`."""
import os
import shutil
from pathlib import Path

import pytest

from factory.qa.cli import main

FIX = Path(__file__).resolve().parent / "fixtures"
OK, ERR = 0, 1


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "evals").mkdir()
    shutil.copy(FIX / "qa" / "protected_eval.py", tmp_path / "evals" / "test_login.py")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory/profile.yaml").write_text("paths:\n  eval: [evals/**]\n")
    (tmp_path / "docs/slices/s1").mkdir(parents=True)
    return tmp_path


def qa(proj, *a):
    return main(["--root", str(proj), "--slice", "s1", *a])


def fail_twice(proj):
    assert qa(proj, "init", "--criteria", "AC-1") == OK
    for rerun in (False, True, False, True):
        extra = ["--rerun"] if rerun else []
        assert qa(proj, "record", "--status", "fail", "--case", "AC-1", "--error", "HTTP 500 at 12:00", *extra) == OK
    assert qa(proj, "feedback", "--criterion", "AC-1", "--observed", "HTTP 500", "--expected", "HTTP 401 returned",
              "--repro", "curl localhost/login") == OK


def promote(proj, *a):
    return main(["--root", str(proj), "promote-notes", "--slice", str(proj / "docs/slices/s1"), *a])


def test_notes_written_and_deterministic(proj, capsys):
    fail_twice(proj)
    assert promote(proj) == OK
    f = proj / "docs/slices/s1/qa-notes.md"
    text = f.read_text()
    assert "## Signature " in text and "attempts 2" in text and "AC-1" in text
    assert "HTTP <N>" in text and "HTTP 401 returned" in text and "proposal" in text
    mtime = f.stat().st_mtime_ns
    assert promote(proj) == OK
    assert f.read_text() == text and f.stat().st_mtime_ns == mtime


def test_missing_log_names_sf(proj, capsys):
    assert promote(proj) == ERR
    assert ".sf" in capsys.readouterr().err
    assert not (proj / "docs/slices/s1/qa-notes.md").exists()


def test_leak_refused_without_echo(proj, capsys):
    secret = Path(proj / "evals/test_login.py").read_text().splitlines()
    line = next(l.strip() for l in secret if len(l.strip()) >= 20)
    assert qa(proj, "init", "--criteria", "AC-1") == OK
    for rerun in (False, True):
        assert qa(proj, "record", "--status", "fail", "--case", "AC-1", "--error", line, *(["--rerun"] if rerun else [])) == OK
    assert promote(proj) == ERR
    err = capsys.readouterr().err
    assert line not in err and not (proj / "docs/slices/s1/qa-notes.md").exists()


def test_symlink_and_outside_refused(proj, tmp_path_factory, capsys):
    fail_twice(proj)
    out = tmp_path_factory.mktemp("elsewhere")
    assert main(["--root", str(proj), "promote-notes", "--slice", str(out / "s1")]) == ERR
    assert "outside" in capsys.readouterr().err
    os.symlink(out, proj / "docs/slices/link")
    assert main(["--root", str(proj), "promote-notes", "--slice", str(proj / "docs/slices/link")]) == ERR
    assert "symlink" in capsys.readouterr().err
    os.symlink(out / "x.md", proj / "docs/slices/s1/qa-notes.md")
    assert promote(proj) == ERR and not (out / "x.md").exists()
