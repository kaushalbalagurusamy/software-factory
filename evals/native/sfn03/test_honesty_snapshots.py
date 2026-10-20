"""SFN-03 T-08 (no fake availability), T-09 (snapshots reproducible), T-10 (nothing existing breaks)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from .conftest import REPO, collect, commit, dump, env, git, mkrepo, onepager, run, write

# collector name -> text that must appear in the reason (a path it searched)
EMPTY_REASONS = {
    "architecture": ["docs/explorer"],
    "research": ["research/"],
    "experiments": ["experiments/"],
    "adrs": ["docs/adr"],
    "prd_journeys": ["docs/prd/onepager.md", "docs/slices/*/proposal.md", "docs/prds/*.md"],
    "evals": ["evals/agents"],
    "bug_log": ["docs/bugs"],
    "dev_journey": ["docs/slices"],
    "hitl": ["docs/adr"],
}


@pytest.mark.parametrize("tab", sorted(EMPTY_REASONS))
def test_T08_an_empty_source_is_unavailable_and_names_the_searched_path(tmp_path, tab):
    res = collect(mkrepo(tmp_path), tab)
    assert res["available"] is False, res
    for path in EMPTY_REASONS[tab]:
        assert path in res["reason"], (tab, res["reason"])


@pytest.mark.parametrize("content", ["", "\n\n", "   \n"], ids=["zero-bytes", "blank-lines", "spaces"])
def test_T08_a_bug_log_file_with_no_entries_is_not_available(tmp_path, content):
    res = collect(mkrepo(tmp_path, {"docs/bug-log.jsonl": content}), "bug_log")
    assert res["available"] is False
    assert "bug-log.jsonl" in res["reason"] and "docs/bugs" in res["reason"]


def test_T08_unrelated_files_in_the_searched_directories_do_not_count(tmp_path):
    files = {"docs/bugs/notes.txt": "x", "research/data.csv": "a,b", "docs/adr/README": "x",
             "experiments/stray.txt": "x", "docs/slices/README.md": "x"}
    repo = mkrepo(tmp_path, files)
    for tab in ("bug_log", "research", "adrs", "experiments"):
        assert collect(repo, tab)["available"] is False, tab


def test_T08_available_always_comes_with_at_least_one_item(tmp_path):
    repo = mkrepo(tmp_path, {
        "docs/prd/onepager.md": onepager([("J", ["s1"], ["x"])]),
        "docs/slices/s1/proposal.md": "# S1\n\npriority: P1\n",
        "docs/bugs/b1.md": "# Bug\n\nStatus: open\n",
        "docs/adr/ADR-001-a.md": "# ADR-001: A\n\nStatus: Proposed\n",
        "research/r.md": "# R\n\nas of: 2026-10-01\n",
        "experiments/q/resolved.json": json.dumps({"question": "q", "resolved_by": "r", "sources": ["s"], "as_of": "2026-10-01"}),
    })
    from factory.ops import collect as C
    for tab in C.TABS:
        res = C.COLLECTORS[tab](C.GitSource(repo, "HEAD"))
        if res["available"]:
            assert len(res["items"]) >= 1, tab
            assert res["summary"]["count"] == len(res["items"]), tab
        else:
            assert res["reason"].strip(), tab


def test_T08_unavailable_tabs_in_the_snapshot_carry_their_reason(tmp_path):
    repo = mkrepo(tmp_path)
    assert run(repo, "bundle").returncode == 0
    sha = git(repo, "rev-parse", "HEAD")
    man = json.loads((repo / "ops" / "snapshots" / sha / "manifest.json").read_text())
    for tab in ("prd_journeys", "bug_log", "hitl", "experiments"):
        t = man["tabs"][tab]
        assert t["available"] is False and t["reason"], tab


# ---- T-09 --------------------------------------------------------------------------------------------------

def content_files(version):
    return {
        "docs/prd/onepager.md": onepager([(f"Journey v{version}", ["s1"], [f"step v{version}"])]),
        "docs/slices/s1/proposal.md": f"# S1 v{version}\n\npriority: P1\nllm_features: true\n",
        "docs/bugs/b1.md": f"# Bug v{version}\n\nStatus: {'open' if version == 1 else 'fixed'}\n",
        "docs/adr/ADR-001-a.md": f"# ADR-001: A v{version}\n\nStatus: {'Proposed' if version == 1 else 'Accepted'}\n",
        "experiments/q/resolved.json": json.dumps({"question": f"q v{version}", "resolved_by": "r", "sources": ["s"],
                                                   "as_of": "2026-10-01"}),
    }


def manifest_tabs(repo, sha, out):
    return json.loads((repo / out / "snapshots" / sha / "manifest.json").read_text())["tabs"]


def test_T09_an_old_commit_rebuilds_to_the_same_snapshot_after_later_commits(tmp_path):
    repo = mkrepo(tmp_path, content_files(1))
    c1 = git(repo, "rev-parse", "HEAD")
    assert run(repo, "bundle", "--sha", c1, "--out", "ops1", "--no-viewer").returncode == 0
    commit(repo, content_files(2), "later")
    commit(repo, {"docs/bugs/b2.md": "# Another\n\nStatus: open\n"}, "later again")
    assert run(repo, "bundle", "--out", "ops1", "--no-viewer").returncode == 0  # HEAD lands in the same store
    assert run(repo, "bundle", "--sha", c1, "--out", "ops2", "--no-viewer").returncode == 0
    t1, t2 = manifest_tabs(repo, c1, "ops1"), manifest_tabs(repo, c1, "ops2")
    assert t1 == t2, "same commit, same collectors: identical tab blobs and summaries"
    for tab in ("prd_journeys", "bug_log", "experiments", "hitl"):
        assert t1[tab]["available"] is True, tab


def test_T09_collectors_at_an_old_sha_ignore_later_commits_and_the_working_tree(tmp_path):
    from factory.ops import collect as C
    repo = mkrepo(tmp_path, content_files(1))
    c1 = git(repo, "rev-parse", "HEAD")
    before = {t: dump(C.COLLECTORS[t](C.GitSource(repo, c1))) for t in C.TABS if t != "git"}
    commit(repo, content_files(2), "later")
    write(repo, {"docs/prd/onepager.md": onepager([("Uncommitted", ["s1"], ["wip"])]),
                 "docs/bugs/new.md": "# New\n\nStatus: open\n"})
    after = {t: dump(C.COLLECTORS[t](C.GitSource(repo, c1))) for t in C.TABS if t != "git"}
    assert before == after
    assert "Journey v1" in before["prd_journeys"] and "Uncommitted" not in before["prd_journeys"]


def test_T09_two_builds_of_one_commit_are_byte_identical(tmp_path):
    repo = mkrepo(tmp_path, content_files(1))
    c1 = git(repo, "rev-parse", "HEAD")
    for out in ("a", "b"):
        assert run(repo, "bundle", "--sha", c1, "--out", out, "--no-viewer").returncode == 0
    blobs_a = {p.name: p.read_bytes() for p in (repo / "a" / "blobs").iterdir()}
    blobs_b = {p.name: p.read_bytes() for p in (repo / "b" / "blobs").iterdir()}
    assert blobs_a == blobs_b


def test_T09_the_manifest_is_historical_and_holds_no_runtime_part(tmp_path):
    repo = mkrepo(tmp_path, content_files(1))
    c1 = git(repo, "rev-parse", "HEAD")
    assert run(repo, "bundle", "--sha", c1, "--out", "ops", "--no-viewer").returncode == 0
    man = json.loads((repo / "ops" / "snapshots" / c1 / "manifest.json").read_text())
    assert man["kind"] == "historical"
    assert not [k for k in man if "runtime" in k.lower()]
    assert not [k for k in man["tabs"] if "runtime" in k.lower() or k == "langfuse"]


def test_T09_llm_features_declared_in_a_proposal_do_not_depend_on_runtime(tmp_path):
    repo = mkrepo(tmp_path, content_files(1))
    c1 = git(repo, "rev-parse", "HEAD")
    run(repo, "bundle", "--sha", c1, "--out", "ops", "--no-viewer")
    write(repo, {"ops/runtime.json": json.dumps({"hitl": {"open": [{"name": "late"}]}})})
    run(repo, "bundle", "--sha", c1, "--out", "ops-again", "--no-viewer")
    assert manifest_tabs(repo, c1, "ops") == manifest_tabs(repo, c1, "ops-again")


# ---- T-10 --------------------------------------------------------------------------------------------------

EXISTING = ["tests/test_ops.py", "tests/test_ops_security.py", "tests/test_ops_events.py", "tests/test_ops_cli_native.py"]


def test_T10_existing_ops_suites_pass_unedited():
    r = subprocess.run([sys.executable, "-m", "pytest", *EXISTING, "-q", "-p", "no:cacheprovider", "-x"],
                       cwd=str(REPO), capture_output=True, text=True, env=env(), timeout=100)
    assert r.returncode == 0, r.stdout[-2500:] + r.stderr[-500:]


def test_T10_the_listed_files_exist_and_are_unmodified_by_this_slice():
    for rel in EXISTING:
        assert (REPO / rel).is_file(), rel
    diff = subprocess.run(["git", "-C", str(REPO), "diff", "--name-only", "HEAD", "--", *EXISTING],
                          capture_output=True, text=True)
    assert diff.stdout.strip() == "", "existing ops tests must not be edited"


def test_T10_existing_collector_shapes_are_unchanged(tmp_path):
    repo = mkrepo(tmp_path, {"docs/slices/s1/proposal.md": "# S1\n\npriority: P1\n\n## UX story\n- As a user I act\n",
                             "research/r.md": "# R\n\nas of: 2026-10-01\n",
                             "docs/adr/ADR-001-a.md": "# ADR-001: A\n\nStatus: Accepted\nDate: 2026-10-01\n"})
    prd = collect(repo, "prd_journeys")
    s = [i for i in prd["items"] if i.get("slice") == "s1"][0]
    assert s["stories"] == ["As a user I act"] and s["priority"] == "P1" and s["path"] == "docs/slices/s1/proposal.md"
    assert collect(repo, "research")["items"][0]["as_of"] == "2026-10-01"
    assert collect(repo, "adrs")["items"][0]["status"] == "Accepted"
