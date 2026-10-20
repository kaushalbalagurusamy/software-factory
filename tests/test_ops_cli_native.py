"""Unit tests for the sf-command events and `sf ops init|backfill|status|autobundle` (SFN-01). Unit coverage, not the gate."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from factory import cli  # noqa: E402


def events(root):
    p = Path(root) / "ops" / "events.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def proj(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SF_EVENTS", raising=False)
    return tmp_path


@pytest.fixture
def fake_tool(tmp_path_factory, monkeypatch):
    """Replace every tool group with a module that exits with $FAKE_EXIT."""
    d = tmp_path_factory.mktemp("fake")
    (d / "fake_tool.py").write_text("import os, sys\nsys.exit(int(os.environ.get('FAKE_EXIT', '0')))\n")
    monkeypatch.syspath_prepend(str(d))
    for g in list(cli.TOOL_GROUPS):
        monkeypatch.setitem(cli.TOOL_GROUPS, g, "fake_tool")


@pytest.mark.parametrize("argv,stage,slice_id", [
    (["intake", "check", "--x", "y"], "0-intake", "-"),
    (["intake", "gate", "--slice", "docs/s/"], "0-intake", "s"),
    (["intake", "experiments", "check"], "0-intake", "-"),
    (["slice", "check", "docs/slices/alpha"], "4-slice", "alpha"),
    (["slice", "triage", "--root", "docs/slices"], "4-slice", "-"),
    (["slice", "lock", "docs/slices/alpha/"], "5-evals", "alpha"),
    (["slice", "tick", "docs/slices/b", "T1", "--role", "implementer"], "6-implement", "b"),
    (["slice", "verify", "--role", "qa", "docs/slices/b", "T1"], "7-qa", "b"),
    (["slice", "amend", "docs/slices/b"], "8-review", "b"),
    (["slice", "done", "docs/slices/b"], "9-drift", "b"),
    (["qa", "--slice", "x/qq", "state"], "7-qa", "qq"),
    (["contracts", "check-contracts"], "4c-contracts", "-"),
    (["contracts", "verify"], "8-gate", "-"),
    (["structure", "diff", "a", "b"], "8-gate", "-"),
    (["structure", "scan"], "4b-structure", "-"),
    (["ops", "bundle"], "11-commit", "-"),
])
def test_stage_mapping_and_slice(proj, fake_tool, monkeypatch, argv, stage, slice_id):
    monkeypatch.setenv("FAKE_EXIT", "1")
    assert cli.main(argv) == 1
    (e,) = events(proj)
    assert (e["stage"], e["slice"], e["verdict"], e["note"], e["source"]) == (stage, slice_id, "fail", "exit=1", "sf")


@pytest.mark.parametrize("argv", [
    ["contracts", "report"], ["hitl", "status"], ["ops", "runtime"], ["ops", "serve"], ["slice", "--help"],
    ["slice", "check", "-h"], ["install", "doctor"], ["slice"],
])
def test_quiet_commands(proj, fake_tool, argv):
    assert cli.main(argv) == 0
    assert events(proj) == []


def test_pass_usage_error_and_exit_code_unchanged(proj, fake_tool, monkeypatch):
    assert cli.main(["slice", "lock", "d"]) == 0
    assert events(proj)[0]["verdict"] == "pass" and events(proj)[0]["note"] == "exit=0"
    monkeypatch.setenv("FAKE_EXIT", "2")
    assert cli.main(["slice", "lock", "d"]) == 2
    monkeypatch.setenv("FAKE_EXIT", "7")
    assert cli.main(["qa", "state"]) == 7
    assert len(events(proj)) == 2


def test_hitl_verdicts(proj, fake_tool, monkeypatch):
    cli.main(["hitl", "request", "--name", "n"])
    cli.main(["hitl", "release", "--name", "n"])
    monkeypatch.setenv("FAKE_EXIT", "5")
    assert cli.main(["hitl", "release", "--name", "n"]) == 5
    assert [(e["stage"], e["verdict"], e["note"]) for e in events(proj)] == [
        ("hitl", "open", "exit=0"), ("hitl", "released", "exit=0"), ("hitl", "fail", "exit=5")]


def test_telemetry_failure_never_changes_exit(proj, fake_tool, monkeypatch, capsys):
    (proj / "ops").write_text("not a directory")
    assert cli.main(["slice", "lock", "d"]) == 0
    assert "event not recorded" in capsys.readouterr().err
    monkeypatch.setenv("SF_EVENTS", "off")
    assert cli.main(["slice", "lock", "d"]) == 0
