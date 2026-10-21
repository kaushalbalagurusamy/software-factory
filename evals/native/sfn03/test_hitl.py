"""SFN-03 T-07: the human stops view (runtime stop ledger, historical ADRs and hitl events, banner on every tab)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from factory.hitl import store

from .conftest import (SHELL, TABS_SHELL, collect, commit, dump, git, mkrepo, run, runtime, shell_text, tab_blob,
                       tree, write)

REASON_A = "need the owner to pick the pricing model"
REASON_B = "ADR-004 touches a one-way door"


def open_stops(repo):
    store.request(repo, "alpha", REASON_A, scope="slice:billing", by="agent:impl")
    store.request(repo, "beta", REASON_B, scope="run", by="agent:review")


def hitl_rt(repo, config=None):
    rt = runtime(repo, config)
    assert "hitl" in rt, "runtime.json carries the runtime part of the human stops tab under 'hitl'"
    return rt["hitl"]


def stop_file(repo, name):
    return json.loads((Path(repo) / ".factory" / "stops" / f"{name}.json").read_text())


# ---- runtime part ------------------------------------------------------------------------------------------

def test_T07_open_stops_are_listed_with_name_stage_reason_opened_at_and_releaser(tmp_path):
    repo = mkrepo(tmp_path)
    open_stops(repo)
    h = hitl_rt(repo)
    by = {s["name"]: s for s in h["open"]}
    assert set(by) == {"alpha", "beta"}
    a = by["alpha"]
    assert a["reason"] == REASON_A
    assert stop_file(repo, "alpha")["requested_at"] in dump(a), "opened-at comes from the ledger"
    assert "slice:billing" in dump(a), "the stage/scope the stop applies to"
    assert "human" in dump(a).lower(), "who may release: a person, not an agent"
    assert "failed verification" not in dump(h)


def test_T07_a_released_stop_is_no_longer_listed(tmp_path):
    repo = mkrepo(tmp_path)
    open_stops(repo)
    store.release(repo, "alpha", "human:owner", tty_probe=lambda: True)
    assert [s["name"] for s in hitl_rt(repo)["open"]] == ["beta"]


def test_T07_no_ledger_means_zero_open_and_no_failure(tmp_path):
    repo = mkrepo(tmp_path)
    h = hitl_rt(repo)
    assert h["open"] == []
    assert "failed verification" not in dump(h)


@pytest.mark.parametrize("tamper", ["edit-file", "delete-file", "forge-file", "edit-log"])
def test_T07_a_failing_chain_is_shown_as_failed_verification_not_as_zero(tmp_path, tamper):
    repo = mkrepo(tmp_path)
    open_stops(repo)
    d = repo / ".factory" / "stops"
    if tamper == "edit-file":
        (d / "alpha.json").write_text('{"name": "alpha", "reason": "everything is fine"}\n')
    elif tamper == "delete-file":
        (d / "alpha.json").unlink()
    elif tamper == "forge-file":
        (d / "ghost.json").write_text("{}\n")
    else:
        log = d / "log.jsonl"
        log.write_text(log.read_text().replace(REASON_A, "nothing to see"))
    h = hitl_rt(repo)
    assert "stop ledger failed verification" in dump(h)
    assert h.get("open") != [], "a ledger that cannot be verified is not reported as zero stops"


def test_T07_collector_never_writes_to_dot_factory(tmp_path):
    repo = mkrepo(tmp_path)
    open_stops(repo)
    before = tree(repo / ".factory")
    hitl_rt(repo)
    run(repo, "bundle")
    assert tree(repo / ".factory") == before, "bytes and mtimes of every file under .factory are unchanged"


def test_T07_collector_does_not_create_dot_factory_when_there_is_none(tmp_path):
    repo = mkrepo(tmp_path)
    hitl_rt(repo)
    run(repo, "bundle")
    assert not (repo / ".factory").exists()


def test_T07_collector_does_not_write_even_when_the_ledger_is_tampered(tmp_path):
    repo = mkrepo(tmp_path)
    open_stops(repo)
    (repo / ".factory" / "stops" / "alpha.json").write_text("{}\n")
    before = tree(repo / ".factory")
    hitl_rt(repo)
    assert tree(repo / ".factory") == before


# ---- historical part ---------------------------------------------------------------------------------------

def adr(n, status):
    return f"# ADR-{n:03d}: Decision {n}\n\nStatus: {status}\nDate: 2026-10-0{n}\n\nBody.\n"


def event(stage, note, verdict="open"):
    return json.dumps({"at": "2026-10-01T00:00:00Z", "stage": stage, "slice": "s1", "sha": "unknown",
                       "verdict": verdict, "note": note, "source": "sf"}) + "\n"


def test_T07_hitl_is_a_registered_historical_tab():
    from factory.ops import collect as C
    assert "hitl" in C.TABS and "hitl" in C.COLLECTORS


def test_T07_historical_part_lists_proposed_and_pending_adrs_and_hitl_events(tmp_path):
    repo = mkrepo(tmp_path, {
        "docs/adr/ADR-001-a.md": adr(1, "Proposed"), "docs/adr/ADR-002-b.md": adr(2, "Accepted"),
        "docs/adr/ADR-003-c.md": adr(3, "Pending"), "docs/adr/ADR-004-d.md": adr(4, "Superseded"),
        "ops/events.jsonl": event("hitl", "waiting on owner for pricing") + event("4-slice", "triage done", "pass"),
    })
    res = collect(repo, "hitl")
    assert res["available"] is True
    text = dump(res["items"])
    assert "ADR-001" in text and "ADR-003" in text
    assert "ADR-002" not in text and "ADR-004" not in text
    assert "waiting on owner for pricing" in text
    assert "triage done" not in text, "only events with stage hitl"


def test_T07_status_matching_ignores_case_and_bold_markup(tmp_path):
    repo = mkrepo(tmp_path, {"docs/adr/ADR-001-a.md": "# ADR-001: A\n\n**Status:** proposed\n\nBody\n"})
    assert "ADR-001" in dump(collect(repo, "hitl"))


def test_T07_historical_part_is_unavailable_with_the_searched_paths_when_empty(tmp_path):
    repo = mkrepo(tmp_path, {"docs/adr/ADR-002-b.md": adr(2, "Accepted"), "ops/events.jsonl": event("4-slice", "x", "pass")})
    res = collect(repo, "hitl")
    assert res["available"] is False
    assert "docs/adr" in res["reason"] and "events" in res["reason"]


def test_T07_historical_part_reads_the_commit_not_the_working_tree(tmp_path):
    repo = mkrepo(tmp_path, {"docs/adr/ADR-001-a.md": adr(1, "Proposed")})
    sha = git(repo, "rev-parse", "HEAD")
    write(repo, {"docs/adr/ADR-001-a.md": adr(1, "Accepted")})
    assert "ADR-001" in dump(collect(repo, "hitl", sha))


# ---- banner and tab in the shell ---------------------------------------------------------------------------

def test_T07_shell_has_the_hitl_tab_and_both_banner_strings():
    html = SHELL.read_text()
    assert re.search(r'\["hitl"\s*,', html), "a hitl entry in the TABS table"
    assert "open human stop(s)" in html and "human stops unknown" in html


def banner_repo(tmp_path):
    repo = mkrepo(tmp_path, {"docs/adr/ADR-001-a.md": adr(1, "Proposed")})
    open_stops(repo)
    assert run(repo, "bundle").returncode == 0
    hitl_rt(repo)
    return repo


@pytest.fixture(scope="module")
def open_repo(tmp_path_factory):
    return banner_repo(tmp_path_factory.mktemp("open"))


@pytest.mark.parametrize("tab", TABS_SHELL)
def test_T07_banner_with_open_stops_appears_on_every_tab(open_repo, tab):
    assert "2 open human stop(s)" in shell_text(open_repo, tab)


@pytest.mark.parametrize("tab", TABS_SHELL)
def test_T07_banner_says_unknown_when_the_runtime_file_is_absent(open_repo, tab):
    text = shell_text(open_repo, tab, with_runtime=False)
    assert "human stops unknown" in text
    assert "open human stop(s)" not in text


@pytest.mark.parametrize("tab", ["overview", "git"])
def test_T07_no_banner_and_no_unknown_when_the_ledger_is_empty(tmp_path, tab):
    repo = mkrepo(tmp_path)
    run(repo, "bundle")
    hitl_rt(repo)
    text = shell_text(repo, tab)
    assert "open human stop(s)" not in text and "human stops unknown" not in text


def test_T07_banner_counts_one_stop_too(tmp_path):
    repo = mkrepo(tmp_path)
    store.request(repo, "solo", REASON_A, by="agent:impl")
    run(repo, "bundle")
    hitl_rt(repo)
    assert "1 open human stop(s)" in shell_text(repo, "overview")


def test_T07_hitl_tab_lists_open_stops_and_historical_items(open_repo):
    repo = open_repo
    text = shell_text(repo, "hitl")
    for want in ("alpha", "beta", REASON_A, REASON_B, "slice:billing", stop_file(repo, "alpha")["requested_at"], "ADR-001"):
        assert want in text, want


def test_T07_hitl_tab_shows_ledger_failure_not_zero_stops(tmp_path):
    repo = mkrepo(tmp_path)
    store.request(repo, "alpha", REASON_A, by="agent:impl")
    (repo / ".factory" / "stops" / "alpha.json").write_text("{}\n")
    run(repo, "bundle")
    hitl_rt(repo)
    text = shell_text(repo, "hitl")
    assert "stop ledger failed verification" in text
    assert "0 open human stop(s)" not in text


# ---- snapshots exclude the runtime part (T-09 side) --------------------------------------------------------

def test_T09_open_stops_never_enter_a_snapshot(tmp_path):
    repo = mkrepo(tmp_path, {"docs/adr/ADR-001-a.md": adr(1, "Proposed")})
    store.request(repo, "zzuniquestop", "zzuniquereason must stay out of history", by="agent:impl")
    assert run(repo, "bundle").returncode == 0
    for f in (repo / "ops").rglob("*.json"):
        t = f.read_text(errors="replace")
        assert "zzuniquestop" not in t and "zzuniquereason" not in t, f
    sha = git(repo, "rev-parse", "HEAD")
    man = json.loads((repo / "ops" / "snapshots" / sha / "manifest.json").read_text())
    assert "hitl" in man["tabs"] and man["tabs"]["hitl"]["available"] is True
