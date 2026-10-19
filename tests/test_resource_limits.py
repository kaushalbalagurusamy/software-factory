"""The repo-wide resource limits must turn a runaway test into a recorded FAILURE, never a pass or a host OOM."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_pytest(tmp_path, test_src, quiet=True, **env):
    shutil.copy(REPO / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_x.py").write_text(test_src)
    e = {**os.environ, **{k: str(v) for k, v in env.items()}}
    return subprocess.run([sys.executable, "-m", "pytest", *(["-q"] if quiet else []), "-p", "no:cacheprovider", "test_x.py"],
                          cwd=tmp_path, capture_output=True, text=True, env=e, timeout=90)


def test_memory_cap_turns_a_runaway_allocation_into_a_failure(tmp_path):
    # Touch pages: macOS may reserve a large zero-filled allocation lazily,
    # which consumes virtual address space without exceeding an RSS limit.
    r = run_pytest(tmp_path, "import time\ndef test_hog():\n    x = bytearray(1500 * 1024 * 1024)\n    for i in range(0, len(x), 4096):\n        x[i] = 1\n    time.sleep(2)\n    assert len(x)\n", SF_TEST_MEM_MB=600)
    assert r.returncode != 0
    if sys.platform == "darwin":
        assert r.returncode == 137
        assert "resource limit: pytest process-tree memory exceeded 600 MB; exit 137" in (
            tmp_path / ".sf/resource-limits.log").read_text()
    else:
        assert "MemoryError" in r.stdout and "1 failed" in r.stdout


def test_timeout_is_a_failure_with_an_explicit_message(tmp_path):
    r = run_pytest(tmp_path, "import time\ndef test_slow():\n    time.sleep(30)\n", SF_TEST_TIMEOUT_S=2)
    assert r.returncode != 0
    assert "resource limit: test exceeded 2 s" in r.stdout and "1 failed" in r.stdout


def test_limits_are_recorded_in_the_header_and_normal_tests_pass(tmp_path):
    r = run_pytest(tmp_path, "def test_ok():\n    assert 1 + 1 == 2\n", quiet=False, SF_TEST_MEM_MB=2048, SF_TEST_TIMEOUT_S=30)
    assert r.returncode == 0
    kind = "sampled process-tree RSS" if sys.platform == "darwin" else "address space"
    assert f"resource limits: {kind} 2048 MB, per-test timeout 30 s" in r.stdout


def test_wrapper_kills_on_wall_clock_records_limits_and_is_not_a_pass(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "bounded-pytest.sh", repo / "scripts" / "bounded-pytest.sh")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "test_x.py").write_text("import time\ndef test_slow():\n    time.sleep(60)\n")
    env = {**os.environ, "SF_TEST_WALL_S": "3", "SF_TEST_TIMEOUT_S": "0", "SF_PYTHON": sys.executable,
           "SF_TEST_LOCK": str(tmp_path / "lock")}
    r = subprocess.run(["bash", str(repo / "scripts" / "bounded-pytest.sh"), "-q", "-p", "no:cacheprovider", "test_x.py"],
                       cwd=repo, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode != 0
    assert "not a pass" in r.stderr
    assert "wall_s=3" in (repo / ".sf" / "resource-limits.log").read_text()
