"""
Tests for Software Factory Bare-Metal CLI Runner.
"""

from pathlib import Path
import pytest
from factory.cli import main

UNITY_EXAMPLES_DIR = Path("/Users/kaushal/Documents/Github/unity/examples/ledger")
LEDGER_PY = UNITY_EXAMPLES_DIR / "ledger.py"


def test_cli_audit_identical_files(capsys):
    ret = main(["audit", "--pre", str(LEDGER_PY), "--post", str(LEDGER_PY)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "TWO-WAY DOOR" in captured.out
    assert "Autonomous Execution Permitted" in captured.out


def test_cli_audit_one_way_door(tmp_path: Path, capsys):
    orig = LEDGER_PY.read_text()
    mutated = orig.replace("with self.mu:", "if True:")
    mutated_file = tmp_path / "unsafe.py"
    mutated_file.write_text(mutated)


    ret = main(["audit", "--pre", str(LEDGER_PY), "--post", str(mutated_file), "--strict"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "ONE-WAY DOOR" in captured.out
    assert "Concurrency Synchronization Shift" in captured.out
    assert "ADR" in captured.out


def test_cli_verify_record_and_check(tmp_path: Path, capsys):
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_sample.py").write_text("def test_one():\n    assert 1 == 1\n")
    manifest = tmp_path / "manifest.json"

    # Record baseline
    ret_record = main(["verify", "--repo", str(tmp_path), "--manifest", str(manifest), "--record"])
    assert ret_record == 0
    assert manifest.exists()

    # Verify untouched
    ret_verify = main(["verify", "--repo", str(tmp_path), "--manifest", str(manifest)])
    assert ret_verify == 0
    captured = capsys.readouterr()
    assert "PASSED" in captured.out


def test_cli_run_spec_one_way_triage(tmp_path: Path, capsys):
    spec = tmp_path / "feature.md"
    spec.write_text("# Feature\nWe must drop table legacy_users and update database schema.\n")

    ret = main(["run", "--spec", str(spec), "--repo", str(tmp_path)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "ONE-WAY DOOR DETECTED" in captured.out
    assert "Socratic Architectural Debate" in captured.out
