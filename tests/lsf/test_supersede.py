import json

from conftest import LSF, at, run
from test_review_fixes import guard


def two(repo, release_new=True):
    run(repo, "init")
    (repo / "x").write_text("x\n")
    for n in ("old", "new"):
        assert run(repo, "hitl", "request", n, "--question", "q", "--artifact", "x").returncode == 0
    if release_new:
        assert run(repo, "hitl", "release", "new", "--by", "owner").returncode == 0


def sup(repo, old="old", new="new", *extra):
    return run(repo, "hitl", "supersede", old, "--by-stop", new, *extra, env=at("11:00"))


def test_supersede_ok_and_closes_old(repo):
    two(repo)
    r = sup(repo, "old", "new", "--by", "claude-delegate", "--note", "owner said so")
    assert r.returncode == 0, r.stdout
    last = json.loads((repo / ".lsf" / "stops.jsonl").read_text().splitlines()[-1])
    assert last["kind"] == "supersede" and last["old"] == "old" and last["new"] == "new" and last["by"] == "claude-delegate"
    assert last["note"] == "owner said so" and last["at"] and last["seq"] == 4 and last["hash"] == last["chain"]
    assert run(repo, "hitl", "status").returncode == 0
    s = {x["name"]: x for x in json.loads(run(repo, "hitl", "status", "--json").stdout)}
    assert s["old"]["status"] == "superseded by new" and s["old"]["state"] == "superseded"
    assert "superseded by new" in run(repo, "hitl", "status").stdout
    st = run(repo, "status", "--json")
    assert st.returncode == 0 and json.loads(st.stdout)["open_stops"] == []
    import importlib.util
    sp = importlib.util.spec_from_file_location("lsf_mod", LSF)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    rt = m.runtime_state(str(repo))  # what the dashboard's Stops tab and banner read
    assert rt["stop_ledger"] == "ok" and rt["status"]["open_stops"] == []
    assert [x["status"] for x in rt["stops"] if x["name"] == "old"] == ["superseded by new"]


def test_supersede_refusals(repo):
    two(repo, release_new=False)
    assert sup(repo).returncode == 1  # new only open
    assert run(repo, "hitl", "release", "new").returncode == 0
    assert sup(repo, "old", "old").returncode == 1
    assert sup(repo, "ghost", "new").returncode == 1
    assert sup(repo, "old", "ghost").returncode == 1
    assert sup(repo, "new", "old").returncode == 1  # old=new is released, not open
    assert run(repo, "hitl", "supersede", "old").returncode == 2  # missing --by-stop
    assert len((repo / ".lsf" / "stops.jsonl").read_text().splitlines()) == 3  # nothing appended


def test_supersede_twice_refused(repo):
    two(repo)
    assert sup(repo).returncode == 0
    assert sup(repo).returncode == 1


def test_supersede_tamper_detected(repo):
    two(repo)
    sup(repo, "old", "new", "--note", "abc")
    led = repo / ".lsf" / "stops.jsonl"
    led.write_text(led.read_text().replace("abc", "abd"))
    for cmd in (("status",), ("hitl", "status")):
        r = run(repo, *cmd)
        assert r.returncode == 1 and "stop ledger failed verification" in r.stdout


def test_supersede_guarded_from_agent(repo):
    run(repo, "init")
    r = guard(repo, "lsf hitl supersede a --by-stop b")
    assert r.returncode == 2 and r.stderr
