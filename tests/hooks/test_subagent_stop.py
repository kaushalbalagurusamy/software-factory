"""Unit tests for the SubagentStop validators (TB-10). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import registry, subagent_stop
from factory.hooks.core import Decision, HookConfig, parse_payload, run_hook
from factory.hooks.subagent_stop import decide

HAS_GIT = shutil.which("git") is not None


def cfg_for(root: Path, **paths) -> HookConfig:
    p = {"eval": ["evals/**"]}
    p.update(paths)
    prof = parse_profile({"schema_version": 1, "project": {"name": "demo"}, "paths": p})
    return HookConfig.from_profile(prof, root)


def payload(agent_type, message="", event="SubagentStop", **extra):
    d = {"session_id": "s", "cwd": "/x", "hook_event_name": event, "permission_mode": "default",
         "agent_id": "a1", "agent_type": agent_type, "agent_transcript_path": "/t",
         "last_assistant_message": message, "stop_hook_active": False}
    d.update(extra)
    return parse_payload(json.dumps(d))


def run(root, agent_type, message="", **paths):
    return decide(payload(agent_type, message), cfg_for(root, **paths))


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def init_repo(root: Path):
    git(root, "init", "-q")
    (root / "README.md").write_text("x\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "init")


# ---------------------------------------------------------------- dispatch
@pytest.mark.parametrize("agent", ["implement", "test", "orchestrator", "mystery", None])
def test_other_agents_allowed(tmp_path, agent):
    assert run(tmp_path, agent, "anything").kind == "allow"


def test_registry_resolves_module():
    assert registry.get_hook("subagent_stop").implemented


def test_other_event_allowed(tmp_path):
    p = payload("research", "no sources", event="Stop")
    assert decide(p, cfg_for(tmp_path)).kind == "allow"


@pytest.mark.parametrize("agent", ["research", "review"])
def test_missing_message_blocks(tmp_path, agent):
    p = parse_payload(json.dumps({"hook_event_name": "SubagentStop", "agent_type": agent}))
    d = decide(p, cfg_for(tmp_path))
    assert d.kind == "block" and "last_assistant_message" in d.reason


# ---------------------------------------------------------------- research
GOOD_RESEARCH = "Findings: x.\n\n## Sources\n- https://example.com/a\n"


def test_research_ok_heading(tmp_path):
    assert run(tmp_path, "research", GOOD_RESEARCH).kind == "allow"


@pytest.mark.parametrize("label", ["**Sources**", "**Sources:**", "## Sources", "# Sources", "### Sources:"])
def test_research_label_forms(tmp_path, label):
    assert run(tmp_path, "research", f"Body.\n\n{label}\n- docs/notes.md\n").kind == "allow"


def test_research_inline_label_with_url(tmp_path):
    assert run(tmp_path, "research", "Body.\n**Sources:** https://example.com/x").kind == "allow"


def test_research_file_path_source(tmp_path):
    assert run(tmp_path, "research", "Body.\n\n## Sources\n- research/notes/a.md\n").kind == "allow"


def test_research_plain_label_line(tmp_path):
    msg = "Batching is supported.\n\nSources\n- https://docs.example.org/api/batching\n"
    assert run(tmp_path, "research", msg).kind == "allow"


def test_research_plain_label_url_must_follow(tmp_path):
    assert run(tmp_path, "research", "See https://e.com/a.\n\nSources\nnothing\n").kind == "block"


def test_research_sources_inside_sentence_is_not_label(tmp_path):
    msg = "The sources of the bug are unclear.\nSources are listed in https://e.com/a\n"
    assert run(tmp_path, "research", msg).kind == "block"


def test_research_prose_slash_is_not_a_path(tmp_path):
    assert run(tmp_path, "research", "Body.\n\n## Sources\nand/or yes/no\n").kind == "block"


def test_research_bare_filename_source(tmp_path):
    assert run(tmp_path, "research", "Body.\n\n## Sources\n- notes.md\n").kind == "allow"


def test_research_missing_sources_label(tmp_path):
    d = run(tmp_path, "research", "Body only https://example.com/a")
    assert d.kind == "block" and "Sources" in d.reason


def test_research_label_without_source(tmp_path):
    d = run(tmp_path, "research", "Body.\n\n## Sources\nnone really, e.g. i.e.\n")
    assert d.kind == "block" and "URL or file path" in d.reason


def test_research_source_before_label_does_not_count(tmp_path):
    d = run(tmp_path, "research", "See https://example.com/a first.\n\n## Sources\nnothing\n")
    assert d.kind == "block"


def test_research_word_sources_in_prose_is_not_label(tmp_path):
    d = run(tmp_path, "research", "I read many Sources today: https://example.com/a")
    assert d.kind == "block"


def test_research_unverified_needs_marker(tmp_path):
    msg = "The API is unverified here.\n\n## Sources\n- https://e.com/a\n"
    d = run(tmp_path, "research", msg)
    assert d.kind == "block" and "[unverified]" in d.reason


def test_research_unverified_case_insensitive(tmp_path):
    msg = "This is UNVERIFIED.\n\n## Sources\n- https://e.com/a\n"
    assert run(tmp_path, "research", msg).kind == "block"


def test_research_unverified_with_marker_ok(tmp_path):
    msg = "The API is unverified [unverified]. Other claim stands.\n\n## Sources\n- https://e.com/a\n"
    assert run(tmp_path, "research", msg).kind == "allow"


def test_research_marker_must_be_in_same_sentence(tmp_path):
    msg = "[unverified] first. The second is unverified too.\n\n## Sources\n- https://e.com/a\n"
    assert run(tmp_path, "research", msg).kind == "block"


def test_research_marker_alone_ok(tmp_path):
    msg = "Claim one [unverified]\nClaim two [unverified]\n\n## Sources\n- https://e.com/a\n"
    assert run(tmp_path, "research", msg).kind == "allow"


def test_research_length_limit(tmp_path):
    body = "x" * (8000 - len(GOOD_RESEARCH))
    ok = body + GOOD_RESEARCH
    assert len(ok) == 8000 and run(tmp_path, "research", ok).kind == "allow"
    d = run(tmp_path, "research", "y" + ok)
    assert d.kind == "block" and "8000" in d.reason


def test_research_lists_every_problem(tmp_path):
    d = run(tmp_path, "research", "unverified " + "z" * 8100)
    assert d.kind == "block"
    for needle in ("Sources", "[unverified]", "8000"):
        assert needle in d.reason


# ---------------------------------------------------------------- audit
def write_audit(root, text, audit_dir="docs/audit"):
    f = root / audit_dir / "BUGS-MITIGATIONS.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return f


HEADER = "| id | severity | where | note |\n|---|---|---|---|\n"


def test_audit_good_rows(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | High | src/a.py:12 | x |\n| 2 | low | b/c.py:3 | y |\n")
    assert run(tmp_path, "audit", "done").kind == "allow"


def test_audit_missing_file_blocks(tmp_path):
    d = run(tmp_path, "audit", "all done")
    assert d.kind == "block" and "BUGS-MITIGATIONS.md" in d.reason


@pytest.mark.parametrize("msg", ["no findings", "There are No Findings."])
def test_audit_missing_file_with_no_findings(tmp_path, msg):
    assert run(tmp_path, "audit", msg).kind == "allow"


def test_audit_missing_severity(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | urgent | src/a.py:12 | x |\n")
    d = run(tmp_path, "audit", "x")
    assert d.kind == "block" and "severity" in d.reason


def test_audit_missing_citation(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | high | src/a.py | x |\n")
    d = run(tmp_path, "audit", "x")
    assert d.kind == "block" and "citation" in d.reason


def test_audit_reports_every_bad_row(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | big | a.py:1 | x |\n| 2 | high | nothing | x |\n| 3 | low | q.py:9 | x |\n")
    d = run(tmp_path, "audit", "x")
    assert d.kind == "block" and "row 3" in d.reason and "row 4" in d.reason and "row 5" not in d.reason
    assert "severity" in d.reason and "citation" in d.reason


def test_audit_header_and_separator_excluded(tmp_path):
    write_audit(tmp_path, HEADER)
    assert run(tmp_path, "audit", "x").kind == "allow"


def test_audit_url_is_not_a_citation(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | high | http://host:80 | x |\n")
    assert run(tmp_path, "audit", "x").kind == "block"


def test_audit_custom_dir(tmp_path):
    write_audit(tmp_path, HEADER + "| 1 | low | a.py:1 | x |\n", audit_dir="audits")
    assert run(tmp_path, "audit", "x", audit_dir="audits").kind == "allow"
    assert run(tmp_path, "audit", "x").kind == "block"  # default dir has no file


def test_audit_non_table_lines_ignored(tmp_path):
    write_audit(tmp_path, "# Bugs\n\nprose | with pipe\n" + HEADER + "| 1 | low | a.py:1 | x |\n")
    assert run(tmp_path, "audit", "x").kind == "allow"


@pytest.mark.skipif(not HAS_GIT, reason="git unavailable")
def test_audit_only_new_rows_checked(tmp_path):
    init_repo(tmp_path)
    write_audit(tmp_path, HEADER + "| 1 | bogus | nowhere | old |\n")
    git(tmp_path, "add", "docs/audit/BUGS-MITIGATIONS.md")
    git(tmp_path, "commit", "-q", "-m", "audit")
    assert run(tmp_path, "audit", "x").kind == "allow"  # old bad row is not new
    write_audit(tmp_path, HEADER + "| 1 | bogus | nowhere | old |\n| 2 | high | a.py:2 | new |\n")
    assert run(tmp_path, "audit", "x").kind == "allow"
    write_audit(tmp_path, HEADER + "| 1 | bogus | nowhere | old |\n| 2 | huge | a.py:2 | new |\n")
    d = run(tmp_path, "audit", "x")
    assert d.kind == "block" and "row 4" in d.reason and "row 3" not in d.reason


@pytest.mark.skipif(not HAS_GIT, reason="git unavailable")
def test_audit_untracked_file_all_rows_new(tmp_path):
    init_repo(tmp_path)
    write_audit(tmp_path, HEADER + "| 1 | bogus | nowhere | x |\n")
    assert run(tmp_path, "audit", "x").kind == "block"


# ---------------------------------------------------------------- review
REV = "Notes.\nVERDICT: APPROVE\nc1: right_reason\nc2: right_reason\n"


def test_review_approve_ok(tmp_path):
    assert run(tmp_path, "review", REV).kind == "allow"


def test_review_no_verdict(tmp_path):
    d = run(tmp_path, "review", "c1: right_reason")
    assert d.kind == "block" and "VERDICT" in d.reason


def test_review_both_verdicts(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\nVERDICT: REJECT\nsrc/a.py:3\nc1: right_reason")
    assert d.kind == "block" and "both" in d.reason.lower()


def test_review_reject_needs_citation(tmp_path):
    d = run(tmp_path, "review", "VERDICT: REJECT\nc1: wrong_reason\n")
    assert d.kind == "block" and "citation" in d.reason


def test_review_reject_with_citation_ok(tmp_path):
    assert run(tmp_path, "review", "VERDICT: REJECT\nsee src/a.py:10\nc1: wrong_reason\n").kind == "allow"


def test_review_approve_citation_not_required(tmp_path):
    assert run(tmp_path, "review", REV).kind == "allow"


def test_review_needs_grade(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\n")
    assert d.kind == "block" and "grade" in d.reason


def test_review_no_passing_cases_waives_grade(tmp_path):
    assert run(tmp_path, "review", "VERDICT: APPROVE\nThere were no passing cases.").kind == "allow"


def test_review_wrong_reason_with_approve_blocks(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\nc1: right_reason\nc2: wrong_reason\n")
    assert d.kind == "block" and "c2" in d.reason and "c1" not in d.reason


def test_review_inconclusive_with_approve_blocks(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\nc1: inconclusive\n")
    assert d.kind == "block" and "c1" in d.reason


def test_review_grade_forms(tmp_path):
    msg = "VERDICT: REJECT\na.py:1\n- t/test_x.py::test_a: wrong_reason\n* case 7: inconclusive\n"
    assert run(tmp_path, "review", msg).kind == "allow"


def test_review_grade_must_be_a_line(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\nI think c1: right_reason is fine so far\n")
    assert d.kind == "block" and "grade" in d.reason


def test_review_unknown_grade_word_not_a_grade(tmp_path):
    d = run(tmp_path, "review", "VERDICT: APPROVE\nc1: fine\n")
    assert d.kind == "block"


def test_review_reports_all_missing(tmp_path):
    d = run(tmp_path, "review", "VERDICT: REJECT\n")
    assert "citation" in d.reason and "grade" in d.reason


# ---------------------------------------------------------------- design
GOOD_SPEC = ("# Spec\n\n## Goals\n- g\n\n## Non-goals\n- n\n\n## Axioms\n"
             "- A1: x. check: pytest -k a\n- A2: y\n  check: test b\n\n## Open questions\n- q\n")


def write(root, rel, text):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def test_design_good_spec(tmp_path):
    write(tmp_path, "docs/spec/feature-spec.md", GOOD_SPEC)
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_no_design_files_allowed(tmp_path):
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_non_spec_name_not_checked(tmp_path):
    write(tmp_path, "docs/spec/notes.md", "nothing here\n")
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_non_markdown_not_checked(tmp_path):
    write(tmp_path, "docs/spec/my-spec.txt", "nothing here\n")
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_outside_design_dirs_not_checked(tmp_path):
    write(tmp_path, "other/my-spec.md", "nothing here\n")
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_missing_headings_each_named(tmp_path):
    write(tmp_path, "docs/prd/spec.md", "# S\n\n## Goals\n- g\n")
    d = run(tmp_path, "design", "done")
    assert d.kind == "block"
    for h in ("Non-goals", "Axioms", "Open questions"):
        assert h in d.reason
    assert "docs/prd/spec.md" in d.reason


def test_design_axiom_without_check(tmp_path):
    write(tmp_path, "docs/spec/a-spec.md", GOOD_SPEC.replace("- A2: y\n  check: test b", "- A2: y"))
    d = run(tmp_path, "design", "done")
    assert d.kind == "block" and "check:" in d.reason and "A2" in d.reason


def test_design_axiom_scope_ends_at_next_heading(tmp_path):
    write(tmp_path, "docs/spec/a-spec.md", GOOD_SPEC.replace("- q", "- a question without the marker"))
    assert run(tmp_path, "design", "done").kind == "allow"


def test_design_numbered_axioms(tmp_path):
    write(tmp_path, "docs/spec/a-spec.md", GOOD_SPEC.replace("- A1: x. check: pytest -k a", "1. A1: x"))
    assert run(tmp_path, "design", "done").kind == "block"


def test_design_custom_dirs(tmp_path):
    write(tmp_path, "plans/s-spec.md", "bare\n")
    assert run(tmp_path, "design", "d", design_dirs=["plans"]).kind == "block"
    assert run(tmp_path, "design", "d").kind == "allow"


def test_design_one_way_door_needs_adr(tmp_path):
    write(tmp_path, "docs/spec/a-spec.md", GOOD_SPEC + "\none-way door: yes\n")
    d = run(tmp_path, "design", "d")
    assert d.kind == "block" and "ADR" in d.reason
    write(tmp_path, "docs/adr/0001-choice.md", "# ADR\n")
    assert run(tmp_path, "design", "d").kind == "allow"


def test_design_one_way_door_in_any_design_doc(tmp_path):
    write(tmp_path, "docs/prd/plain.md", "x\none-way door: yes\n")
    assert run(tmp_path, "design", "d").kind == "block"


def test_design_one_way_door_no_is_fine(tmp_path):
    write(tmp_path, "docs/prd/plain.md", "one-way door: no\n")
    assert run(tmp_path, "design", "d").kind == "allow"


def test_design_adr_dir_from_design_dirs_last_segment(tmp_path):
    write(tmp_path, "plans/p.md", "one-way door: yes\n")
    assert run(tmp_path, "design", "d", design_dirs=["plans", "records/adr"]).kind == "block"
    write(tmp_path, "records/adr/0001.md", "# ADR\n")
    assert run(tmp_path, "design", "d", design_dirs=["plans", "records/adr"]).kind == "allow"


def test_design_adr_dir_literal_docs_adr_even_if_not_design_dir(tmp_path):
    write(tmp_path, "plans/p.md", "one-way door: yes\n")
    write(tmp_path, "docs/adr/0001.md", "# ADR\n")
    assert run(tmp_path, "design", "d", design_dirs=["plans"]).kind == "allow"


def test_design_empty_adr_dir_is_not_an_adr(tmp_path):
    write(tmp_path, "docs/prd/p.md", "one-way door: yes\n")
    (tmp_path / "docs/adr").mkdir(parents=True)
    assert run(tmp_path, "design", "d").kind == "block"


@pytest.mark.skipif(not HAS_GIT, reason="git unavailable")
def test_design_only_changed_files_checked(tmp_path):
    init_repo(tmp_path)
    write(tmp_path, "docs/spec/old-spec.md", "bare\n")
    git(tmp_path, "add", "docs/spec/old-spec.md")
    git(tmp_path, "commit", "-q", "-m", "old")
    assert run(tmp_path, "design", "d").kind == "allow"
    write(tmp_path, "docs/spec/old-spec.md", "still bare, edited\n")
    assert run(tmp_path, "design", "d").kind == "block"


@pytest.mark.skipif(not HAS_GIT, reason="git unavailable")
def test_design_untracked_spec_checked(tmp_path):
    init_repo(tmp_path)
    write(tmp_path, "docs/spec/new-spec.md", "bare\n")
    assert run(tmp_path, "design", "d").kind == "block"


# ---------------------------------------------------------------- protocol
def test_run_hook_block_json(tmp_path):
    stdin = json.dumps({"hook_event_name": "SubagentStop", "agent_type": "research",
                        "last_assistant_message": "nothing"})
    r = run_hook(decide, stdin, cfg_for(tmp_path))
    out = json.loads(r.stdout)
    assert r.exit_code == 0 and out["decision"] == "block" and "Sources" in out["reason"]


def test_run_hook_allow(tmp_path):
    stdin = json.dumps({"hook_event_name": "SubagentStop", "agent_type": "implement"})
    r = run_hook(decide, stdin, cfg_for(tmp_path))
    assert (r.exit_code, r.stdout, r.stderr) == (0, "", "")


def test_run_hook_malformed_fails_closed(tmp_path):
    r = run_hook(decide, "not json", cfg_for(tmp_path))
    assert "hook error:" in r.stdout or "hook error:" in r.stderr


def test_non_string_message_blocks(tmp_path):
    stdin = json.dumps({"hook_event_name": "SubagentStop", "agent_type": "review",
                        "last_assistant_message": 5})
    r = run_hook(decide, stdin, cfg_for(tmp_path))
    assert json.loads(r.stdout)["decision"] == "block"


def test_decision_type():
    assert isinstance(subagent_stop.decide(payload("test"), cfg_for(Path("."))), Decision)
