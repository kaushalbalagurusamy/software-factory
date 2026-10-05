"""Tests for skills/prd-writer/scripts/check_scope.py."""
from __future__ import annotations

import importlib.util
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "prd-writer" / "scripts" / "check_scope.py"
EXAMPLE = ROOT / "skills" / "prd-writer" / "references" / "example-prd.md"

spec = importlib.util.spec_from_file_location("check_scope", SCRIPT)
cs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cs)


def make_repo(tmp_path: Path, names: list[str]) -> Path:
    for name in names:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("def handler():\n    pass\n", encoding="utf-8")
    return tmp_path


def run(tmp_path: Path, units: str) -> tuple[list[str], list[str]]:
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\n```yaml scope\n" + textwrap.dedent(units) + "```\n", encoding="utf-8")
    data = cs.load_scope(prd)
    return cs.validate(data, cs.list_files(tmp_path), tmp_path)


def matches(pattern: str, path: str) -> bool:
    return bool(cs.glob_to_regex(pattern).match(path))


def test_glob_semantics():
    assert matches("a/**", "a/b/c.py")
    assert not matches("a/**", "ab/c.py")
    assert matches("*.py", "x.py")
    assert not matches("*.py", "d/x.py")
    assert matches("**/x.py", "x.py")
    assert matches("**/x.py", "d/e/x.py")
    assert matches("docs/adr/", "docs/adr/ADR-0001.md")
    assert matches("src/?.py", "src/a.py")
    assert not matches("src/?.py", "src/ab.py")
    assert matches("./src/a.py", "src/a.py")


def test_clean_scope_passes(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py", "src/b/mod.py", "docs/notes.md"])
    errors, warnings = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/a/**"]
            reads: ["docs/**"]
            entry_points: [{path: src/a/mod.py, symbol: handler}]
          - id: U2
            owns: ["src/b/**"]
            depends_on: [U1]
    """)
    assert errors == []
    assert warnings == []


def test_overlap_on_existing_file_is_an_error(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py", "src/a/x.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/a/**"]
          - id: U2
            owns: ["src/a/x.py"]
    """)
    assert any("U1 and U2 both own" in e for e in errors)


def test_new_path_under_another_units_scope_is_an_error(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py", "src/b/mod.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/a/**", "src/b/new.py"]
            new: ["src/b/new.py"]
          - id: U2
            owns: ["src/b/**"]
    """)
    assert any("falls under U2's owns" in e for e in errors)


def test_owns_that_matches_nothing_needs_a_new_path(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/typo/**"]
    """)
    assert any("matches no files" in e for e in errors)
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/fresh/**"]
            new: ["src/fresh/mod.py"]
    """)
    assert errors == []


def test_new_path_must_be_explicit_and_covered(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/a/**"]
            new: ["src/a/*.py", "elsewhere/x.py"]
    """)
    assert any("explicit file path" in e for e in errors)
    assert any("not covered by any `owns`" in e for e in errors)


def test_too_broad_pattern(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["**"]
    """)
    assert any("too broad" in e for e in errors)


def test_dependency_cycle_and_unknown_dependency(tmp_path):
    make_repo(tmp_path, ["a/x.py", "b/x.py"])
    errors, _ = run(tmp_path, """
        units:
          - id: U1
            owns: ["a/**"]
            depends_on: [U2, U9]
          - id: U2
            owns: ["b/**"]
            depends_on: [U1]
    """)
    assert any("cycle" in e for e in errors)
    assert any("'U9' is not a unit" in e for e in errors)


def test_entry_point_checks(tmp_path):
    make_repo(tmp_path, ["src/a/mod.py", "src/b/mod.py"])
    errors, warnings = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/a/**"]
            entry_points:
              - {path: src/a/mod.py, symbol: missing_symbol}
              - {path: src/b/mod.py, symbol: handler}
              - {path: src/gone.py}
    """)
    assert any("'src/gone.py' does not exist" in e for e in errors)
    assert any("missing_symbol" in w for w in warnings)
    assert any("outside this unit's owns and reads" in w for w in warnings)


def test_possible_overlap_between_wildcard_scopes_warns(tmp_path):
    make_repo(tmp_path, ["src/api/a.py", "src/api/v2/b.py"])
    errors, warnings = run(tmp_path, """
        units:
          - id: U1
            owns: ["src/api/*.py"]
          - id: U2
            owns: ["src/api/v2/**"]
    """)
    assert errors == []
    assert any("may overlap" in w for w in warnings)


def test_missing_or_duplicate_fence_is_unreadable(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nno block here\n", encoding="utf-8")
    with pytest.raises(cs.ScopeError):
        cs.load_scope(prd)
    block = "```yaml scope\nunits: []\n```\n"
    prd.write_text(block + block, encoding="utf-8")
    with pytest.raises(cs.ScopeError):
        cs.load_scope(prd)


def test_expand_lists_concrete_files(tmp_path):
    make_repo(tmp_path, ["src/a/one.py", "src/a/two.py", "docs/n.md"])
    prd = tmp_path / "prd.md"
    prd.write_text("```yaml scope\nunits:\n  - id: U1\n    goal: g\n    owns: ['src/a/**']\n"
                   "    reads: ['docs/**']\n```\n", encoding="utf-8")
    out = cs.expand(cs.load_scope(prd), "U1", cs.list_files(tmp_path))
    assert "src/a/one.py" in out and "src/a/two.py" in out and "docs/n.md" in out


def test_diff_reports_edits_outside_scope(tmp_path):
    make_repo(tmp_path, ["a/x.py", "b/y.py"])
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)
    (tmp_path / "a" / "x.py").write_text("changed\n", encoding="utf-8")
    (tmp_path / "b" / "y.py").write_text("changed\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("stray\n", encoding="utf-8")
    data = {"units": [{"id": "U1", "owns": ["a/**"]}, {"id": "U2", "owns": ["b/**"]}]}
    stray = dict(cs.out_of_scope(data, "U1", cs.changed_files(tmp_path, "HEAD")))
    assert "a/x.py" not in stray
    assert stray["b/y.py"] == "owned by U2"
    assert stray["c.txt"] == "owned by no unit"


def test_example_prd_is_valid_for_this_repo():
    data = cs.load_scope(EXAMPLE)
    errors, _ = cs.validate(data, cs.list_files(ROOT), ROOT)
    assert errors == [], errors
