"""Unit tests for the ticket ledger (TB-11). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import pytest

from factory.ledger import LedgerError, SECTIONS, append, create_ledger, load_summary, verify

T0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


def chain(prev: str, text: str) -> str:
    return hashlib.sha256(prev.encode("utf-8") + b"\n" + text.encode("utf-8")).hexdigest()


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "ledger" / "T-1.md"
    create_ledger(p, "T-1", "Demo ticket")
    return p


def populate(p):
    append(p, "Spec", "design", "spec one", T0)
    append(p, "Research", "research", "research one\nline two", T0)
    append(p, "Implementation", "implement", "impl one", T0)
    append(p, "Spec", "design", "spec two", T0)
    return p


def edit(p, old, new, count=1):
    s = p.read_text(encoding="utf-8")
    assert old in s
    p.write_text(s.replace(old, new, count), encoding="utf-8")


def test_create_has_nine_sections_in_order(path):
    s = path.read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", s, re.M)
    assert heads == list(SECTIONS)
    assert SECTIONS == ("Spec", "Research", "Architecture", "Evals", "Implementation",
                        "Review", "Test Results", "Deploy Log", "Audit Trail")
    lines = s.split("\n")
    assert lines[0].startswith("# ") and "T-1" in lines[0] and "Demo ticket" in lines[0]
    assert lines[1] == "<!-- entries: 0; head: -->"
    assert verify(path) == []


def test_create_over_existing_raises(path):
    before = path.read_bytes()
    with pytest.raises(LedgerError):
        create_ledger(path, "T-1", "again")
    assert path.read_bytes() == before


def test_append_format_and_chain(path):
    append(path, "Research", "research", "hello", "2026-10-19T12:34:56Z")
    append(path, "Spec", "design", "world", T0)
    s = path.read_text(encoding="utf-8")
    c1 = chain("", "hello")
    c2 = chain(c1, "world")
    assert f"### 2026-10-19T12:34:56Z research\nhello\n<!-- chain: {c1}; seq: 1 -->" in s
    assert f"### 2026-10-19T12:00:00Z design\nworld\n<!-- chain: {c2}; seq: 2 -->" in s
    assert s.split("\n")[1] == f"<!-- entries: 2; head: {c2} -->"
    # Spec precedes Research in the file although it was appended second
    assert s.index("world") < s.index("hello")
    assert verify(path) == []


def test_now_forms(path):
    append(path, "Spec", "design", "a", datetime(2026, 1, 2, 5, 0, 0, tzinfo=timezone(timedelta(hours=2))))
    assert "### 2026-01-02T03:00:00Z design" in path.read_text(encoding="utf-8")
    with pytest.raises(LedgerError):
        append(path, "Spec", "design", "b", datetime(2026, 1, 2))
    with pytest.raises(LedgerError):
        append(path, "Spec", "design", "b", "2026-01-02T03:00:00")


@pytest.mark.parametrize("section,role", [
    ("Research", "research"), ("Spec", "design"), ("Architecture", "design"), ("Evals", "test"),
    ("Test Results", "test"), ("Deploy Log", "test"), ("Deploy Log", "orchestrator"),
    ("Implementation", "implement"), ("Review", "review"), ("Audit Trail", "orchestrator"),
])
def test_owner_can_write(path, section, role):
    append(path, section, role, "ok", T0)
    assert verify(path) == []


@pytest.mark.parametrize("section,role", [
    ("Research", "design"), ("Spec", "research"), ("Implementation", "test"), ("Review", "implement"),
    ("Audit Trail", "research"), ("Evals", "implement"), ("Spec", "audit"), ("Spec", "nobody"),
    ("Deploy Log", "review"),
])
def test_non_owner_rejected(path, section, role):
    before = path.read_bytes()
    with pytest.raises(LedgerError):
        append(path, section, role, "nope", T0)
    assert path.read_bytes() == before


def test_unknown_section_and_missing_file(path, tmp_path):
    with pytest.raises(LedgerError):
        append(path, "Notes", "design", "x", T0)
    with pytest.raises(LedgerError):
        append(path, "spec", "design", "x", T0)
    with pytest.raises(LedgerError):
        append(tmp_path / "none.md", "Spec", "design", "x", T0)


@pytest.mark.parametrize("bad", [
    "x\n### 2026-10-19T12:00:00Z design\ny",
    "x\n<!-- chain: abc; seq: 1 -->",
    "x\n## Research",
    "x\n<!-- entries: 5; head: -->",
])
def test_structure_forging_text_rejected(path, bad):
    with pytest.raises(LedgerError):
        append(path, "Spec", "design", bad, T0)


def test_text_with_markdown_headings_ok(path):
    append(path, "Spec", "design", "## Goals\n### sub\n- item", T0)
    append(path, "Research", "research", "after", T0)
    assert verify(path) == []


def test_trailing_newline_stripped(path):
    append(path, "Spec", "design", "body\n", T0)
    assert f"<!-- chain: {chain('', 'body')}; seq: 1 -->" in path.read_text(encoding="utf-8")
    assert verify(path) == []


def test_intact_ledger_verifies(path):
    populate(path)
    assert verify(path) == []


def test_edit_earlier_entry_detected(path):
    populate(path)
    edit(path, "spec one", "spec ONE")
    problems = verify(path)
    assert problems
    assert any("section 'Spec' entry 1" in p for p in problems)
    assert not any("entry 2" in p for p in problems)


def test_edit_in_other_section_detected(path):
    populate(path)
    edit(path, "impl one", "impl evil")
    problems = verify(path)
    assert any("section 'Implementation'" in p for p in problems)


def test_remove_middle_entry_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    block = re.search(r"### \S+ research\nresearch one\nline two\n<!-- chain: [0-9a-f]+; seq: 2 -->\n\n", s).group(0)
    path.write_text(s.replace(block, ""), encoding="utf-8")
    problems = verify(path)
    assert problems
    assert any("seq" in p for p in problems)
    assert any("section 'Implementation'" in p for p in problems)


def test_remove_last_entry_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    block = re.search(r"### \S+ design\nspec two\n<!-- chain: [0-9a-f]+; seq: 4 -->\n\n", s).group(0)
    path.write_text(s.replace(block, ""), encoding="utf-8")
    problems = verify(path)
    assert problems
    assert any("anchor" in p for p in problems)


def test_missing_chain_line_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    m = re.search(r"<!-- chain: [0-9a-f]+; seq: 1 -->\n", s)
    path.write_text(s.replace(m.group(0), ""), encoding="utf-8")
    problems = verify(path)
    assert any("section 'Spec' entry 1" in p and "chain line" in p for p in problems)


def test_swapped_entry_text_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    s = s.replace("spec one", "@@").replace("spec two", "spec one").replace("@@", "spec two")
    path.write_text(s, encoding="utf-8")
    problems = verify(path)
    assert any("section 'Spec' entry 1" in p for p in problems)
    assert any("section 'Spec' entry 2" in p for p in problems)


def test_seq_renumbered_detected(path):
    populate(path)
    edit(path, "seq: 2 -->", "seq: 3 -->")
    problems = verify(path)
    assert problems
    assert any("seq" in p for p in problems)


def test_reorder_within_file_with_seq_intact_is_not_tamper(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    m1 = re.search(r"### \S+ design\nspec one\n<!-- chain: [0-9a-f]+; seq: 1 -->\n\n", s).group(0)
    m2 = re.search(r"### \S+ design\nspec two\n<!-- chain: [0-9a-f]+; seq: 4 -->\n\n", s).group(0)
    s = s.replace(m1, "@@1").replace(m2, "@@2").replace("@@1", m2).replace("@@2", m1)
    path.write_text(s, encoding="utf-8")
    assert verify(path) == []


def test_entry_moved_to_foreign_section_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    m = re.search(r"### \S+ research\nresearch one\nline two\n<!-- chain: [0-9a-f]+; seq: 2 -->\n\n", s).group(0)
    s = s.replace(m, "")
    s = s.replace("## Architecture\n\n", "## Architecture\n\n" + m)
    path.write_text(s, encoding="utf-8")
    problems = verify(path)
    assert any("section 'Architecture'" in p and "research" in p for p in problems)


def test_role_changed_in_header_detected(path):
    populate(path)
    edit(path, " research\nresearch one", " design\nresearch one")
    assert any("section 'Research'" in p for p in verify(path))


def test_anchor_removed_or_edited_detected(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    lines = s.split("\n")
    anchor = lines[1]
    path.write_text(s.replace(anchor, "<!-- entries: 1; head: -->"), encoding="utf-8")
    assert any("anchor" in p for p in verify(path))
    path.write_text(s.replace(anchor + "\n", ""), encoding="utf-8")
    assert any("anchor" in p for p in verify(path))


def test_section_heading_tamper_detected(path):
    populate(path)
    edit(path, "## Research\n", "")
    assert verify(path)


def test_stray_line_detected(path):
    populate(path)
    edit(path, "## Review\n", "## Review\nsneaky\n")
    assert verify(path)


def test_missing_file_is_a_problem(tmp_path):
    problems = verify(tmp_path / "gone.md")
    assert problems and isinstance(problems[0], str)


def test_append_refuses_after_last_entry_removed(path):
    populate(path)
    s = path.read_text(encoding="utf-8")
    block = re.search(r"### \S+ design\nspec two\n<!-- chain: [0-9a-f]+; seq: 4 -->\n\n", s).group(0)
    path.write_text(s.replace(block, ""), encoding="utf-8")
    with pytest.raises(LedgerError):
        append(path, "Spec", "design", "laundering", T0)


def test_append_after_content_edit_keeps_tamper_visible(path):
    populate(path)
    edit(path, "spec one", "spec ONE")
    append(path, "Review", "review", "later", T0)
    assert any("section 'Spec' entry 1" in p for p in verify(path))


def test_load_summary_shape_and_latest(path):
    populate(path)
    out = load_summary(path)
    for name in SECTIONS:
        assert f"## {name}" in out
    assert "spec two" in out and "spec one" not in out
    assert "research one" in out and "impl one" in out
    assert "chain:" not in out
    assert load_summary(path) == out


def test_load_summary_empty_sections(path):
    out = load_summary(path)
    assert all(f"## {n}" in out for n in SECTIONS)
    assert len(out) <= 4000


def test_load_summary_capped_and_deterministic(path):
    for sec, role in [("Spec", "design"), ("Research", "research"), ("Implementation", "implement"),
                      ("Review", "review"), ("Evals", "test"), ("Audit Trail", "orchestrator")]:
        append(path, sec, role, "word " * 2000, T0)
    out = load_summary(path)
    assert len(out) <= 4000
    assert out == load_summary(path)
    assert all(f"## {n}" in out for n in SECTIONS)


def test_load_summary_missing_file(tmp_path):
    with pytest.raises(LedgerError):
        load_summary(tmp_path / "gone.md")


def test_unicode_text_roundtrip(path):
    append(path, "Spec", "design", "naïve café ✓", T0)
    assert verify(path) == []
