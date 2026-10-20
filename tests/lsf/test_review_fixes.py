"""Fixes from the 2026-10-20 adversarial review."""
import json
import os
import subprocess
import sys

import pytest

from conftest import LSF, SKILL, at, events, run

sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL / "scripts"))
import lsf as L  # noqa: E402


def led(repo):
    return repo / ".lsf" / "stops.jsonl"


def test_deleting_the_ledger_is_not_no_stops(repo):
    run(repo, "init")
    run(repo, "phase", "start", "0-intake")
    run(repo, "phase", "end", "0-intake")
    led(repo).unlink()
    (repo / ".lsf" / "stops.head").unlink()
    for cmd in (("hitl", "status"), ("status",), ("phase", "start", "1-sweep")):
        r = run(repo, *cmd)
        assert r.returncode == 1 and "stop ledger inconsistent" in r.stdout + r.stderr, cmd
        assert "no human stops" not in r.stdout


def test_forged_release_without_event_is_inconsistent(repo):
    run(repo, "init")
    run(repo, "hitl", "request", "g", "--question", "q")
    entries = [json.loads(x) for x in led(repo).read_text().splitlines()]
    e = {"kind": "release", "name": "g", "released_at": "2026-10-20T10:00:00Z", "released_by": "x", "note": "", "via": "dashboard",
         "seq": 2, "prev": entries[-1]["chain"]}
    e["chain"] = e["hash"] = L._chain(e["prev"], L._entry_text(e))
    with open(led(repo), "a") as f:
        f.write(json.dumps(e) + "\n")
    (repo / ".lsf" / "stops.head").write_text(json.dumps({"seq": 2, "chain": e["chain"]}))
    r = run(repo, "hitl", "status")
    assert r.returncode == 1 and "stop ledger inconsistent" in r.stdout


def test_hitl_events_survive_events_off_and_via_recorded(repo):
    run(repo, "init")
    run(repo, "hitl", "request", "g", "--question", "q", env={"LSF_EVENTS": "off"})
    assert run(repo, "hitl", "release", "g", env={"LSF_EVENTS": "off"}).returncode == 0
    s = json.loads(run(repo, "hitl", "status", "--json").stdout)
    assert s[0]["via"] == "cli-nontty"
    assert [e["verdict"] for e in events(repo) if e["stage"] == "hitl"] == ["opened", "released"]


def test_strict_hitl_refuses_without_tty(repo):
    assert run(repo, "init", "--strict-hitl").returncode == 0
    assert json.loads((repo / ".lsf" / "profile.json").read_text())["require_tty_release"] is True
    run(repo, "hitl", "request", "g", "--question", "q")
    r = run(repo, "hitl", "release", "g", stdin="")
    assert r.returncode == 3 and "terminal" in r.stdout
    assert run(repo, "hitl", "repair", "--yes", stdin="").returncode == 3
    assert run(repo, "hitl", "status").returncode == 3


def guard(repo, cmd):
    return run(repo, "hook", "guard", stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))


def test_guard_hook(repo):
    run(repo, "init")
    for bad in ("lsf hitl release g", "python3 x/lsf.py --root . hitl repair --yes", "rm .lsf/stops.jsonl", "echo x > .lsf/stops.head",
                "curl -X POST localhost:8765/api/hitl/release"):
        r = guard(repo, bad)
        assert r.returncode == 2 and r.stderr and r.stdout == "", bad
    for ok in ("ls", "cat .lsf/stops.jsonl", "lsf hitl status", "git commit -m x"):
        r = guard(repo, ok)
        assert r.returncode == 0 and r.stdout == "" and r.stderr == "", ok
    for junk in ("", "nope", "[]", '{"tool_input": 4}'):
        assert run(repo, "hook", "guard", stdin=junk).returncode == 0
    cfg = json.loads(run(repo, "hooks", "print").stdout)["hooks"]["PreToolUse"][0]
    assert cfg["matcher"] == "Bash" and cfg["hooks"][0]["command"].endswith("hook guard")


def test_head_heals_after_crash_window_and_repair(repo):
    run(repo, "init")
    run(repo, "hitl", "request", "a", "--question", "q")
    head = repo / ".lsf" / "stops.head"
    old = head.read_text()
    run(repo, "hitl", "request", "b", "--question", "q")
    head.write_text(old)
    assert run(repo, "hitl", "status").returncode == 3
    assert json.loads(head.read_text())["seq"] == 2
    good = led(repo).read_text()
    led(repo).write_text(good.replace('"q"', '"Z"', 1) if False else good.splitlines()[0] + "\nGARBAGE\n")
    assert run(repo, "hitl", "status").returncode == 1
    r = run(repo, "budget")
    assert r.returncode == 1 and "waiting on human: not measured (stop ledger failed verification)" in r.stdout
    assert run(repo, "budget", "--json").returncode == 1
    assert run(repo, "status").returncode == 1
    assert run(repo, "hitl", "repair").returncode == 2
    assert run(repo, "hitl", "repair", "--yes").returncode == 0
    assert list((repo / ".lsf").glob("stops.jsonl.corrupt-*"))
    assert run(repo, "hitl", "status").returncode == 3
    assert [e for e in events(repo) if e["verdict"] == "repaired"]
    assert run(repo, "hitl", "request", "c", "--question", "q").returncode == 0


def test_budget_session_total_and_group_waiting(repo):
    run(repo, "init")
    run(repo, "phase", "start", "0-intake", env=at("10:00"))
    run(repo, "phase", "end", "0-intake", env=at("10:08"))
    run(repo, "hitl", "release", "0-intake-review", env=at("10:14"))
    run(repo, "phase", "start", "7-implement", env=at("10:14"))
    b = json.loads(run(repo, "budget", "--json", env=at("10:20")).stdout)
    assert b["groups"]["align"]["waiting_minutes"] == 6.0 and b["session_total_minutes"] == 20.0
    h = run(repo, "budget", env=at("10:20")).stdout
    assert "WARN: clock overridden" in h and "session total" in h
    assert "WARN" in run(repo, "status", env=at("10:20")).stdout
    assert "WARN clock" in run(repo, "doctor", env=at("10:20")).stdout


def test_redaction_extras():
    for raw in ("curl -u admin:hunter2 http://x", "postgres://user:pw9@host/db", "sk_live_abcdefgh12345", "x --token ABC123 y",
                "--password s3cret z", "AIza" + "a" * 30, "npm_" + "b" * 24):
        out = L.redact(raw)
        assert "hunter2" not in out and "pw9" not in out and "abcdefgh12345" not in out and "ABC123" not in out
        assert "s3cret" not in out and "a" * 30 not in out and "b" * 24 not in out


def test_file_route_dotgit_any_case():
    assert L.forbidden_rel(".GIT/config") and L.forbidden_rel("a/.Git/x") and L.forbidden_rel(".LSF/api_token")
    assert not L.forbidden_rel("docs/a.md")


def test_empty_bug_log_unavailable(repo):
    (repo / "docs").mkdir()
    (repo / "docs/bug-log.jsonl").write_text("")
    t = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]["bug_log"]
    assert t["available"] is False and t["reason"]


def test_truncated_scan_is_said(repo, monkeypatch):
    (repo / "research").mkdir()
    (repo / "research/t.md").write_text("# T\n")
    for i in range(5):
        (repo / "research" / ("x%d.txt" % i)).write_text("x")
    monkeypatch.setattr(L, "MAX_FILES", 3)
    tabs = L.collect_tabs(L.WorkTree(str(repo.resolve())))
    t = tabs["research"]
    assert "truncated: scan stopped at 3 files" in (t.get("reason") or t["summary"].get("truncated"))


def test_deep_artifacts_found_in_a_huge_tree(repo):
    (repo / "a").mkdir()
    for i in range(30):
        (repo / "a" / ("f%d" % i)).write_text("x")
    (repo / "research").mkdir()
    (repo / "research/t.md").write_text("# T\n")
    old = L.MAX_FILES
    L.MAX_FILES = 10
    try:
        t = L.collect_tabs(L.WorkTree(str(repo.resolve())))["research"]
    finally:
        L.MAX_FILES = old
    assert t["available"] and t["items"][0]["path"] == "research/t.md"


def test_hook_root_walks_up_and_never_creates_lsf(repo, tmp_path):
    run(repo, "init")
    sub = repo / "deep" / "er"
    sub.mkdir(parents=True)
    payload = json.dumps({"cwd": str(sub), "last_assistant_message": "hi"})
    e = dict(os.environ)
    r = subprocess.run([sys.executable, str(LSF), "hook", "Stop"], input=payload, capture_output=True, text=True, env=e, cwd=str(tmp_path))
    assert r.returncode == 0 and r.stdout == "" and any(x["stage"] == "Stop" for x in events(repo))
    other = tmp_path / "elsewhere"
    other.mkdir()
    r = subprocess.run([sys.executable, str(LSF), "hook", "Stop"], input=json.dumps({"cwd": str(other)}), capture_output=True,
                       text=True, cwd=str(other))
    assert r.returncode == 0 and r.stdout == "" and not (other / ".lsf").exists()


def test_commit_counted_only_for_real_commit_commands(repo):
    run(repo, "init")
    def post(cmd):
        run(repo, "hook", "PostToolUse", stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
    for c in ('echo "git commit"', "grep 'git commit' x", "ls"):
        post(c)
    assert not [e for e in events(repo) if e["verdict"] == "commit"]
    for c in ("git commit -m x", "cd p && git commit -am y", "git -C d commit -m z", "FOO=1 git commit"):
        post(c)
    assert len([e for e in events(repo) if e["verdict"] == "commit"]) == 4


def test_stale_lock_of_dead_process_is_broken(repo):
    run(repo, "init")
    lock = repo / ".lsf" / ".lock"
    lock.mkdir()
    (lock / "pid").write_text("999999")
    import time
    t = time.time()
    assert run(repo, "hitl", "request", "g", "--question", "q").returncode == 0
    assert time.time() - t < 4
