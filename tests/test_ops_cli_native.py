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
    commit(proj, files={".gitignore": "ops/\n"})
    (proj / "ops").mkdir()
    (proj / "ops" / "events.jsonl").write_text("")
    assert sf("ops", "autobundle", "install", cwd=proj).returncode == 0
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("SF_EVENTS", None)  # the owner's shell does not switch events off
    (proj / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=proj, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "hooked"],
                   cwd=proj, check=True, env=env)
    import time
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    for _ in range(150):
        if (proj / "ops" / "snapshots" / head / "manifest.json").exists():
            break
        time.sleep(0.1)
    assert (proj / "ops" / "snapshots" / head / "manifest.json").exists()
    assert (proj / "ops" / "events.jsonl").read_text() == ""
    assert subprocess.run(["git", "status", "--porcelain"], cwd=proj, capture_output=True, text=True).stdout == ""
