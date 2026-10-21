"""Repo-wide resource limits for every pytest run (tests/ and evals/), after a 19 GB runaway test killed a session.

A limit that trips is a FAILURE with an explicit 'resource limit' message, never a skip or a pass.
  SF_TEST_MEM_MB     address-space cap for the pytest process and its children (default 4096; 0 disables)
  SF_TEST_TIMEOUT_S  wall-clock cap per test (default 120; 0 disables)
The limits in force are printed in the report header so a run records what it was bounded by.
"""
import os
import resource
import signal
import sys
import threading
from pathlib import Path

import pytest

MEM_MB = int(os.environ.get("SF_TEST_MEM_MB", "4096"))
TIMEOUT_S = int(os.environ.get("SF_TEST_TIMEOUT_S", "120"))
sys.dont_write_bytecode = True  # this process and, via the variable, children
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # scripts run under test must not leave .pyc in skills/ (test_skills_sync rejects it)


def pytest_sessionstart(session):
    if MEM_MB > 0:
        limit = MEM_MB * 1024 * 1024
        if sys.platform == "darwin":
            # Darwin rejects RLIMIT_AS on current Python builds. Keep direct
            # pytest invocations bounded too; the wrapper also watches children.
            from factory.resource_limits import tree_rss
            def watch_memory():
                while True:
                    try:
                        if tree_rss(os.getpid()) > limit:
                            # pytest may be capturing fd 2 when this trips;
                            # retain a durable diagnostic before immediate exit.
                            log = Path.cwd() / ".sf" / "resource-limits.log"
                            log.parent.mkdir(parents=True, exist_ok=True)
                            with log.open("a") as handle:
                                handle.write(f"resource limit: pytest process-tree memory exceeded {MEM_MB} MB; exit 137 (not a pass)\n")
                            os.write(2, b"resource limit: pytest process-tree memory exceeded (not a pass)\n")
                            os._exit(137)
                    except Exception as error:
                        os.write(2, f"resource limit: memory supervisor failed: {error}\n".encode())
                        os._exit(125)
                    threading.Event().wait(0.2)
            threading.Thread(target=watch_memory, daemon=True).start()
            return
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (limit if hard == resource.RLIM_INFINITY else min(limit, hard), hard))


def pytest_report_header(config):
    kind = "sampled process-tree RSS" if sys.platform == "darwin" else "address space"
    return f"resource limits: {kind} {MEM_MB or 'unlimited'} MB, per-test timeout {TIMEOUT_S or 'none'} s (SF_TEST_MEM_MB, SF_TEST_TIMEOUT_S)"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if TIMEOUT_S <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def on_alarm(signum, frame):
        pytest.fail(f"resource limit: test exceeded {TIMEOUT_S} s (SF_TEST_TIMEOUT_S)", pytrace=False)

    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(TIMEOUT_S)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
