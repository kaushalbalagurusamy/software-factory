"""
The governance gate must not pass a Python or Go change it could not analyze.
A missing Unity/z3 install and an exception during lowering both fail closed.
"""

from pathlib import Path

import pytest

import factory.governance as gov
from factory.governance import DoorType, GateUnavailableError, GovernanceEngine, RiskCategory


def _py_pair(tmp_path: Path):
    pre = tmp_path / "pre.py"
    post = tmp_path / "post.py"
    pre.write_text("def f():\n    return 1\n")
    post.write_text("def f():\n    return 2\n")
    return pre, post


def test_missing_unity_raises_for_python(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gov, "UNITY_AVAILABLE", False)
    monkeypatch.setattr(gov, "UNITY_IMPORT_ERROR", "No module named 'z3'")
    pre, post = _py_pair(tmp_path)

    with pytest.raises(GateUnavailableError, match="No module named 'z3'"):
        GovernanceEngine().audit_source_pair(pre, post)


def test_missing_unity_still_scans_sql(monkeypatch, tmp_path: Path):
    """Unity does not read SQL, so the text scan is the whole gate for it and stays available."""
    monkeypatch.setattr(gov, "UNITY_AVAILABLE", False)
    pre = tmp_path / "v1.sql"
    post = tmp_path / "v2.sql"
    pre.write_text("CREATE TABLE a (id INT);")
    post.write_text("DROP TABLE a;")

    report = GovernanceEngine().audit_source_pair(pre, post)

    assert report.door_type == DoorType.ONE_WAY
    assert any(r.category == RiskCategory.SCHEMA_MUTATION for r in report.risks)


def test_lowering_exception_is_one_way_not_two_way(monkeypatch, tmp_path: Path):
    def boom(*_args, **_kwargs):
        raise RuntimeError("tree-sitter blew up")

    monkeypatch.setattr(gov, "compute_semantic_delta", boom)
    pre, post = _py_pair(tmp_path)

    report = GovernanceEngine().audit_source_pair(pre, post)

    assert report.door_type == DoorType.ONE_WAY
    unanalyzed = [r for r in report.risks if r.category == RiskCategory.UNANALYZABLE]
    assert len(unanalyzed) == 1
    assert "tree-sitter blew up" in unanalyzed[0].description
    assert not any(r.category == RiskCategory.LOCAL_REFACTOR for r in report.risks)
