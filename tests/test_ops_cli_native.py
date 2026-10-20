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


# ---- sf ops init / backfill / status / autobundle -----------------------------------------------------------

def sf(*args, cwd):
    return subprocess.run([sys.executable, "-m", "factory.cli", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(REPO), "SF_EVENTS": "off"})


def commit(repo, msg="c", files=None):
    for rel, text in (files or {}).items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", msg], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_init_creates_and_is_idempotent(proj):
    commit(proj, files={"docs/slices/s1/proposal.md": "# P\n"})
    r = sf("ops", "init", cwd=proj)
    assert r.returncode == 0, r.stderr
    tabs = {ln.split(":")[0]: ln for ln in r.stdout.splitlines()}
    from factory.ops.collect import TABS
    assert list(tabs) == list(TABS)
    assert tabs["git"].endswith(": available")
    assert "not available: " in tabs["dev_journey"] and "no stage events recorded" in tabs["dev_journey"]
    assert (proj / "ops" / "events.jsonl").read_bytes() == b"" and (proj / "ops" / "shell" / "index.html").exists()
    (proj / "ops" / "config.json").write_text('{"keep": 1}')
    before = {p: p.read_bytes() for p in (proj / "ops").rglob("*") if p.is_file()}
    assert sf("ops", "init", cwd=proj).returncode == 0
    assert {p: p.read_bytes() for p in (proj / "ops").rglob("*") if p.is_file()} == before


def test_init_refuses_outside_git(tmp_path):
    assert sf("ops", "init", cwd=tmp_path).returncode == 2
    assert not (tmp_path / "ops").exists()


def test_init_dir_option(proj, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    commit(other)
    assert sf("ops", "init", "--dir", str(other), cwd=proj).returncode == 0
    assert (other / "ops" / "index.json").exists() and not (proj / "ops").exists()


def test_status_and_backfill(proj):
    c1 = commit(proj, "one")
    assert sf("ops", "status", cwd=proj).returncode == 4  # no snapshot yet
    j = json.loads(sf("ops", "status", "--json", cwd=proj).stdout)
    assert j == {"head": c1, "snapshot": None, "behind": None, "events": 0}
    assert sf("ops", "bundle", cwd=proj).returncode == 0
    assert sf("ops", "status", cwd=proj).returncode == 0
    c3 = commit(proj, "two") and commit(proj, "three")
    j = json.loads(sf("ops", "status", "--json", cwd=proj).stdout)
    assert (j["head"], j["snapshot"], j["behind"]) == (c3, c1, 2)
    assert sf("ops", "status", cwd=proj).returncode == 4
    r = sf("ops", "backfill", cwd=proj)
    assert r.returncode == 0 and "built 2, skipped 1, failed 0" in r.stdout
    assert "skipped 3" in sf("ops", "backfill", cwd=proj).stdout
    assert sf("ops", "status", cwd=proj).returncode == 0
    assert "built 0, skipped 1" in sf("ops", "backfill", "--limit", "1", cwd=proj).stdout
    idx = json.loads((proj / "ops" / "index.json").read_text())
    assert idx["head"] == c1 or idx["head"] == c3  # head is set by default-HEAD bundles only


def test_backfill_lists_failures_and_continues(proj, monkeypatch):
    from factory.ops import bundle as B, cli as opscli
    shas = [commit(proj, str(i)) for i in range(3)]
    real = B.bundle

    def flaky(repo, sha, *a, **k):
        if sha == shas[1]:
            raise RuntimeError("boom")
        return real(repo, sha, *a, **k)
    monkeypatch.setattr(B, "bundle", flaky)
    assert opscli.main(["backfill"]) == 1
    assert (proj / "ops" / "snapshots" / shas[2] / "manifest.json").exists()
    assert (proj / "ops" / "snapshots" / shas[0] / "manifest.json").exists()


def test_index_head_and_runtime_fields(proj):
    from factory.ops import bundle as B, runtime as R
    c1 = commit(proj, "one")
    B.bundle(proj, "HEAD", Path("ops"))
    assert json.loads((proj / "ops" / "index.json").read_text())["head"] == c1
    commit(proj, "two")
    d = R.write_runtime(None, proj / "ops" / "runtime.json")
    assert (d["behind"], d["repo_head"] == c1) == (1, False)
    d = R.write_runtime(None, proj.parent / "nowhere" / "runtime.json")
    assert d["behind"] is None and d["repo_head"] is None


def test_dev_journey_events_filtered_and_unavailable_without_events(proj):
    from factory.ops import bundle as B
    ev = '{"at": "%s", "stage": "7-qa", "slice": "s", "sha": "x", "verdict": "pass", "note": ""}\n'
    c1 = commit(proj, "none")
    B.bundle(proj, "HEAD", Path("ops"))
    man = json.loads((proj / "ops" / "snapshots" / c1 / "manifest.json").read_text())
    assert man["tabs"]["dev_journey"]["available"] is False
    assert "no stage events recorded" in man["tabs"]["dev_journey"]["reason"]
    c2 = commit(proj, "events", files={"ops/events.jsonl": ev % "2000-01-01T00:00:00+00:00" + ev % "2999-01-01T00:00:00+00:00"})
    B.bundle(proj, "HEAD", Path("ops"))
    man = json.loads((proj / "ops" / "snapshots" / c2 / "manifest.json").read_text())
    blob = json.loads((proj / "ops" / "blobs" / f"{man['tabs']['dev_journey']['blob']}.json").read_text())
    assert [e["at"][:4] for e in blob["events"]] == ["2000"]


def test_autobundle_lifecycle(proj):
    commit(proj)
    hook = proj / ".git" / "hooks" / "post-commit"
    assert "not installed" in sf("ops", "autobundle", "status", cwd=proj).stdout
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\necho mine\n")
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0
    first = hook.read_bytes()
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0 and hook.read_bytes() == first
    t = first.decode()
    assert "echo mine" in t and t.count("# >>> sf ops autobundle >>>") == 1 and "ops bundle --sha HEAD" in t
    assert "120" in t and os.access(hook, os.X_OK) and "installed" in sf("ops", "autobundle", "status", cwd=proj).stdout
    assert sf("ops", "autobundle", "uninstall", cwd=proj).returncode == 0
    assert hook.read_text() == "#!/bin/sh\necho mine\n"
    sf("ops", "autobundle", "install", cwd=proj)
    hook.write_text(first.decode().split("# >>>")[0].replace("echo mine\n", "") + "# >>>" + first.decode().split("# >>>")[1])
    sf("ops", "autobundle", "uninstall", cwd=proj)
    assert not hook.exists()


def test_autobundle_runs_after_commit_and_never_fails_the_commit(proj):
    commit(proj)
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0
    commit(proj, "hooked")
    import time
    for _ in range(100):
        if (proj / "ops" / "index.json").exists():
            break
        time.sleep(0.1)
    assert (proj / "ops" / "index.json").exists()


def test_autobundle_in_linked_worktree(proj, tmp_path_factory):
    commit(proj)
    wt = tmp_path_factory.mktemp("wt") / "w"
    subprocess.run(["git", "-C", str(proj), "worktree", "add", "-q", str(wt), "-b", "other"], check=True)
    assert sf("ops", "autobundle", "install", "--repo", str(wt), cwd=wt).returncode == 0
    assert (proj / ".git" / "hooks" / "post-commit").exists()


def test_viewer_has_staleness_banner_texts():
    html = (REPO / "ops" / "shell" / "index.html").read_text()
    for t in ("commits behind the repository", "Up to date", "Repository state unknown"):
        assert t in html


def test_autobundle_commit_leaves_tree_clean(proj):
    commit(proj, files={".gitignore": "ops/*\n!ops/events.jsonl\n"})  # events.jsonl is only kept out by the local exclude
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("SF_EVENTS", None)
    (proj / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=proj, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "hooked"],
                   cwd=proj, check=True, env=env)
    import time
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    for _ in range(150):
        if events(proj) and (proj / "ops" / "snapshots" / head / "manifest.json").exists():
            break
        time.sleep(0.1)
    assert (proj / "ops" / "snapshots" / head / "manifest.json").exists()
    assert [e["stage"] for e in events(proj)] == ["11-commit"]
    st = subprocess.run(["git", "status", "--porcelain"], cwd=proj, capture_output=True, text=True).stdout
    assert "events.jsonl" not in st and "f.txt" not in st


def exclude_lines(repo):
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"], capture_output=True,
                       text=True).stdout.strip()
    p = Path(p) if os.path.isabs(p) else Path(repo) / p
    return p.read_text().splitlines() if p.exists() else []


def test_exclude_is_idempotent_for_init_and_autobundle(proj):
    commit(proj)
    ex = proj / ".git" / "info" / "exclude"
    ex.parent.mkdir(exist_ok=True)
    ex.write_text("keep-me")  # no trailing newline
    sf("ops", "init", cwd=proj)
    sf("ops", "autobundle", "install", cwd=proj)
    sf("ops", "init", cwd=proj)
    sf("ops", "autobundle", "install", cwd=proj)
    assert exclude_lines(proj) == ["keep-me", "ops/events.jsonl"]
    assert not (proj / ".gitignore").exists()


def test_exclude_in_linked_worktree_and_missing_file(proj, tmp_path_factory):
    commit(proj)
    (proj / ".git" / "info" / "exclude").unlink(missing_ok=True)
    wt = tmp_path_factory.mktemp("wt") / "w"
    subprocess.run(["git", "-C", str(proj), "worktree", "add", "-q", str(wt), "-b", "other"], check=True)
    assert sf("ops", "init", "--dir", str(wt), cwd=wt).returncode == 0
    assert sf("ops", "autobundle", "install", "--repo", str(wt), cwd=wt).returncode == 0
    assert exclude_lines(wt) == ["ops/events.jsonl"] and exclude_lines(proj) == ["ops/events.jsonl"]
    assert "events.jsonl" not in subprocess.run(["git", "status", "--porcelain"], cwd=wt, capture_output=True,
                                                text=True).stdout


def test_event_goes_to_the_repo_of_the_path_argument(proj, fake_tool, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    (other / "docs" / "slices" / "s9").mkdir(parents=True)
    assert cli.main(["slice", "check", str(other / "docs" / "slices" / "s9")]) == 0
    assert cli.main(["ops", "bundle", "--repo", str(other)]) == 0
    assert cli.main(["qa", "--root", str(other), "state"]) == 0
    assert [e["stage"] for e in events(other)] == ["4-slice", "11-commit", "7-qa"]
    assert events(proj) == []
    assert cli.main(["slice", "lock", "plain"]) == 0  # no path argument that leaves the cwd repo
    assert [e["stage"] for e in events(proj)] == ["5-evals"]


def test_untracked_local_log_reaches_the_snapshot(proj):
    from factory.ops import bundle as B
    ev = '{"at": "%s", "stage": "7-qa", "slice": "s", "sha": "x", "verdict": "pass", "note": ""}\n'
    (proj / "ops").mkdir()
    (proj / "ops" / "events.jsonl").write_text(ev % "2000-01-01T00:00:00+00:00" + ev % "2999-01-01T00:00:00+00:00" + "garbage\n")
    c = commit(proj, "one")
    B.bundle(proj, "HEAD", Path("ops"))
    man = json.loads((proj / "ops" / "snapshots" / c / "manifest.json").read_text())
    dj = man["tabs"]["dev_journey"]
    assert dj["available"] is True
    blob = json.loads((proj / "ops" / "blobs" / f"{dj['blob']}.json").read_text())
    assert [e["at"][:4] for e in blob["events"]] == ["2000"] and blob["events_source"] == "local log"
    (proj / "ops" / "events.jsonl").write_text("")  # the stored snapshot stays reproducible
    assert json.loads((proj / "ops" / "blobs" / f"{dj['blob']}.json").read_text())["events"]


def test_empty_or_missing_local_log_keeps_the_reason(proj):
    from factory.ops import bundle as B
    c = commit(proj, "one")
    B.bundle(proj, "HEAD", Path("ops"))
    assert "no stage events recorded" in json.loads(
        (proj / "ops" / "snapshots" / c / "manifest.json").read_text())["tabs"]["dev_journey"]["reason"]


def test_hook_built_snapshot_shows_the_11_commit_event(proj):
    import time
    commit(proj)
    sf("ops", "init", cwd=proj)
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0
    shim = proj.parent / "shim"  # the hook resolves `sf` from PATH: point it at this checkout
    shim.mkdir(exist_ok=True)
    (shim / "sf").write_text(f'#!/bin/sh\nPYTHONPATH="{REPO}" exec "{sys.executable}" -m factory.cli "$@"\n')
    (shim / "sf").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "SF_EVENTS"} | {"PYTHONPATH": str(REPO), "PATH": f"{shim}:{os.environ['PATH']}"}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "h1"],
                   cwd=proj, check=True, env=env)
    time.sleep(0.5)
    for _ in range(100):  # the second commit's snapshot is built after the first commit's event exists
        if events(proj):
            break
        time.sleep(0.1)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "h2"],
                   cwd=proj, check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    man = proj / "ops" / "snapshots" / head / "manifest.json"
    for _ in range(150):
        if man.exists():
            break
        time.sleep(0.1)
    assert json.loads(man.read_text())["tabs"]["dev_journey"]["available"] is True


def test_parallel_bundles_keep_every_index_entry(proj):
    shas = [commit(proj, str(i)) for i in range(8)]
    env = {**os.environ, "PYTHONPATH": str(REPO), "SF_EVENTS": "off"}
    ps = [subprocess.Popen([sys.executable, "-m", "factory.cli", "ops", "bundle", "--sha", s], cwd=proj, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for s in shas]
    assert [p.wait() for p in ps] == [0] * 8
    idx = json.loads((proj / "ops" / "index.json").read_text())
    assert {c["sha"] for c in idx["commits"]} == set(shas)


def test_backfill_reindexes_lost_entries(proj):
    shas = [commit(proj, str(i)) for i in range(3)]
    assert sf("ops", "backfill", cwd=proj).returncode == 0
    ip = proj / "ops" / "index.json"
    idx = json.loads(ip.read_text())
    idx["commits"] = idx["commits"][:1]
    ip.write_text(json.dumps(idx))
    assert sf("ops", "backfill", cwd=proj).returncode == 0
    assert {c["sha"] for c in json.loads(ip.read_text())["commits"]} == set(shas)


def test_head_never_moves_to_a_non_descendant(proj):
    from factory.ops import bundle as B
    c1 = commit(proj, "one")
    c2 = commit(proj, "two")
    B.bundle(proj, c2, Path("ops"))
    B.update_index(proj / "ops", [], c2, proj)
    B.update_index(proj / "ops", [], c1, proj)  # an older bundle finishing last
    assert json.loads((proj / "ops" / "index.json").read_text())["head"] == c2
    subprocess.run(["git", "checkout", "-q", "-b", "side", c1], cwd=proj, check=True)
    c3 = commit(proj, "side")
    B.update_index(proj / "ops", [], c3, proj)  # diverged
    assert json.loads((proj / "ops" / "index.json").read_text())["head"] == c2
