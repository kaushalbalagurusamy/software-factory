"""Launcher behavior without calling a model or relying on a shell alias."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "skills/lsf/scripts/launch.py"


def load():
    spec = importlib.util.spec_from_file_location("lsf_launch", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_starts_the_requested_services_without_inventing_work():
    command, env = load().prepare([], "/usr/local/bin/claude", Path("/tmp/example"), {})
    assert command[:3] == ["/usr/local/bin/claude", "--dangerously-skip-permissions", "--remote-control"]
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[-2] == "--"
    assert command[-1].startswith("/lsf\n")
    assert "away-mode" in command[-1]
    assert "before initializing the phase clock" in command[-1]
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] == "1"


def test_explicit_interview_model_applies_to_subagents_too():
    command, env = load().prepare(["--model", "opus", "--name", "Interview"], "claude", Path("/tmp/x"), {})
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--name") + 1] == "Interview"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "opus"


def test_preserves_task_as_data_and_never_uses_shell_interpolation():
    text = "Handle spaces and $(touch /tmp/never) literally"
    command, _ = load().prepare([text], "claude", Path("/tmp/my repo"), {})
    assert text in command[-1]
    assert command[0] == "claude"


def test_subscription_launcher_removes_api_credentials_and_inherited_model():
    command, env = load().prepare([], "claude", Path("/tmp/x"), {
        "ANTHROPIC_API_KEY": "fake", "ANTHROPIC_AUTH_TOKEN": "fake",
        "ANTHROPIC_MODEL": "opus", "PATH": "/bin", "KEEP_ME": "yes",
    })
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_MODEL" not in env
    assert env["KEEP_ME"] == "yes"


def test_unrecognized_options_fail_instead_of_becoming_task_text():
    with pytest.raises(SystemExit):
        load().prepare(["--typo"], "claude", Path("/tmp/x"), {})


def test_exec_path_keeps_arguments_and_exit_status(tmp_path):
    import json
    import subprocess
    fake = tmp_path / 'fake-claude'
    fake.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                    'print(json.dumps({"args": sys.argv[1:], "api": '
                    '"ANTHROPIC_API_KEY" in os.environ}))\nsys.exit(7)\n')
    fake.chmod(0o755)
    env = dict(os.environ, CLAUDE_LSF_BIN=str(fake), ANTHROPIC_API_KEY='fake')
    result = subprocess.run([sys.executable, str(SOURCE), '--name', 'A B',
                             'literal $(touch nope)'], env=env, capture_output=True, text=True)
    assert result.returncode == 7
    data = json.loads(result.stdout)
    assert data['args'][data['args'].index('--name') + 1] == 'A B'
    assert 'literal $(touch nope)' in data['args'][-1]
    assert data['api'] is False
