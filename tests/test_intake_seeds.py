"""Research seeds file check."""
import shutil
from pathlib import Path

import pytest

from factory.intake.cli import main

HEAD = "seed_id\ttopic\tlens\tquestion\tpriority\tdepends_on\tstatus\toutput_path\n"
GOOD_NOTE = "# Note\n\n## Sources\n- a\n\n## What I could not verify\n- b\n"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "lenses.txt").write_text("# lens names\ncryptography\nperformance\n")
    return tmp_path


def seeds(p, *rows):
    (p / "research" / "seeds.tsv").write_text(HEAD + "".join("\t".join(r) + "\n" for r in rows))


def run():
    return main(["seeds", "check"])


def row(i="S-1", lens="cryptography", prio="P1", dep="", status="open", out="", topic="t", q="what?"):
    return [i, topic, lens, q, prio, dep, status, out]


def test_valid_seeds_pass(proj):
    seeds(proj, row("S-1"), row("S-2", dep="S-1", lens="performance", prio="P0"))
    assert run() == 0


def test_unknown_lens_fails(proj, capsys):
    seeds(proj, row(lens="astrology"))
    assert run() == 1 and "astrology" in capsys.readouterr().err


def test_bad_priority_fails(proj, capsys):
    seeds(proj, row(prio="urgent"))
    assert run() == 1 and "priority" in capsys.readouterr().err


def test_dependency_cycle_fails(proj, capsys):
    seeds(proj, row("S-1", dep="S-2"), row("S-2", dep="S-1"))
    assert run() == 1 and "cycle" in capsys.readouterr().err


def test_unknown_dependency_and_duplicate_ids_fail(proj, capsys):
    seeds(proj, row("S-1", dep="S-9"), row("S-1"))
    assert run() == 1
    err = capsys.readouterr().err
    assert "S-9" in err and "duplicate" in err


def test_completed_seed_needs_existing_output(proj, capsys):
    seeds(proj, row(status="completed", out="research/s1.md"))
    assert run() == 1 and "research/s1.md" in capsys.readouterr().err
    seeds(proj, row(status="completed", out=""))
    assert run() == 1


def test_completed_seed_output_needs_sources_and_could_not_verify(proj, capsys):
    (proj / "research" / "s1.md").write_text("# Note\n\n## Sources\n- a\n")
    seeds(proj, row(status="completed", out="research/s1.md"))
    assert run() == 1 and "could not verify" in capsys.readouterr().err
    (proj / "research" / "s1.md").write_text("# Note\n\n## What I could not verify\n- b\n")
    assert run() == 1 and "Sources" in capsys.readouterr().err
    (proj / "research" / "s1.md").write_text(GOOD_NOTE)
    assert run() == 0


def test_completed_seed_with_incomplete_dependency_fails(proj, capsys):
    (proj / "research" / "s2.md").write_text(GOOD_NOTE)
    seeds(proj, row("S-1"), row("S-2", dep="S-1", status="completed", out="research/s2.md"))
    assert run() == 1 and "S-1" in capsys.readouterr().err


def test_missing_lens_list_is_an_error_not_a_pass(proj, capsys):
    (proj / "research" / "lenses.txt").unlink()
    seeds(proj, row())
    assert main(["seeds", "check", "--lenses", str(proj / "nope.txt")]) == 2


def test_default_lens_list_ships_with_the_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "seeds.tsv").write_text(HEAD + "\t".join(row(lens="cryptography")) + "\n")
    assert run() == 0
