"""TB-10: Sub-agent stop validators (R-16).

Expectations come only from docs/prds/TB-10-subagent-stop-validators.md and docs/contracts/hook-io.md / profile.md.
Audit and design fixtures are real git repositories whose report files are new (untracked), so every row and file
counts as new/changed under any reading of 'new' and 'changed' (see coverage/ambiguities-C.md).
"""
from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

from evals.agents import lib

HOOK = "factory.hooks.subagent_stop"
R = ["R-16"]


def case(cid: str, tier: str = "diagnostic", reqs=None):
    return pytest.mark.case(cid, tier=tier, tb="10", reqs=reqs or R)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=root, check=True, capture_output=True, text=True)


def project(tmp_path: Path, profile="base", new_files: dict | None = None) -> Path:
    """Committed baseline (profile + README), then `new_files` written as untracked additions."""
    root = lib.make_project(tmp_path, profile, files={"README.md": "fixture\n", "src/app.py": "X = 1\n"})
    git(root, "init", "-q")
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "initial")
    for rel, content in (new_files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


def stop(root: Path, agent_type: str, message: str | None, agent_id: str = "a1") -> dict:
    extra = {"agent_transcript_path": str(root.parent / "t.jsonl"), "stop_hook_active": False}
    if message is not None:
        extra["last_assistant_message"] = message
    return lib.payload(root, event="SubagentStop", agent_type=agent_type, agent_id=agent_id, **extra)


def decide(root: Path, agent_type: str, message: str | None, **kw):
    return lib.run_decide(HOOK, stop(root, agent_type, message, **kw), root)


# ---------------------------------------------------------------- messages

RESEARCH_OK = (
    "Batching is supported by the upstream API. The rate limit is 50 requests per minute [unverified].\n\n"
    "## Sources\n- https://docs.example.org/api/batching\n- docs/research/notes.md\n"
)
RESEARCH_NO_SOURCES = "Batching is supported by the upstream API. It has a rate limit of 50 per minute.\n"

AUDIT_OK_ROWS = (
    "| src/app.py:12 | high | Validate input before use |\n"
    "| src/db.py:40 | low | Close the cursor |\n"
)

SPEC_OK = (
    "# Login spec\n\n## Goals\n- Users sign in.\n\n## Non-goals\n- Social login.\n\n"
    "## Axioms\n- Passwords are never logged. check: tests/test_login.py::test_no_password_in_logs\n"
    "- Lockout after five failures. check: tests/test_login.py::test_lockout\n\n"
    "## Open questions\n- Session length?\n"
)


def pad_to(text: str, n: int) -> str:
    """Pad `text` with neutral filler sentences to exactly n characters."""
    filler = "Filler words for length. "
    body = text + filler * (n // len(filler) + 1)
    return body[:n]


# ---------------------------------------------------------------- golden

@case("TB10-G-001", "golden")
def test_g001_research_without_sources_blocks(tmp_path):
    """PRD b2: research's message 'must contain a heading or bold label `Sources` followed by at least one URL or
    file path ... Otherwise block.'"""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "research", RESEARCH_NO_SOURCES).kind == "block"


@case("TB10-G-002", "golden")
def test_g002_research_well_formed_allows(tmp_path):
    """Negative control. PRD b2: a Sources heading followed by a URL and a path, and the one sentence containing
    `unverified` carries `[unverified]`, under 8,000 characters -> allow."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "research", RESEARCH_OK).kind == "allow"


@case("TB10-G-003", "golden")
def test_g003_audit_row_without_severity_blocks(tmp_path):
    """PRD b3: every new row in `<audit_dir>/BUGS-MITIGATIONS.md` must have a severity cell equal to critical, high,
    medium or low; a row without one blocks."""
    lib.need(HOOK, "decide")
    rows = AUDIT_OK_ROWS + "| src/app.py:30 | Missing timeout on HTTP call |\n"
    root = project(tmp_path, new_files={"docs/audit/BUGS-MITIGATIONS.md": rows})
    assert decide(root, "audit", "Audit complete; findings recorded.").kind == "block"


@case("TB10-G-004", "golden")
def test_g004_audit_valid_rows_allow(tmp_path):
    """Negative control. PRD b3: rows with a valid severity and a `<path>:<line>` citation -> allow."""
    lib.need(HOOK, "decide")
    root = project(tmp_path, new_files={"docs/audit/BUGS-MITIGATIONS.md": AUDIT_OK_ROWS})
    assert decide(root, "audit", "Audit complete; findings recorded.").kind == "allow"


@case("TB10-G-005", "golden")
def test_g005_review_approve_with_wrong_reason_blocks(tmp_path):
    """PRD b4: 'a `wrong_reason` grade with `VERDICT: APPROVE` blocks'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Reviewed the diff.\nTB09-G-001: right_reason\nTB09-G-002: wrong_reason\n\nVERDICT: APPROVE\n"
    assert decide(root, "review", msg).kind == "block"


@case("TB10-G-006", "golden")
def test_g006_review_approve_with_grades_allows(tmp_path):
    """Negative control. PRD b4: `VERDICT: APPROVE` with at least one grade line and no wrong_reason -> allow."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Reviewed the diff.\nTB09-G-001: right_reason\nTB09-G-002: right_reason\n\nVERDICT: APPROVE\n"
    assert decide(root, "review", msg).kind == "allow"


@case("TB10-G-007", "golden")
def test_g007_review_reject_without_citation_blocks(tmp_path):
    """PRD b4: 'a REJECT must contain at least one `<path>:<line>` citation'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "The change weakens a test.\nTB09-G-001: right_reason\n\nVERDICT: REJECT\n"
    assert decide(root, "review", msg).kind == "block"


@case("TB10-G-008", "golden")
def test_g008_design_spec_missing_axioms_blocks(tmp_path):
    """PRD b5: a Markdown file changed under `paths.design_dirs` whose name contains `spec` must contain the
    headings Goals, Non-goals, Axioms, Open questions; one without Axioms blocks."""
    lib.need(HOOK, "decide")
    spec = "# Login spec\n\n## Goals\n- Users sign in.\n\n## Non-goals\n- Social login.\n\n## Open questions\n- ?\n"
    root = project(tmp_path, new_files={"docs/spec/login-spec.md": spec})
    d = decide(root, "design", "Spec written.")
    assert d.kind == "block"
    assert "Axioms" in d.reason


@case("TB10-G-009", "golden")
def test_g009_design_complete_spec_allows(tmp_path):
    """Negative control. PRD b5: all four headings present and every Axioms item has `check:` -> allow."""
    lib.need(HOOK, "decide")
    root = project(tmp_path, new_files={"docs/spec/login-spec.md": SPEC_OK})
    assert decide(root, "design", "Spec written.").kind == "allow"


@case("TB10-G-010", "golden")
def test_g010_implement_is_not_validated(tmp_path):
    """Negative control. PRD b1: '`implement`, `test`, `orchestrator` and unknown types are allowed by this hook'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "implement", "done").kind == "allow"


# ---------------------------------------------------------------- diagnostic: research (b2)

@case("TB10-D-001")
def test_d001_sources_heading_with_file_path_allows(tmp_path):
    """PRD b2: a heading `Sources` followed by a file path (no URL) is enough."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Batching is supported.\n\n### Sources\n- docs/research/batching.md\n"
    assert decide(root, "research", msg).kind == "allow"


@case("TB10-D-002")
def test_d002_bold_sources_label_with_url_allows(tmp_path):
    """PRD b2: a *bold label* `Sources` followed by a URL is accepted."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Batching is supported.\n\n**Sources**\n- https://docs.example.org/api/batching\n"
    assert decide(root, "research", msg).kind == "allow"


@case("TB10-D-003")
def test_d003_sources_heading_without_reference_blocks(tmp_path):
    """PRD b2: the Sources heading must be 'followed by at least one URL or file path'; an empty list blocks."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Batching is supported.\n\n## Sources\n- the vendor told me\n"
    assert decide(root, "research", msg).kind == "block"


@case("TB10-D-004")
def test_d004_url_only_before_sources_heading_blocks(tmp_path):
    """PRD b2: the URL or path must *follow* the Sources heading; one that only appears before it does not count."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "See https://docs.example.org/api/batching for context.\n\n## Sources\n- none recorded\n"
    assert decide(root, "research", msg).kind == "block"


@case("TB10-D-005")
def test_d005_plain_sources_word_is_not_a_label(tmp_path):
    """PRD b2: 'a heading or bold label `Sources`'; a plain sentence mentioning sources is neither."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Batching is supported; my sources were varied, e.g. https://docs.example.org/api/batching.\n"
    assert decide(root, "research", msg).kind == "block"


@case("TB10-D-006")
def test_d006_unmarked_unverified_sentence_blocks(tmp_path):
    """PRD b2: 'any sentence containing the word `unverified` must carry the marker `[unverified]`'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "The rate limit claim is unverified. Batching works.\n\n## Sources\n- https://docs.example.org/a\n"
    assert decide(root, "research", msg).kind == "block"


@case("TB10-D-007")
def test_d007_length_exactly_8000_allows(tmp_path):
    """PRD b2 boundary: 'the message must be at most 8,000 characters' - exactly 8,000 is allowed."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = pad_to(RESEARCH_OK + "\n", 8000)
    assert len(msg) == 8000
    assert decide(root, "research", msg).kind == "allow"


@case("TB10-D-008")
def test_d008_length_8001_blocks(tmp_path):
    """PRD b2 boundary: 8,001 characters exceeds the 8,000 limit -> block."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = pad_to(RESEARCH_OK + "\n", 8001)
    assert len(msg) == 8001
    assert decide(root, "research", msg).kind == "block"


@case("TB10-D-009")
def test_d009_empty_research_message_blocks(tmp_path):
    """PRD b2 (empty boundary): an empty message has no Sources -> block."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "research", "").kind == "block"


@case("TB10-D-010")
def test_d010_missing_research_message_blocks_cli(tmp_path):
    """PRD b2 + hook-io fail closed: a research stop with no `last_assistant_message` at all cannot show Sources;
    the command line answers block (exit 0, decision block)."""
    lib.need(HOOK, "decide")
    lib.need("factory.hooks.registry")
    root = project(tmp_path)
    proc = lib.run_cli("subagent_stop", stop(root, "research", None), root)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["decision"] == "block"


@case("TB10-D-011")
def test_d011_research_reason_lists_every_missing_element(tmp_path):
    """PRD b6: 'Each block reason lists every missing element' - missing Sources and an unmarked `unverified`
    sentence are both named."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    d = decide(root, "research", "The rate limit claim is unverified. Batching works.\n")
    assert d.kind == "block"
    assert "sources" in d.reason.lower() and "unverified" in d.reason.lower()


# ---------------------------------------------------------------- diagnostic: audit (b3)

def audit(tmp_path, rows: str | None, message: str = "Audit complete; findings recorded.", profile="base",
          rel: str = "docs/audit/BUGS-MITIGATIONS.md"):
    files = {rel: rows} if rows is not None else {}
    root = project(tmp_path, profile=profile, new_files=files)
    return decide(root, "audit", message)


@case("TB10-D-012")
def test_d012_severity_case_insensitive(tmp_path):
    """PRD b3: severity match is 'case-insensitive' - `HIGH` and `Medium` are valid."""
    lib.need(HOOK, "decide")
    rows = "| src/app.py:12 | HIGH | fix |\n| src/db.py:3 | Medium | fix |\n"
    assert audit(tmp_path, rows).kind == "allow"


@case("TB10-D-013")
def test_d013_all_four_severities_allowed(tmp_path):
    """PRD b3: each of `critical`, `high`, `medium`, `low` is an allowed severity."""
    lib.need(HOOK, "decide")
    rows = "".join(f"| src/m{i}.py:{i + 1} | {s} | fix |\n" for i, s in enumerate(["critical", "high", "medium", "low"]))
    assert audit(tmp_path, rows).kind == "allow"


@case("TB10-D-014")
def test_d014_unknown_severity_blocks(tmp_path):
    """PRD b3: a severity cell not equal to one of the four values (`severe`) blocks."""
    lib.need(HOOK, "decide")
    rows = AUDIT_OK_ROWS + "| src/app.py:50 | severe | fix |\n"
    assert audit(tmp_path, rows).kind == "block"


@case("TB10-D-015")
def test_d015_row_without_citation_blocks(tmp_path):
    """PRD b3: every new row needs 'a citation matching `<path>:<line>`'."""
    lib.need(HOOK, "decide")
    rows = AUDIT_OK_ROWS + "| the login module | high | fix |\n"
    assert audit(tmp_path, rows).kind == "block"


@case("TB10-D-016")
def test_d016_citation_without_line_blocks(tmp_path):
    """PRD b3: a path with no `:<line>` part is not a `<path>:<line>` citation."""
    lib.need(HOOK, "decide")
    rows = AUDIT_OK_ROWS + "| src/app.py | high | fix |\n"
    assert audit(tmp_path, rows).kind == "block"


@case("TB10-D-017")
def test_d017_missing_file_with_no_findings_allows(tmp_path):
    """PRD b3: 'A missing file is allowed only if the message says `no findings`'."""
    lib.need(HOOK, "decide")
    assert audit(tmp_path, None, message="Audit complete: no findings.").kind == "allow"


@case("TB10-D-018")
def test_d018_missing_file_without_no_findings_blocks(tmp_path):
    """PRD b3: a missing BUGS-MITIGATIONS.md without `no findings` in the message blocks."""
    lib.need(HOOK, "decide")
    assert audit(tmp_path, None, message="Audit complete.").kind == "block"


@case("TB10-D-019")
def test_d019_alt_audit_dir_is_used(tmp_path):
    """PRD b3 reads `<audit_dir>` from the profile: under alt (`notes/audit`) valid rows there allow."""
    lib.need(HOOK, "decide")
    assert audit(tmp_path, AUDIT_OK_ROWS, profile="alt", rel="notes/audit/BUGS-MITIGATIONS.md").kind == "allow"


@case("TB10-D-020")
def test_d020_alt_ignores_default_audit_dir(tmp_path):
    """PRD b3 with alt: a file at docs/audit is not `<audit_dir>` (notes/audit), so the report is missing and,
    without `no findings`, blocks."""
    lib.need(HOOK, "decide")
    assert audit(tmp_path, AUDIT_OK_ROWS, profile="alt", message="Audit complete.").kind == "block"


@case("TB10-D-021")
def test_d021_audit_reason_lists_severity_and_citation(tmp_path):
    """PRD b6: the reason lists every missing element - a row with neither severity nor citation names both."""
    lib.need(HOOK, "decide")
    d = audit(tmp_path, AUDIT_OK_ROWS + "| something is off | please fix |\n")
    assert d.kind == "block"
    assert "severity" in d.reason.lower() and "citation" in d.reason.lower()


# ---------------------------------------------------------------- diagnostic: review (b4)

@case("TB10-D-022")
def test_d022_review_without_verdict_blocks(tmp_path):
    """PRD b4: 'the message must contain `VERDICT: APPROVE` or `VERDICT: REJECT`'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "review", "Looks fine.\nTB09-G-001: right_reason\n").kind == "block"


@case("TB10-D-023")
def test_d023_reject_with_citation_and_grade_allows(tmp_path):
    """PRD b4: a REJECT with a `<path>:<line>` citation and a grade line is well formed -> allow."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Weakened assertion at tests/test_calc.py:14.\nTB09-G-001: right_reason\n\nVERDICT: REJECT\n"
    assert decide(root, "review", msg).kind == "allow"


@case("TB10-D-024")
def test_d024_approve_without_grades_blocks(tmp_path):
    """PRD b4: 'at least one grade line is required unless the message contains `no passing cases`'."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "review", "All good.\n\nVERDICT: APPROVE\n").kind == "block"


@case("TB10-D-025")
def test_d025_no_passing_cases_waives_grades(tmp_path):
    """PRD b4: with `no passing cases` in the message, no grade line is required."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "review", "There are no passing cases to grade.\n\nVERDICT: APPROVE\n").kind == "allow"


@case("TB10-D-026")
def test_d026_reject_with_wrong_reason_allowed(tmp_path):
    """PRD b4: only 'a `wrong_reason` grade with `VERDICT: APPROVE`' blocks; with REJECT (cited) it is allowed."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Shortcut found at src/app.py:7.\nTB09-G-001: wrong_reason\n\nVERDICT: REJECT\n"
    assert decide(root, "review", msg).kind == "allow"


@case("TB10-D-027")
def test_d027_reject_without_grades_blocks(tmp_path):
    """PRD b4: the grade-line requirement applies to REJECT too (cited REJECT, no grade, no `no passing cases`)."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, "review", "Bug at src/app.py:7.\n\nVERDICT: REJECT\n").kind == "block"


@case("TB10-D-028")
def test_d028_review_reason_lists_verdict_and_grade(tmp_path):
    """PRD b6: a message missing both the verdict and grade lines gets a reason naming both."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    d = decide(root, "review", "I looked at it.\n")
    assert d.kind == "block"
    assert "verdict" in d.reason.lower() and "grade" in d.reason.lower()


@case("TB10-D-029")
def test_d029_inconclusive_grade_counts_as_grade_line(tmp_path):
    """PRD b4: 'every line of the form `<id>: right_reason`, `wrong_reason` or `inconclusive` is a grade'; a cited
    REJECT whose only grade is inconclusive satisfies the grade-line requirement."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    msg = "Flaky at tests/test_calc.py:3.\nTB09-D-001: inconclusive\n\nVERDICT: REJECT\n"
    assert decide(root, "review", msg).kind == "allow"


# ---------------------------------------------------------------- diagnostic: design (b5)

def design(tmp_path, files: dict, profile="base"):
    root = project(tmp_path, profile=profile, new_files=files)
    return decide(root, "design", "Design written.")


@case("TB10-D-030")
def test_d030_spec_missing_two_headings_names_both(tmp_path):
    """PRD b5 + b6: a spec missing `Non-goals` and `Open questions` blocks, and the reason names both."""
    lib.need(HOOK, "decide")
    spec = "# Spec\n\n## Goals\n- a\n\n## Axioms\n- x. check: tests/test_x.py::test_x\n"
    d = design(tmp_path, {"docs/spec/pay-spec.md": spec})
    assert d.kind == "block"
    assert "non-goals" in d.reason.lower() and "open questions" in d.reason.lower()


@case("TB10-D-031")
def test_d031_non_goals_heading_does_not_satisfy_goals(tmp_path):
    """PRD b5: the heading `Goals` is required; a `Non-goals` heading is a different heading."""
    lib.need(HOOK, "decide")
    spec = SPEC_OK.replace("## Goals\n- Users sign in.\n\n", "")
    assert design(tmp_path, {"docs/spec/login-spec.md": spec}).kind == "block"


@case("TB10-D-032")
def test_d032_axiom_without_check_blocks(tmp_path):
    """PRD b5: 'every list item under `Axioms` must contain `check:`'; one item without it blocks."""
    lib.need(HOOK, "decide")
    spec = SPEC_OK.replace("- Lockout after five failures. check: tests/test_login.py::test_lockout",
                           "- Lockout after five failures.")
    assert design(tmp_path, {"docs/spec/login-spec.md": spec}).kind == "block"


@case("TB10-D-033")
def test_d033_one_way_door_without_adr_blocks(tmp_path):
    """PRD b5: 'if any design document contains `one-way door: yes`, an ADR file under `docs/adr` must exist'."""
    lib.need(HOOK, "decide")
    spec = SPEC_OK + "\none-way door: yes\n"
    assert design(tmp_path, {"docs/spec/login-spec.md": spec}).kind == "block"


@case("TB10-D-034")
def test_d034_one_way_door_with_adr_allows(tmp_path):
    """PRD b5: with `one-way door: yes` and an ADR file under docs/adr, the spec is allowed."""
    lib.need(HOOK, "decide")
    spec = SPEC_OK + "\none-way door: yes\n"
    files = {"docs/spec/login-spec.md": spec, "docs/adr/ADR-0007-session-store.md": "# ADR-0007\nDecision: x\n"}
    assert design(tmp_path, files).kind == "allow"


@case("TB10-D-035")
def test_d035_non_spec_named_file_not_checked(tmp_path):
    """PRD b5 applies to files 'whose name contains `spec`'; an incomplete docs/prd/overview.md is not checked."""
    lib.need(HOOK, "decide")
    assert design(tmp_path, {"docs/prd/overview.md": "# Overview\nJust notes.\n"}).kind == "allow"


@case("TB10-D-036")
def test_d036_spec_outside_design_dirs_not_checked(tmp_path):
    """PRD b5 applies to files 'under `paths.design_dirs`'; an incomplete src/spec.md is not checked."""
    lib.need(HOOK, "decide")
    assert design(tmp_path, {"src/spec.md": "# Spec\nnothing\n"}).kind == "allow"


@case("TB10-D-037")
def test_d037_alt_design_dir_is_checked(tmp_path):
    """PRD b5 reads `paths.design_dirs` from the profile: under alt (`design/prd`, `design/adr`) an incomplete
    design/prd/checkout-spec.md blocks."""
    lib.need(HOOK, "decide")
    assert design(tmp_path, {"design/prd/checkout-spec.md": "# Checkout spec\n## Goals\n- a\n"},
                  profile="alt").kind == "block"


@case("TB10-D-038")
def test_d038_alt_ignores_default_design_dir(tmp_path):
    """PRD b5 with alt: docs/spec is not a design dir, so an incomplete docs/spec/checkout-spec.md is not checked."""
    lib.need(HOOK, "decide")
    assert design(tmp_path, {"docs/spec/checkout-spec.md": "# Checkout spec\n## Goals\n- a\n"},
                  profile="alt").kind == "allow"


# ---------------------------------------------------------------- diagnostic: b1 routing, b7 no network, adapter

@pytest.mark.parametrize("agent_type", [
    pytest.param(t, marks=case(f"TB10-D-{i:03d}"), id=t)
    for i, t in enumerate(["test", "orchestrator", "mystery-agent"], start=39)])
def test_d_unvalidated_types_allowed(tmp_path, agent_type):
    """PRD b1: `test`, `orchestrator` and unknown agent types are allowed by this hook, whatever the message."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    assert decide(root, agent_type, "").kind == "allow"


@case("TB10-D-042")
def test_d042_no_network(tmp_path, monkeypatch):
    """PRD b7: 'Validators read only the message and files under the project root; no network.' With sockets
    patched to fail, research and review validation still decide, and no connection is attempted."""
    lib.need(HOOK, "decide")
    root = project(tmp_path)
    attempts = []

    def deny(*a, **k):
        attempts.append(a)
        raise OSError("network disabled in eval")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    assert decide(root, "research", RESEARCH_OK).kind == "allow"
    assert decide(root, "research", RESEARCH_NO_SOURCES).kind == "block"
    assert attempts == []


@case("TB10-D-043")
def test_d043_cli_block_shape(tmp_path):
    """hook-io adapter for SubagentStop: block is exit 0 with stdout {"decision":"block","reason":...}; allow is
    exit 0 with empty stdout."""
    lib.need(HOOK, "decide")
    lib.need("factory.hooks.registry")
    root = project(tmp_path)
    blocked = lib.run_cli("subagent_stop", stop(root, "research", RESEARCH_NO_SOURCES), root)
    assert blocked.returncode == 0
    data = json.loads(blocked.stdout)
    assert data["decision"] == "block" and data["reason"]
    allowed = lib.run_cli("subagent_stop", stop(root, "research", RESEARCH_OK), root)
    assert allowed.returncode == 0 and allowed.stdout.strip() == ""
