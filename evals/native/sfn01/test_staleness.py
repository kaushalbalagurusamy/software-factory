"""SFN-01 E-11 (staleness), E-12 (dev journey fills), E-13 (events are history, telemetry is not)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import REPO, child_env, commit, git, read_events, sf

SHELL = REPO / "ops" / "shell" / "index.html"


def manifest(repo, sha) -> dict:
    return json.loads((repo / "ops" / "snapshots" / sha / "manifest.json").read_text())


def tab_blob(repo, sha, tab) -> dict:
    t = manifest(repo, sha)["tabs"][tab]
    return json.loads((repo / "ops" / "blobs" / f"{t['blob']}.json").read_text())


def ev_line(at, stage="7-qa", slice_id="s1", verdict="pass") -> str:
    return json.dumps({"at": at, "stage": stage, "slice": slice_id, "sha": "abc", "verdict": verdict, "note": ""}) + "\n"


# ------------------------------------------------------------------ E-11

def test_E11_index_json_records_the_head_the_bundle_ran_from(repo):
    r = sf(repo, "ops", "bundle")
    assert r.returncode == 0, r.stderr
    idx = json.loads((repo / "ops" / "index.json").read_text())
    assert idx["head"] == git(repo, "rev-parse", "HEAD")
    commit(repo, "later", {"a.txt": "1\n"})
    sf(repo, "ops", "bundle")
    assert json.loads((repo / "ops" / "index.json").read_text())["head"] == git(repo, "rev-parse", "HEAD")


def test_E11_index_json_keeps_its_existing_shape(repo):
    sf(repo, "ops", "bundle")
    idx = json.loads((repo / "ops" / "index.json").read_text())
    assert idx["schema"] == 1 and idx["commits"][0]["sha"] == git(repo, "rev-parse", "HEAD")


def test_E11_runtime_json_gets_repo_head_and_behind(repo):
    sf(repo, "ops", "init")
    r = sf(repo, "ops", "runtime")
    assert r.returncode == 0, r.stderr
    rt = json.loads((repo / "ops" / "runtime.json").read_text())
    assert rt["repo_head"] == git(repo, "rev-parse", "HEAD")
    assert rt["behind"] == 0


def test_E11_behind_counts_commits_since_the_newest_snapshot(repo):
    sf(repo, "ops", "init")
    commit(repo, "one", {"a.txt": "1\n"})
    head = commit(repo, "two", {"b.txt": "2\n"})
    sf(repo, "ops", "runtime")
    rt = json.loads((repo / "ops" / "runtime.json").read_text())
    assert rt["repo_head"] == head and rt["behind"] == 2
    sf(repo, "ops", "bundle")
    sf(repo, "ops", "runtime")
    assert json.loads((repo / "ops" / "runtime.json").read_text())["behind"] == 0


def test_E11_runtime_command_still_labels_its_figures_and_stays_exit_0(repo):
    sf(repo, "ops", "init")
    sf(repo, "ops", "runtime")
    rt = json.loads((repo / "ops" / "runtime.json").read_text())
    assert "figures" in rt and "as_of" in rt


@pytest.mark.parametrize("needle", [
    "commits behind the repository", "Snapshot is ", "Up to date", "Repository state unknown",
])
def test_E11_viewer_shell_has_the_staleness_banner_wording(needle):
    html = SHELL.read_text(encoding="utf-8")
    assert needle in html, f"ops/shell/index.html is missing the banner text {needle!r}"


def test_E11_viewer_shell_reads_behind_from_runtime_json():
    html = SHELL.read_text(encoding="utf-8")
    assert "behind" in html and "runtime.json" in html


# ------------------------------------------------------------------ E-12

def test_E12_a_snapshot_with_committed_events_shows_them_in_dev_journey(repo):
    from factory.ops.events import emit
    for stage in ("4-slice", "5-evals", "7-qa"):
        assert emit(repo, stage, "s1", "pass")
    git(repo, "add", "--", "ops/events.jsonl")
    sha = commit(repo, "with events")
    assert sf(repo, "ops", "bundle", env=child_env(SF_EVENTS="off")).returncode == 0
    m = manifest(repo, sha)["tabs"]["dev_journey"]
    assert m["available"] is True
    evs = tab_blob(repo, sha, "dev_journey")["events"]
    assert [e["stage"] for e in evs] == ["4-slice", "5-evals", "7-qa"]
    assert all(e["slice"] == "s1" for e in evs)


def test_E12_events_emitted_by_sf_commands_reach_the_dev_journey_tab(repo):
    (repo / "docs" / "slices").mkdir(parents=True)
    sf(repo, "slice", "triage", "--root", "docs/slices")  # E-04 writes the event
    assert len(read_events(repo)) == 1
    git(repo, "add", "--", "ops/events.jsonl")
    sha = commit(repo, "commit the events")
    sf(repo, "ops", "bundle", env=child_env(SF_EVENTS="off"))
    evs = tab_blob(repo, sha, "dev_journey")["events"]
    assert [(e["stage"], e["verdict"]) for e in evs] == [("4-slice", "pass")]


def test_E12_no_events_at_all_reports_not_available_with_the_stated_reason(repo):
    sha = git(repo, "rev-parse", "HEAD")
    out = sf(repo, "ops", "init").stdout
    tab = manifest(repo, sha)["tabs"]["dev_journey"]
    assert tab["available"] is False
    assert "no stage events recorded" in tab["reason"]
    line = [ln for ln in out.splitlines() if "dev" in ln.lower() and "journey" in ln.lower().replace("_", " ")]
    assert len(line) == 1 and "not available: no stage events recorded" in line[0]


def test_E12_an_empty_events_file_is_the_same_as_no_events(repo):
    sf(repo, "ops", "init")
    git(repo, "add", "--", "ops/events.jsonl")
    sha = commit(repo, "empty events file")
    sf(repo, "ops", "bundle", env=child_env(SF_EVENTS="off"))
    tab = manifest(repo, sha)["tabs"]["dev_journey"]
    assert tab["available"] is False and "no stage events recorded" in tab["reason"]


def test_E12_viewer_renders_the_unavailable_reason_rather_than_an_empty_table():
    html = SHELL.read_text(encoding="utf-8")
    assert "d.reason" in html and "unavailable" in html.lower()  # the not-available card shows the collector's reason


# ------------------------------------------------------------------ E-13

def test_E13_events_after_the_snapshot_commit_date_are_filtered_out(repo):
    lines = "".join([
        ev_line("2025-12-31T23:59:59+00:00", "e1-before"),
        ev_line("2026-01-01T12:00:00+00:00", "e2-equal"),
        ev_line("2026-01-01T12:00:01+00:00", "e3-after-by-1s"),
        ev_line("2026-02-01T00:00:00+00:00", "e4-after"),
    ])
    sha = commit(repo, "dated", {"ops/events.jsonl": lines}, date="2026-01-01T12:00:00+0000")
    sf(repo, "ops", "bundle", env=child_env(SF_EVENTS="off"))
    evs = tab_blob(repo, sha, "dev_journey")["events"]
    assert [e["stage"] for e in evs] == ["e1-before", "e2-equal"]


def test_E13_the_comparison_is_by_instant_not_by_string(repo):
    # commit date 12:00 at +02:00 is 10:00Z; an event at 11:00Z is later even though "11" > "12" is false as text
    lines = ev_line("2026-01-01T09:00:00+00:00", "early") + ev_line("2026-01-01T11:00:00+00:00", "late-in-utc") \
        + ev_line("2026-01-01T11:30:00+02:00", "early-with-offset")
    sha = commit(repo, "tz", {"ops/events.jsonl": lines}, date="2026-01-01T12:00:00+0200")
    sf(repo, "ops", "bundle", env=child_env(SF_EVENTS="off"))
    evs = tab_blob(repo, sha, "dev_journey")["events"]
    assert sorted(e["stage"] for e in evs) == ["early", "early-with-offset"]


def test_E13_older_snapshots_do_not_show_newer_events(repo):
    first = commit(repo, "first", {"ops/events.jsonl": ev_line("2026-01-01T00:00:00+00:00", "old")},
                   date="2026-01-01T00:00:00+0000")
    second = commit(repo, "second", {"ops/events.jsonl": ev_line("2026-01-01T00:00:00+00:00", "old")
                                     + ev_line("2026-03-01T00:00:00+00:00", "new")}, date="2026-03-01T00:00:00+0000")
    sf(repo, "ops", "bundle", "--sha", second, env=child_env(SF_EVENTS="off"))
    sf(repo, "ops", "bundle", "--sha", first, env=child_env(SF_EVENTS="off"))
    assert [e["stage"] for e in tab_blob(repo, first, "dev_journey")["events"]] == ["old"]
    assert [e["stage"] for e in tab_blob(repo, second, "dev_journey")["events"]] == ["old", "new"]


def test_E13_runtime_telemetry_never_enters_a_snapshot(repo):
    sf(repo, "ops", "init")
    commit(repo, "more", {"a.txt": "1\n"})
    sf(repo, "ops", "runtime")
    assert (repo / "ops" / "runtime.json").is_file()
    sf(repo, "ops", "bundle")
    for sub in ("snapshots", "blobs"):
        for p in (repo / "ops" / sub).rglob("*.json"):
            text = p.read_text()
            assert '"repo_head"' not in text and '"figures"' not in text and '"behind"' not in text, p
    idx = (repo / "ops" / "index.json").read_text()
    assert '"behind"' not in idx and '"figures"' not in idx


def test_E13_snapshot_of_the_same_commit_is_stable_after_events_are_appended_later(repo):
    sha = commit(repo, "one", {"ops/events.jsonl": ev_line("2026-01-01T00:00:00+00:00", "a")},
                 date="2026-01-01T00:00:00+0000")
    sf(repo, "ops", "bundle", "--sha", sha, env=child_env(SF_EVENTS="off"))
    before = (repo / "ops" / "snapshots" / sha / "manifest.json").read_bytes()
    from factory.ops.events import emit
    emit(repo, "later", "s", "v")  # working-tree only, not in the commit
    sf(repo, "ops", "bundle", "--sha", sha, env=child_env(SF_EVENTS="off"))
    assert (repo / "ops" / "snapshots" / sha / "manifest.json").read_bytes() == before
    assert [e["stage"] for e in tab_blob(repo, sha, "dev_journey")["events"]] == ["a"]
