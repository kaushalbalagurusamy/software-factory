import ast
import json

from conftest import LSF, SKILL, at, events, run


def test_python39_syntax_and_no_forbidden_things():
    src = LSF.read_text()
    ast.parse(src, feature_version=(3, 9))
    for bad in ("fcntl", "flock", "prlimit", "/proc", "tomllib", "urllib", "import factory", "from factory"):
        assert bad not in src


def test_help_for_every_command(repo):
    for c in "init phase event hitl status budget serve bundle hooks doctor cost".split():
        r = run(repo, c, "--help")
        assert r.returncode == 0 and "usage" in r.stdout.lower(), c


def test_init_profile_and_idempotent(repo):
    assert run(repo, "init").returncode == 0
    p = json.loads((repo / ".lsf" / "profile.json").read_text())
    assert p["session_minutes"] == 60 and p["editor"] == "vscode" and p["workspace_root"] == str(repo.resolve())
    assert [x["id"] for x in p["phases"]][0] == "0-intake" and p["checkpoints"]["6-decide"] is True
    assert p["checkpoints"]["7-implement"] is False
    run(repo, "event", "x", "y")
    run(repo, "init", "--checkpoints", "all")
    assert events(repo) and json.loads((repo / ".lsf" / "profile.json").read_text()) == p


def test_checkpoint_modes(repo):
    run(repo, "init", "--checkpoints", "none")
    assert not any(json.loads((repo / ".lsf" / "profile.json").read_text())["checkpoints"].values())


def test_bad_weights_exit_2(repo):
    assert run(repo, "init", "--weight", "align=0.9").returncode == 2
    run(repo, "init")
    prof = repo / ".lsf" / "profile.json"
    d = json.loads(prof.read_text())
    d["weights"]["align"] = 0.9
    prof.write_text(json.dumps(d))
    assert run(repo, "budget").returncode == 2 and run(repo, "status").returncode == 2


def test_phase_flow_and_budget(repo):
    run(repo, "init", "--checkpoints", "none")
    assert run(repo, "phase", "start", "nope").returncode == 2
    assert run(repo, "phase", "end", "0-intake").returncode == 1
    assert run(repo, "phase", "start", "0-intake", env=at("10:00")).returncode == 0
    assert run(repo, "phase", "start", "1-sweep", env=at("10:10")).returncode == 0
    r = run(repo, "status", env=at("10:15"))
    assert "1-sweep" in r.stdout and "5.0" in r.stdout and "2-research" in r.stdout
    b = json.loads(run(repo, "budget", "--json", env=at("10:20")).stdout)
    assert b["groups"]["align"]["actual_minutes"] == 20.0
    assert b["groups"]["align"]["planned_minutes"] == 36.0
    assert b["groups"]["build"]["actual_minutes"] is None
    assert "under" in b["groups"]["build"]["flag"] and "under" in b["groups"]["align"]["flag"]
    assert b["waiting_on_human_minutes"] == 0
    ev = [e for e in events(repo) if e["stage"] == "0-intake"]
    assert ev[-1]["verdict"] == "switched"
    h = run(repo, "budget", env=at("12:00")).stdout
    assert "over" in h and "waiting on human" in h and "not measured" in h


def test_checkpoint_blocks_phase_start_until_release(repo):
    run(repo, "init")
    run(repo, "phase", "start", "0-intake", env=at("10:00"))
    r = run(repo, "phase", "end", "0-intake", "--ask", "Is the brief right?", "--artifact", "docs/a.md", env=at("10:05"))
    assert r.returncode == 0 and "0-intake-review" in r.stdout
    s = run(repo, "hitl", "status", "--json", env=at("10:06"))
    assert s.returncode == 3
    stop = json.loads(s.stdout)[0]
    assert stop["question"] == "Is the brief right?" and stop["artifact"] == ["docs/a.md"] and stop["opened_at"]
    blocked = run(repo, "phase", "start", "1-sweep", env=at("10:06"))
    assert blocked.returncode == 3 and "0-intake-review" in blocked.stdout
    assert run(repo, "hitl", "release", "nope").returncode == 1
    assert run(repo, "hitl", "release", "0-intake-review", "--by", "owner", "--note", "ok", env=at("10:20")).returncode == 0
    assert run(repo, "hitl", "release", "0-intake-review").returncode == 1
    s = run(repo, "hitl", "status", "--json")
    assert s.returncode == 0 and json.loads(s.stdout)[0]["released_by"] == "owner"
    assert run(repo, "phase", "start", "1-sweep", env=at("10:21")).returncode == 0
    b = json.loads(run(repo, "budget", "--json", env=at("10:30")).stdout)
    assert b["waiting_on_human_minutes"] == 15.0 and b["groups"]["align"]["actual_minutes"] == 14.0


def test_stop_ledger_tamper_detected(repo):
    run(repo, "init")
    run(repo, "hitl", "request", "a", "--question", "q1")
    run(repo, "hitl", "request", "b", "--question", "q2")
    led = repo / ".lsf" / "stops.jsonl"
    good = led.read_text()
    for bad in (good.replace("q1", "qX"), good.splitlines()[0] + "\n", "garbage\n" + good, good + "\n\n"):
        led.write_text(bad)
        for cmd in (("status",), ("hitl", "status")):
            r = run(repo, *cmd)
            assert r.returncode == 1 and "stop ledger failed verification" in r.stdout
        assert run(repo, "phase", "start", "0-intake").returncode == 1
    led.write_text(good)
    assert run(repo, "hitl", "status").returncode == 3


def test_event_redaction_truncation_and_off(repo):
    run(repo, "event", "qa", "fail", "--note", "key sk-abcdefghijklmnopqrstuv\x07 password=hunter2 " + "a" * 3000, "--role", "qa")
    e = events(repo)[0]
    assert set("at stage slice phase verdict note source sha".split()) <= set(e)
    assert "sk-abc" not in e["note"] and "hunter2" not in e["note"] and "\x07" not in e["note"]
    assert len(e["note"]) == 2000 and e["source"] in ("agent", "lsf", "hook") and len(e["sha"]) == 40 and e["role"] == "qa"
    n = len(events(repo))
    run(repo, "event", "a", "b", env={"LSF_EVENTS": "off"})
    run(repo, "event", "a", "b", env={"SF_EVENTS": "off"})
    assert len(events(repo)) == n


def test_event_without_git_sha_is_unknown(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    run(d, "event", "a", "b")
    assert events(d)[0]["sha"] == "unknown"


def test_cost(repo):
    assert run(repo, "cost", "add", "--usd", "1.5", "--model", "m1", "--tokens", "100").returncode == 0
    run(repo, "cost", "add", "--usd", "0.5", "--model", "m1")
    assert run(repo, "cost", "add", "--usd", "-1").returncode == 2
    s = json.loads(run(repo, "cost", "summary", "--json").stdout)
    assert s["total_usd"] == 2.0 and s["by_model"]["m1"]["entries"] == 2 and s["label"] == "manual"


def test_doctor(repo):
    r = run(repo, "doctor")
    assert r.returncode == 0 and "PASS self-check" in r.stdout
    assert run(repo, "doctor", "--port", "0").returncode == 1


def test_root_before_or_after(repo):
    import subprocess
    import sys
    r = subprocess.run([sys.executable, str(LSF), "--root", str(repo), "init"], capture_output=True, text=True)
    assert r.returncode == 0 and (repo / ".lsf").is_dir()
