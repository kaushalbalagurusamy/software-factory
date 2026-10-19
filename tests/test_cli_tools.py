"""`sf <tool>` delegates to the factory tool modules and propagates their exit codes."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GROUPS = ["slice", "structure", "contracts", "intake", "ops", "qa"]


def sf(*args):
    code = "import sys; from factory.cli import main; sys.exit(main(sys.argv[1:]))"
    return subprocess.run([sys.executable, "-c", code, *args], cwd=REPO, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("group", GROUPS)
def test_group_help_exits_zero_and_shows_usage(group):
    r = sf(group, "--help")
    assert r.returncode == 0, r.stderr
    assert "usage" in (r.stdout + r.stderr).lower()


def test_unknown_subcommand_of_a_tool_is_a_usage_error_not_a_pass():
    assert sf("slice", "no-such-command").returncode != 0


def test_exit_code_of_the_tool_is_propagated(tmp_path):
    r = sf("slice", "check", str(tmp_path / "missing-slice"))
    assert r.returncode != 0


def test_existing_commands_still_work():
    assert sf("audit", "--help").returncode == 0
