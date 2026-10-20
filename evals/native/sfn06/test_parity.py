"""L-11 same file conventions / parity with factory.ops.collect, L-10 data side ('not available: <path>'),
L-15 bounds. lsf is only ever run as a subprocess (`lsf bundle --json`); factory.ops.collect is imported for the oracle."""
from __future__ import annotations

import json
import time

import pytest

from .conftest import Rig, find_key, walk

REQUIRED = ["research", "experiments", "adrs", "bug_log", "prd_journeys", "architecture", "git"]


def build_fixture(rig: Rig):
    rig.write("research/alpha.md", "# Alpha findings\n\nAs of: 2026-10-01.\n")
    rig.write("research/beta.md", "# Beta notes\n")
    rig.write("experiments/e1/results.json", json.dumps({"winner": "sqlite", "n": 3}))
    rig.write("experiments/e1/resolved.json", json.dumps({"resolved": True}))
    rig.write("experiments/e2/results.json", "{ broken json")
    rig.write("docs/adr/ADR-0001-use-sqlite.md", "# ADR-0001 Use SQLite\n\n**Status:** Accepted\n**Date:** 2026-10-02\n")
    rig.write("docs/adr/ADR-0002-queue.md", "# Queue choice\n\nStatus: Proposed\nDate: 2026-10-03\n")
    rig.write("docs/slices/s1/proposal.md", "# Slice one\npriority: P1\n\n## UX stories\n- As a user I log in\n- As a user I log out\n")
    rig.write("docs/slices/s2/proposal.md", "# Slice two\npriority: P0\n\n## User stories\n1. As an admin I audit\n")
    rig.write("docs/bugs/b1.md", "# Bug one\n\n**Status:** open\n")
    rig.write("docs/bugs/b2.md", "# Bug two\n\nStatus: fixed\n")
    rig.write("docs/explorer/m.model.json", json.dumps({"meta": {"title": "Model"}, "nodes": {"a": {"diagram": "graph TD"}, "b": {}}}))
    rig.commit(["research", "experiments", "docs"], "fixture artifacts")


def canon(items):
    return sorted(json.dumps(i, sort_keys=True) for i in items)


@pytest.fixture
def fixture_rig(rig):
    build_fixture(rig)
    rig.init()
    return rig


def tab(bundle, name):
    t = find_key(bundle, name)
    assert isinstance(t, dict), f"bundle has no tab {name!r}"
    return t


def test_L11_parity_with_factory_ops_collect(fixture_rig):
    from factory.ops import collect
    oracle = collect.collect_all(collect.GitSource(fixture_rig.repo, "HEAD"))
    bundle = fixture_rig.bundle()
    for name in REQUIRED:
        mine, theirs = tab(bundle, name), oracle[name]
        assert mine["available"] == theirs["available"], name
        if not theirs["available"]:
            continue
        a, b = list(mine["items"]), list(theirs["items"])
        if name == "architecture":
            a = [{k: v for k, v in i.items() if k != "model"} for i in a]
            b = [{k: v for k, v in i.items() if k != "model"} for i in b]
        assert canon(a) == canon(b), name


def test_L11_unavailable_tabs_agree_with_the_oracle_on_an_empty_repo(rig):
    from factory.ops import collect
    rig.init()
    oracle = collect.collect_all(collect.GitSource(rig.repo, "HEAD"))
    bundle = rig.bundle()
    for name in ("research", "experiments", "adrs", "bug_log", "prd_journeys", "architecture"):
        assert oracle[name]["available"] is False
        assert tab(bundle, name)["available"] is False, name


def test_L11_every_tab_reads_the_contract_paths(fixture_rig):
    b = fixture_rig.bundle()
    assert len(tab(b, "research")["items"]) == 2
    assert {i["name"] for i in tab(b, "experiments")["items"]} == {"e1", "e2"}
    assert any("error" in i for i in tab(b, "experiments")["items"]), "broken results.json is reported, not skipped"
    assert len(tab(b, "adrs")["items"]) == 2
    assert len(tab(b, "bug_log")["items"]) == 2
    assert len(tab(b, "prd_journeys")["items"]) == 2
    assert len(tab(b, "git")["items"]) >= 2


def test_L11_working_tree_changes_show_up(fixture_rig):
    fixture_rig.write("research/gamma.md", "# Gamma uncommitted\n")
    assert any(i["path"] == "research/gamma.md" for i in tab(fixture_rig.bundle(), "research")["items"])


NAMED = {  # tab -> path fragments an empty repo's reason must name (any one of them)
    "research": ("research/",),
    "experiments": ("experiments/",),
    "adrs": ("docs/adr",),
    "bug_log": ("docs/bugs",),
    "prd_journeys": ("docs/slices", "docs/prd"),
    "architecture": ("docs/explorer",),
    "docs": ("docs/eli12",),
}


@pytest.mark.parametrize("name", sorted(NAMED))
def test_L10_unavailable_reason_names_the_path_searched(inited, name):
    t = tab(inited.bundle(), name)
    assert t["available"] is False
    assert any(f in t["reason"] for f in NAMED[name]), t["reason"]
    assert "items" not in t or not t["items"]


def test_L10_available_is_never_reported_with_zero_items(inited):
    # directories exist on disk but hold nothing a tab reads
    for d in ("research", "experiments", "docs/adr", "docs/bugs", "docs/slices", "docs/explorer", "docs/eli12"):
        (inited.repo / d).mkdir(parents=True)
    (inited.repo / "docs/adr/README.txt").write_text("not an ADR\n")
    b = inited.bundle()
    for name in NAMED:
        t = tab(b, name)
        assert t["available"] is False, (name, t)
    for d in walk(b):
        if d.get("available") is True and "items" in d:
            assert len(d["items"]) > 0, d


def test_L10_docs_tab_reads_eli12_index(inited):
    inited.write("docs/eli12/INDEX.md", "# Index\n- a.b: does a thing\n")
    inited.write("docs/eli12/a.b.md", "# a/b.py\n\nThis file does a thing.\n")
    inited.write("docs/eli12/index.json", json.dumps({"a/b.py": "docs/eli12/a.b.md"}))
    t = tab(inited.bundle(), "docs")
    assert t["available"] is True and t["items"]


def test_L11_slices_without_stories_do_not_crash(inited):
    inited.write("docs/slices/s9/proposal.md", "# No stories here\n")
    t = tab(inited.bundle(), "prd_journeys")
    assert t["available"] is True and t["items"][0]["stories"] == []


# ---------------------------------------------------------------- L-15 bounds
def test_L15_oversized_file_is_not_read_into_the_bundle(inited):
    inited.write("docs/adr/ADR-0007-big.md", "# Huge\n\n" + "x" * (6 * 1024 * 1024))
    inited.write("docs/adr/ADR-0008-small.md", "# Small\n**Status:** Accepted\n")
    p = inited.run("bundle", "--json", timeout=30)
    assert p.returncode in (0, 1) and "Traceback" not in p.stderr
    assert len(p.stdout) < 2 * 1024 * 1024
    if p.returncode == 0:
        assert "ADR-0008-small" in p.stdout


def test_L15_file_listing_is_capped(inited):
    d = inited.repo / "research"
    d.mkdir()
    for i in range(21000):
        (d / f"n{i}.md").write_bytes(b"#\n")
    t0 = time.time()
    p = inited.run("bundle", "--json", timeout=60)
    assert time.time() - t0 < 40
    assert p.returncode in (0, 1) and "Traceback" not in p.stderr
    if p.returncode == 0:
        items = tab(json.loads(p.stdout), "research").get("items", [])
        assert len(items) <= 20000


def test_L15_skip_dirs_are_not_scanned(inited):
    for skip in (".git", "node_modules", ".venv"):
        inited.write(f"{skip}/pkg/docs/adr/ADR-0099-hidden.md", "# hidden\n")
        inited.write(f"{skip}/pkg/research/hidden.md", "# hidden\n")
    p = inited.run("bundle", "--json", timeout=30)
    assert p.returncode == 0 and "ADR-0099" not in p.stdout and "hidden.md" not in p.stdout


def test_L15_bundle_makes_no_network_request(inited):
    p = inited.run("bundle", "--json", env={"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
                                            "no_proxy": ""}, timeout=30)
    assert p.returncode == 0 and "Traceback" not in p.stderr
