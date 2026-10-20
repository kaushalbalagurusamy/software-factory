"""SFN-03 T-03 (experiments incl. resolved.json) and T-04 (bug log)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import collect, dump, mkrepo, run, shell_text

VALID_RESOLVED = {"question": "Which queue library?", "resolved_by": "research/queues.md",
                  "sources": ["https://example.org/benchmarks"], "as_of": "2026-10-01"}


def check(root: Path, *extra):
    return run(root, "experiments", "check", "--root", "experiments", *extra, module="factory.intake")


def put_resolved(root: Path, name="q1", **over):
    data = {**VALID_RESOLVED, **over}
    data = {k: v for k, v in data.items() if v is not ...}
    d = root / "experiments" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "resolved.json").write_text(json.dumps(data))


# ---- T-03 checker ------------------------------------------------------------------------------------------

def test_T03_valid_resolved_json_is_accepted(tmp_path):
    put_resolved(tmp_path)
    p = check(tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("over,word", [
    ({"resolved_by": ""}, "resolved_by"), ({"resolved_by": "   "}, "resolved_by"), ({"resolved_by": ...}, "resolved_by"),
    ({"sources": []}, "source"), ({"sources": ...}, "source"),
    ({"as_of": ...}, "as_of"), ({"as_of": ""}, "as_of"), ({"as_of": "last week"}, "as_of"),
    ({"question": ...}, "question"), ({"question": ""}, "question"),
], ids=["by-empty", "by-blank", "by-missing", "sources-empty", "sources-missing", "date-missing", "date-empty",
        "date-bad", "question-missing", "question-empty"])
def test_T03_resolved_json_missing_a_required_part_is_rejected_with_exit_1(tmp_path, over, word):
    put_resolved(tmp_path, **over)
    p = check(tmp_path)
    out = (p.stdout + p.stderr).lower()
    assert p.returncode == 1, p.stdout + p.stderr
    assert "q1" in out, "the error names the offending experiment"
    assert word in out, f"the error names the missing part ({word}), not just 'results.json not found'"


def test_T03_unparseable_resolved_json_is_rejected(tmp_path):
    d = tmp_path / "experiments" / "q1"
    d.mkdir(parents=True)
    (d / "resolved.json").write_text("{not json")
    p = check(tmp_path)
    assert p.returncode == 1 and "resolved.json" in p.stdout + p.stderr


def test_T03_one_bad_resolved_among_good_ones_fails_the_run(tmp_path):
    put_resolved(tmp_path, "good")
    put_resolved(tmp_path, "bad", sources=[])
    p = check(tmp_path)
    assert p.returncode == 1 and "bad" in p.stdout + p.stderr and "source" in (p.stdout + p.stderr).lower()


def test_T03_check_by_id_only_looks_at_that_experiment(tmp_path):
    put_resolved(tmp_path, "good")
    put_resolved(tmp_path, "bad", sources=[])
    assert check(tmp_path, "good").returncode == 0


def test_T03_an_experiment_directory_with_neither_file_still_fails(tmp_path):
    (tmp_path / "experiments" / "empty").mkdir(parents=True)
    assert check(tmp_path).returncode == 1


def test_T03_a_valid_results_json_still_passes_next_to_resolved(tmp_path):
    d = tmp_path / "experiments" / "exp1"
    d.mkdir(parents=True)
    (d / "enum.md").write_text("Candidates as of 2026-10-01: alpha and beta.\n")
    (d / "results.json").write_text(json.dumps({
        "question": "alpha or beta?", "as_of": "2026-10-02",
        "candidates": [{"name": "alpha", "enumeration": "enum.md"}, {"name": "beta", "enumeration": "enum.md"}],
        "metrics": [{"name": "speed"}, {"name": "cost"}],
        "decision_rule_preregistered": "Pick the candidate that wins on both speed and cost.",
        "result": {"winner": "alpha", "basis": ["speed", "cost"],
                   "scores": {"alpha": {"speed": 1, "cost": 1}, "beta": {"speed": 2, "cost": 2}}}}))
    put_resolved(tmp_path)
    p = check(tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr


# ---- T-03 collector / tab ----------------------------------------------------------------------------------

def exp_files():
    return {
        "experiments/exp1/results.json": json.dumps({"question": "alpha or beta?", "result": {"winner": "alpha"}}),
        "experiments/q1/resolved.json": json.dumps(VALID_RESOLVED),
    }


def test_T03_collector_lists_both_kinds_with_kind_field(tmp_path):
    res = collect(mkrepo(tmp_path, exp_files()), "experiments")
    assert res["available"] is True
    kinds = {i["name"]: i["kind"] for i in res["items"]}
    assert kinds == {"exp1": "experiment", "q1": "resolved"}
    q1 = [i for i in res["items"] if i["name"] == "q1"][0]
    assert q1["path"] == "experiments/q1/resolved.json"
    assert "research/queues.md" in dump(q1) and "Which queue library?" in dump(q1)


def test_T03_resolved_only_makes_the_tab_available(tmp_path):
    r = mkrepo(tmp_path, {"experiments/q1/resolved.json": json.dumps(VALID_RESOLVED)})
    res = collect(r, "experiments")
    assert res["available"] is True and [i["kind"] for i in res["items"]] == ["resolved"]


def test_T03_unreadable_resolved_json_is_listed_with_an_error_not_dropped(tmp_path):
    r = mkrepo(tmp_path, {"experiments/q1/resolved.json": "{oops"})
    res = collect(r, "experiments")
    assert res["available"] is True and "error" in res["items"][0]


def test_T03_unavailable_reason_names_both_paths(tmp_path):
    res = collect(mkrepo(tmp_path), "experiments")
    assert res["available"] is False
    assert "experiments/*/results.json" in res["reason"] and "experiments/*/resolved.json" in res["reason"]


def test_T03_experiments_tab_shows_resolved_choices(tmp_path):
    r = mkrepo(tmp_path, exp_files())
    assert run(r, "bundle").returncode == 0
    text = shell_text(r, "experiments")
    assert "Which queue library?" in text and "resolved" in text.lower()


# ---- T-04 bug log ------------------------------------------------------------------------------------------

def bug(title, status=None, slice_=None, crit=None):
    lines = [f"# {title}", ""]
    if status is not None:
        lines.append(f"Status: {status}")
    if slice_:
        lines.append(f"Slice: {slice_}")
    if crit:
        lines.append(f"Criterion: {crit}")
    return "\n".join(lines) + "\n\nSome description.\n"


def bug_items(res):
    assert res["available"] is True, res
    return {i["id"]: i for i in res["items"] if "id" in i}


@pytest.mark.parametrize("status", ["open", "fixed", "wontfix"])
def test_T04_valid_statuses_are_returned_as_written(tmp_path, status):
    r = mkrepo(tmp_path, {"docs/bugs/b1.md": bug("Crash on save", status, "s1", "C-3")})
    b = bug_items(collect(r, "bug_log"))["b1"]
    assert b["title"] == "Crash on save" and b["status"] == status
    assert b["slice"] == "s1" and b["criterion"] == "C-3"
    assert b["path"] == "docs/bugs/b1.md"


@pytest.mark.parametrize("status", ["invalid", "closed", "in progress", "OPEN!!"])
def test_T04_unknown_status_is_returned_as_invalid_not_dropped(tmp_path, status):
    r = mkrepo(tmp_path, {"docs/bugs/b1.md": bug("Odd one", status), "docs/bugs/b2.md": bug("Fine", "open")})
    items = bug_items(collect(r, "bug_log"))
    assert set(items) == {"b1", "b2"}
    assert items["b1"]["status"] == "invalid"
    assert items["b2"]["status"] == "open"


def test_T04_optional_slice_and_criterion_lines_may_be_absent(tmp_path):
    b = bug_items(collect(mkrepo(tmp_path, {"docs/bugs/b1.md": bug("Lonely", "open")}), "bug_log"))["b1"]
    assert not b.get("slice") and not b.get("criterion")


def test_T04_title_is_the_first_heading(tmp_path):
    text = "Intro line\n\n# First heading\n\n## Second\n\nStatus: fixed\n"
    b = bug_items(collect(mkrepo(tmp_path, {"docs/bugs/b1.md": text}), "bug_log"))["b1"]
    assert b["title"] == "First heading" and b["status"] == "fixed"


def test_T04_legacy_jsonl_entries_are_still_returned(tmp_path):
    r = mkrepo(tmp_path, {"docs/bug-log.jsonl": json.dumps({"id": "old", "title": "Old bug", "status": "open"}) + "\n"})
    res = collect(r, "bug_log")
    assert res["available"] is True and "Old bug" in dump(res)


def qa_notes_repo(tmp_path):
    """A repo whose docs/slices/s1/qa-notes.md was produced by promote-notes from a real attempt log."""
    from .test_qa_notes import make_qa_root, promote
    root, sig = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    assert promote(root, d).returncode == 0
    from .conftest import git
    git(root, "add", "--", "docs/slices/s1/qa-notes.md")
    git(root, "commit", "-q", "-m", "notes")
    return root, sig


def test_T04_repeated_failure_entries_from_qa_notes_are_returned(tmp_path):
    root, sig = qa_notes_repo(tmp_path)
    res = collect(root, "bug_log")
    assert res["available"] is True
    hits = [i for i in res["items"] if sig in dump(i)]
    assert hits, dump(res)
    assert any("s1" in dump(i) for i in hits)


def test_T04_a_slice_with_only_qa_notes_makes_the_tab_available(tmp_path):
    root, _ = qa_notes_repo(tmp_path)
    assert not (root / "docs" / "bugs").exists()
    assert collect(root, "bug_log")["available"] is True


def test_T04_bug_tab_renders_status_and_title(tmp_path):
    r = mkrepo(tmp_path, {"docs/bugs/b1.md": bug("Crash on save", "open"), "docs/bugs/b2.md": bug("Weird", "bogus")})
    assert run(r, "bundle").returncode == 0
    text = shell_text(r, "evals")
    for want in ("Crash on save", "Weird", "invalid"):
        assert want in text, want
