"""SFN-01 E-07..E-09: `sf ops init`, `sf ops backfill`, `sf ops status`."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .conftest import REPO, child_env, commit, git, read_events, sf, snapshot_tree

TABS = ("architecture", "research", "experiments", "adrs", "prd_journeys", "evals", "bug_log", "dev_journey", "git")


def norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.lower())


def tab_lines(out: str) -> dict:
    """{tab: the output line that mentions it}; fails if a tab is missing or mentioned on several lines."""
    found = {}
    for tab in TABS:
        hits = [ln for ln in out.splitlines() if norm(tab) in norm(ln)]
        assert len(hits) == 1, f"tab {tab}: expected one line, got {hits}\n{out}"
        found[tab] = hits[0]
    return found


def count(out: str, word: str) -> int:
    m = re.search(rf"(\d+)\s*{word}", out, re.I) or re.search(rf"{word}\D{{0,3}}(\d+)", out, re.I)
    assert m, f"no '{word}' count in output:\n{out}"
    return int(m.group(1))


def manifest(repo, sha) -> dict:
    return json.loads((repo / "ops" / "snapshots" / sha / "manifest.json").read_text())


def tab_blob(repo, sha, tab) -> dict:
    t = manifest(repo, sha)["tabs"][tab]
    return json.loads((repo / "ops" / "blobs" / f"{t['blob']}.json").read_text())


# ------------------------------------------------------------------ E-07 sf ops init

def test_E07_init_creates_config_events_shell_and_a_head_snapshot(repo):
    r = sf(repo, "ops", "init")
    assert r.returncode == 0, r.stderr
    assert json.loads((repo / "ops" / "config.json").read_text()) is not None
    assert (repo / "ops" / "events.jsonl").is_file() and (repo / "ops" / "events.jsonl").stat().st_size == 0
    assert (repo / "ops" / "shell" / "index.html").is_file()
    head = git(repo, "rev-parse", "HEAD")
    assert (repo / "ops" / "snapshots" / head / "manifest.json").is_file()
    idx = json.loads((repo / "ops" / "index.json").read_text())
    assert any(c["sha"] == head for c in idx["commits"])


def test_E07_init_prints_one_line_per_historical_tab(repo):
    out = sf(repo, "ops", "init").stdout
    lines = tab_lines(out)
    for tab, ln in lines.items():
        ok = re.search(r"(?<!not )\bavailable\b", ln) or re.search(r"not available: \S", ln)
        assert ok, f"{tab}: line must say 'available' or 'not available: <reason>': {ln!r}"
    # the verdict printed matches the manifest
    head = git(repo, "rev-parse", "HEAD")
    tabs = manifest(repo, head)["tabs"]
    for tab, ln in lines.items():
        assert ("not available:" in ln) == (not tabs[tab]["available"]), (tab, ln)


def test_E07_init_never_overwrites_an_existing_config(repo):
    (repo / "ops").mkdir()
    custom = b'{"health_url": "https://example.invalid/health", "keep": "me"}\n'
    (repo / "ops" / "config.json").write_bytes(custom)
    assert sf(repo, "ops", "init").returncode == 0
    assert (repo / "ops" / "config.json").read_bytes() == custom


def test_E07_init_keeps_existing_events_and_adds_no_event_of_its_own(repo):
    (repo / "ops").mkdir()
    old = '{"at": "2026-01-01T00:00:00+00:00", "stage": "x", "slice": "s", "sha": "u", "verdict": "v", "note": ""}\n'
    (repo / "ops" / "events.jsonl").write_text(old)
    assert sf(repo, "ops", "init").returncode == 0
    assert (repo / "ops" / "events.jsonl").read_text() == old


def test_E07_init_twice_changes_nothing_and_exits_0(repo):
    assert sf(repo, "ops", "init").returncode == 0
    first = snapshot_tree(repo / "ops")
    r = sf(repo, "ops", "init")
    assert r.returncode == 0, r.stderr
    assert snapshot_tree(repo / "ops") == first  # byte-identical, including events.jsonl


def test_E07_init_refuses_outside_a_git_repository_with_exit_2(bare_dir):
    r = sf(bare_dir, "ops", "init")
    assert r.returncode == 2
    assert "git" in r.stderr.lower() and "invalid choice" not in r.stderr  # refused for the right reason
    assert not (bare_dir / "ops").exists()


def test_E07_init_dir_option_targets_that_repository(repo, bare_dir):
    r = sf(bare_dir, "ops", "init", "--dir", str(repo))
    assert r.returncode == 0, r.stderr
    assert (repo / "ops" / "config.json").is_file() and not (bare_dir / "ops").exists()


def test_E07_init_dir_option_outside_git_is_exit_2(bare_dir, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    r = sf(other, "ops", "init", "--dir", str(bare_dir))
    assert r.returncode == 2 and "git" in r.stderr.lower() and "invalid choice" not in r.stderr


def test_E07_init_installs_the_current_viewer_shell(repo):
    sf(repo, "ops", "init")
    assert (repo / "ops" / "shell" / "index.html").read_bytes() == (REPO / "ops" / "shell" / "index.html").read_bytes()


# ------------------------------------------------------------------ E-08 sf ops backfill

@pytest.fixture
def history(repo):
    shas = [git(repo, "rev-parse", "HEAD")]
    for i in range(3):
        shas.append(commit(repo, f"c{i}", {f"f{i}.txt": f"{i}\n"}))
    return repo, shas  # oldest first, 4 commits


def has_snapshot(repo, sha) -> bool:
    return (repo / "ops" / "snapshots" / sha / "manifest.json").is_file()


def test_E08_backfill_builds_every_commit_of_the_branch(history):
    repo, shas = history
    r = sf(repo, "ops", "backfill")
    assert r.returncode == 0, r.stderr
    assert all(has_snapshot(repo, s) for s in shas)
    assert (count(r.stdout, "built"), count(r.stdout, "skipped"), count(r.stdout, "failed")) == (4, 0, 0)


def test_E08_backfill_skips_commits_that_already_have_a_snapshot(history):
    repo, shas = history
    sf(repo, "ops", "bundle", "--sha", shas[-1], env=child_env(SF_EVENTS="off"))
    before = (repo / "ops" / "snapshots" / shas[-1] / "manifest.json").read_bytes()
    r = sf(repo, "ops", "backfill")
    assert r.returncode == 0
    assert (count(r.stdout, "built"), count(r.stdout, "skipped"), count(r.stdout, "failed")) == (3, 1, 0)
    assert (repo / "ops" / "snapshots" / shas[-1] / "manifest.json").read_bytes() == before
    again = sf(repo, "ops", "backfill")
    assert (count(again.stdout, "built"), count(again.stdout, "skipped")) == (0, 4)


def test_E08_limit_takes_the_newest_commits_first(history):
    repo, shas = history
    r = sf(repo, "ops", "backfill", "--limit", "2")
    assert r.returncode == 0
    assert has_snapshot(repo, shas[-1]) and has_snapshot(repo, shas[-2])
    assert not has_snapshot(repo, shas[0]) and not has_snapshot(repo, shas[1])
    assert count(r.stdout, "built") == 2


def test_E08_a_commit_that_fails_is_listed_and_does_not_stop_the_rest(history):
    repo, shas = history
    bad = shas[1]
    (repo / "ops" / "snapshots").mkdir(parents=True)
    victim = repo.parent / "victim"
    victim.mkdir()
    (repo / "ops" / "snapshots" / bad).symlink_to(victim, target_is_directory=True)  # bundle refuses to write through it
    r = sf(repo, "ops", "backfill")
    assert r.returncode == 1
    assert bad[:7] in r.stdout + r.stderr  # the failing commit is listed
    assert (count(r.stdout, "built"), count(r.stdout, "failed")) == (3, 1)
    assert all(has_snapshot(repo, s) for s in shas if s != bad)
    assert list(victim.iterdir()) == []


def test_E08_repo_option_from_another_directory(history, bare_dir):
    repo, shas = history
    r = sf(bare_dir, "ops", "backfill", "--repo", str(repo))
    assert r.returncode == 0, r.stderr
    assert all(has_snapshot(repo, s) for s in shas)
    assert not (bare_dir / "ops").exists()


def test_E08_only_the_current_branch_is_bundled(history):
    repo, shas = history
    git(repo, "checkout", "-q", "-b", "side", shas[1])
    side = commit(repo, "side-only", {"side.txt": "s\n"})
    git(repo, "checkout", "-q", "main")
    sf(repo, "ops", "backfill")
    assert not has_snapshot(repo, side)
    assert has_snapshot(repo, shas[-1])


# ------------------------------------------------------------------ E-09 sf ops status

def test_E09_current_snapshot_exits_0_and_reports_head_and_counts(repo):
    sf(repo, "ops", "init")
    r = sf(repo, "ops", "status")
    assert r.returncode == 0, r.stderr
    head = git(repo, "rev-parse", "HEAD")
    assert head[:7] in r.stdout
    assert re.search(r"\b0\b", r.stdout), r.stdout  # zero commits behind


def test_E09_behind_commits_exit_4_with_the_git_rev_list_count(repo):
    sf(repo, "ops", "init")
    snap = git(repo, "rev-parse", "HEAD")
    commit(repo, "one", {"a.txt": "1\n"})
    head = commit(repo, "two", {"b.txt": "2\n"})
    r = sf(repo, "ops", "status")
    assert r.returncode == 4
    assert head[:7] in r.stdout and snap[:7] in r.stdout
    assert git(repo, "rev-list", "--count", f"{snap}..{head}") == "2"
    assert re.search(r"\b2\b", r.stdout), r.stdout


def test_E09_no_snapshot_exits_4(repo):
    r = sf(repo, "ops", "status")
    assert r.returncode == 4
    assert git(repo, "rev-parse", "HEAD")[:7] in r.stdout


def test_E09_event_count_is_printed(repo):
    from factory.ops.events import emit
    sf(repo, "ops", "init")
    for i in range(3):
        assert emit(repo, "x", "s", "v", note=str(i))
    commit(repo, "one", {"a.txt": "1\n"})
    commit(repo, "two", {"b.txt": "2\n"})
    commit(repo, "three", {"c.txt": "3\n"})
    commit(repo, "four", {"d.txt": "4\n"})
    out = sf(repo, "ops", "status").stdout
    assert re.search(r"\b3\b", out) and re.search(r"\b4\b", out), out  # 3 events, 4 behind


def test_E09_json_is_one_object_with_the_same_facts(repo):
    from factory.ops.events import emit
    sf(repo, "ops", "init")
    snap = git(repo, "rev-parse", "HEAD")
    emit(repo, "x", "s", "v")
    emit(repo, "x", "s", "v")
    emit(repo, "x", "s", "v")
    commit(repo, "one", {"a.txt": "1\n"})
    head = commit(repo, "two", {"b.txt": "2\n"})
    r = sf(repo, "ops", "status", "--json")
    assert r.returncode == 4
    obj = json.loads(r.stdout)
    assert isinstance(obj, dict)
    vals = list(obj.values())
    assert any(isinstance(v, str) and v.startswith(head[:7]) for v in vals), obj
    assert any(isinstance(v, str) and v.startswith(snap[:7]) for v in vals), obj
    ints = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
    assert 2 in ints and 3 in ints, obj  # behind == 2, events == 3


def test_E09_json_current_exits_0_with_zero_behind(repo):
    sf(repo, "ops", "init")
    r = sf(repo, "ops", "status", "--json")
    assert r.returncode == 0
    obj = json.loads(r.stdout)
    assert 0 in [v for v in obj.values() if isinstance(v, int) and not isinstance(v, bool)]


def test_E09_repo_option_from_another_directory(repo, bare_dir):
    sf(repo, "ops", "init")
    commit(repo, "one", {"a.txt": "1\n"})
    assert sf(bare_dir, "ops", "status", "--repo", str(repo)).returncode == 4


def test_E09_status_writes_nothing_and_leaves_no_event(repo):
    sf(repo, "ops", "init")
    before = snapshot_tree(repo / "ops")
    sf(repo, "ops", "status")
    sf(repo, "ops", "status", "--json")
    assert snapshot_tree(repo / "ops") == before
    assert read_events(repo) == []
