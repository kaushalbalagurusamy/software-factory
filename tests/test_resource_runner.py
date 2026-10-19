"""The bounded runner must work without Linux-only executable dependencies."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(tmp_path, code, *, memory=256, wall=5):
    return subprocess.run(
        [sys.executable, "-m", "factory.resource_limits", "--memory-mb", str(memory),
         "--wall-s", str(wall), "--lock", str(tmp_path / "lock"), "--",
         sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=15,
    )


def test_preserves_command_exit_status(tmp_path):
    assert run(tmp_path, "raise SystemExit(7)").returncode == 7


def test_success_does_not_need_linux_utilities(tmp_path):
    result = run(tmp_path, "print('completed')")
    assert result.returncode == 0, result.stderr
    assert "completed" in result.stdout


def test_timeout_is_failure(tmp_path):
    result = run(tmp_path, "import time; time.sleep(10)", wall=0.4)
    assert result.returncode == 124
    assert "wall-clock" in result.stderr


def test_descendant_memory_is_bounded(tmp_path):
    code = ("import subprocess,sys; subprocess.run([sys.executable, '-c', "
            "'import time; data=bytearray(160*1024*1024); time.sleep(10)'])")
    result = run(tmp_path, code, memory=96)
    assert result.returncode == 137, result.stderr
    assert "memory" in result.stderr


def test_serializes_runs_with_a_shared_lock(tmp_path):
    lock = tmp_path / "lock"
    import fcntl
    with lock.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = subprocess.run(
            [sys.executable, "-m", "factory.resource_limits", "--lock", str(lock),
             "--lock-wait-s", "0.2", "--", sys.executable, "-c", "print('must not run')"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
    assert result.returncode == 124
    assert "must not run" not in result.stdout
    assert "lock" in result.stderr
