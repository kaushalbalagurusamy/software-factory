"""SFN-03 T-01 (one-page core PRD journeys) and T-02 (other PRD sources)."""
from __future__ import annotations

import pytest

from .conftest import collect, dump, find_key, mkrepo, onepager, onepager_with_lines, shell_text, run

ONEPAGER = "docs/prd/onepager.md"
SLICE_MD = "# Slice {}\n\npriority: P1\n\n## UX story\n- As a user I do a thing\n"


def journeys(res):
    assert res["available"] is True, res
    return [i for i in res["items"] if i.get("kind") == "journey"]


def by_name(res, name):
    got = [j for j in journeys(res) if j["name"] == name]
    assert len(got) == 1, (name, [j.get("name") for j in journeys(res)])
    return got[0]


def slice_exists(j):
    """{slice id: exists} from the journey's `slices` list of {id, exists}."""
    return {s["id"]: s["exists"] for s in j["slices"]}


def repo_with(tmp_path, page, slices=("s1", "s2")):
    files = {ONEPAGER: page}
    for s in slices:
        files[f"docs/slices/{s}/proposal.md"] = SLICE_MD.format(s)
    return mkrepo(tmp_path, files)


def test_T01_journeys_have_name_steps_and_slice_existence(tmp_path):
    page = onepager([("Sign up", ["s1", "s2"], ["Open the app", "Enter email", "Confirm"]),
                     ("Check out", ["s1"], ["Add to cart"])])
    res = collect(repo_with(tmp_path, page), "prd_journeys")
    j = by_name(res, "Sign up")
    assert j["steps"] == ["Open the app", "Enter email", "Confirm"]
    assert slice_exists(j) == {"s1": True, "s2": True}
    assert by_name(res, "Check out")["steps"] == ["Add to cart"]
    assert "Core PRD" in dump(res)  # the page's title line is carried


def test_T01_journey_order_follows_the_page(tmp_path):
    page = onepager([("Zeta", ["s1"], ["a"]), ("Alpha", ["s1"], ["b"]), ("Mid", ["s1"], ["c"])])
    names = [j["name"] for j in journeys(collect(repo_with(tmp_path, page), "prd_journeys"))]
    assert names == ["Zeta", "Alpha", "Mid"]


def test_T01_unknown_slice_id_is_flagged_and_known_one_is_not(tmp_path):
    page = onepager([("Mixed", ["s1", "ghost"], ["step"]), ("Clean", ["s1"], ["step"])])
    res = collect(repo_with(tmp_path, page), "prd_journeys")
    mixed, clean = by_name(res, "Mixed"), by_name(res, "Clean")
    assert slice_exists(mixed) == {"s1": True, "ghost": False}
    assert "unknown slice" in dump(mixed["flags"]) and "ghost" in dump(mixed["flags"])
    assert "unknown slice" not in dump(clean)


def test_T01_slice_directory_without_proposal_still_counts_as_existing(tmp_path):
    r = mkrepo(tmp_path, {ONEPAGER: onepager([("J", ["bare"], ["x"])]), "docs/slices/bare/tasks.md": "- [ ] t\n"})
    assert slice_exists(by_name(collect(r, "prd_journeys"), "J")) == {"bare": True}


def test_T01_only_slice_ids_naming_a_directory_not_a_file_exist(tmp_path):
    r = mkrepo(tmp_path, {ONEPAGER: onepager([("J", ["afile"], ["x"])]), "docs/slices/afile": "i am a file\n"})
    assert slice_exists(by_name(collect(r, "prd_journeys"), "J")) == {"afile": False}


def test_T01_missing_slices_line_returns_the_journey_with_a_flag(tmp_path):
    page = onepager([("No slices", None, ["step one"]), ("Fine", ["s1"], ["step"])])
    res = collect(repo_with(tmp_path, page), "prd_journeys")
    j = by_name(res, "No slices")
    assert j["slices"] == [] and j["steps"] == ["step one"]
    assert j["flags"], "a journey with no Slices line must be flagged"
    assert not by_name(res, "Fine").get("flags")


@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (5, True), (6, False)])
def test_T01_step_count_boundaries_zero_one_five_six(tmp_path, n, ok):
    steps = [f"step {i}" for i in range(n)]
    res = collect(repo_with(tmp_path, onepager([("J", ["s1"], steps)])), "prd_journeys")
    j = by_name(res, "J")
    assert j["steps"] == steps, "steps are returned as written, never truncated or dropped"
    assert (not j.get("flags")) is ok, j


def test_T01_exactly_80_lines_has_no_warning(tmp_path):
    res = collect(repo_with(tmp_path, onepager_with_lines(80)), "prd_journeys")
    assert find_key(res, "warning") == [] or all(not w for w in find_key(res, "warning")), dump(res)
    by_name(res, "Last journey")


def test_T01_81_lines_warns_and_keeps_every_journey(tmp_path):
    res = collect(repo_with(tmp_path, onepager_with_lines(81)), "prd_journeys")
    assert "longer than one page" in find_key(res, "warning")
    j = by_name(res, "Last journey")  # the content at the end of the long page is not cut off
    assert j["steps"] == ["only step"]


def test_T01_a_very_long_page_is_never_truncated(tmp_path):
    many = [(f"Journey {i}", ["s1"], ["a", "b"]) for i in range(60)]
    res = collect(repo_with(tmp_path, onepager(many)), "prd_journeys")
    assert len(journeys(res)) == 60
    assert "longer than one page" in find_key(res, "warning")


def test_T01_journey_without_the_prefix_heading_is_not_a_journey(tmp_path):
    page = "# Core PRD\n\n## Overview\nSlices: s1\n- not a journey\n\n## Journey: Real\nSlices: s1\n- yes\n"
    assert [j["name"] for j in journeys(collect(repo_with(tmp_path, page), "prd_journeys"))] == ["Real"]


def test_T02_proposals_prds_and_onepager_all_listed(tmp_path):
    r = mkrepo(tmp_path, {
        ONEPAGER: onepager([("J", ["s1"], ["x"])]),
        "docs/slices/s1/proposal.md": SLICE_MD.format("s1"),
        "docs/prds/SFN-99-thing.md": "# SFN-99: A thing\n\n| | |\n|---|---|\n| **Delivers** | Owner clauses X1, X2 |\n\nBody.\n",
    })
    res = collect(r, "prd_journeys")
    kinds = {i.get("kind") for i in res["items"]}
    assert "journey" in kinds and "prd" in kinds
    assert any(i.get("slice") == "s1" and i["stories"] for i in res["items"]), "proposals keep their existing shape"
    prd = [i for i in res["items"] if i.get("kind") == "prd"]
    assert len(prd) == 1 and prd[0]["path"] == "docs/prds/SFN-99-thing.md"
    assert "A thing" in prd[0]["title"]
    assert "Owner clauses X1, X2" in dump(prd[0])


@pytest.mark.parametrize("files", [
    {"docs/prds/P.md": "# P\n\nDelivers: x\n"},
    {"docs/slices/s1/proposal.md": SLICE_MD.format("s1")},
    {ONEPAGER: onepager([("J", ["s1"], ["x"])])},
], ids=["prds-only", "proposals-only", "onepager-only"])
def test_T02_any_single_source_makes_the_tab_available(tmp_path, files):
    assert collect(mkrepo(tmp_path, files), "prd_journeys")["available"] is True


def test_T02_unavailable_reason_names_all_three_paths(tmp_path):
    res = collect(mkrepo(tmp_path), "prd_journeys")
    assert res["available"] is False
    for path in ("docs/prd/onepager.md", "docs/slices/*/proposal.md", "docs/prds/*.md"):
        assert path in res["reason"], res["reason"]


def test_T08_onepager_without_any_journey_is_not_available(tmp_path):
    res = collect(mkrepo(tmp_path, {ONEPAGER: "# Core PRD\n\nJust prose, no journeys.\n"}), "prd_journeys")
    assert res["available"] is False
    assert "onepager.md" in res["reason"]


def test_T01_prd_tab_renders_journeys_steps_and_unknown_slice_flag(tmp_path):
    page = onepager([("Browse catalogue", ["s1", "ghost"], ["Open the shelf", "Pick a book"])])
    r = repo_with(tmp_path, page)
    assert run(r, "bundle").returncode == 0
    text = shell_text(r, "prd")
    for want in ("Browse catalogue", "Open the shelf", "Pick a book", "unknown slice"):
        assert want in text, want
