"""Run commands with a POSIX lock, process-tree RSS limit and wall-clock limit.

Uses Python and ps on both macOS and Linux; no flock/prlimit/timeout binaries.
RSS is sampled, not a kernel allocation quota. A limit failure never passes.
"""
import argparse
from collections import defaultdict
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def tree_rss(pid):
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,rss="],
        capture_output=True, text=True, check=True, timeout=5,
    )
    children = defaultdict(list)
    sizes = {}
    for line in result.stdout.splitlines():
        child, parent, rss = map(int, line.split())
        children[parent].append(child)
        sizes[child] = rss * 1024
    total, pending, seen = 0, [pid], set()
    while pending:
        child = pending.pop()
        if child in seen:
            continue
        seen.add(child)
        total += sizes.get(child, 0)
        pending.extend(children[child])
    return total


def _terminate(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(command, *, memory_mb, wall_s, lock, lock_wait_s=1800):
    Path(lock).parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a") as handle:
        deadline = time.monotonic() + lock_wait_s
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print("resource limit: timed out waiting for test lock", file=sys.stderr)
                    return 124
                time.sleep(0.05)
        process = subprocess.Popen(command, start_new_session=True)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if wall_s > 0 and time.monotonic() - started >= wall_s:
                    _terminate(process)
                    print(f"resource limit: {wall_s}s wall-clock limit exceeded (not a pass)", file=sys.stderr)
                    return 124
                if memory_mb > 0 and tree_rss(process.pid) > memory_mb * 1024 * 1024:
                    _terminate(process)
                    print(f"resource limit: {memory_mb} MB process-tree memory limit exceeded (not a pass)", file=sys.stderr)
                    return 137
                time.sleep(0.1)
        except BaseException:
            _terminate(process)
            raise
        return process.returncode if process.returncode >= 0 else 128 - process.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-mb", type=int, default=4096)
    parser.add_argument("--wall-s", type=float, default=900)
    parser.add_argument("--lock", default="/tmp/sf-factory-pytest.lock")
    parser.add_argument("--lock-wait-s", type=float, default=1800)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or min(args.memory_mb, args.wall_s, args.lock_wait_s) < 0:
        parser.error("a command and nonnegative resource limits are required")
    try:
        return run(command, memory_mb=args.memory_mb, wall_s=args.wall_s,
                   lock=args.lock, lock_wait_s=args.lock_wait_s)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"resource limit: supervisor failed: {error} (not a pass)", file=sys.stderr)
        return 125


if __name__ == "__main__":
    sys.exit(main())
