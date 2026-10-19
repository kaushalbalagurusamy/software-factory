"""Fail-closed governance: a missing or crashing required verifier must block.

These tests do not need Unity. They fake the verifier being unavailable or
raising by monkeypatching the governance module's flag and function, so they run
identically with or without a Unity checkout installed.
"""

from pathlib import Path

import pytest

import factory.governance as governance
from factory.governance import (
    DoorType,
    GovernanceEngine,
    GovernanceReport,
    RiskCategory,
    VerifierStatus,
)

CODE = "def add(a, b):\n    return a + b\n"
CODE_V2 = "def add(a, b):\n    return b + a\n"


@pytest.fixture
def py_pair(tmp_path: Path):
    pre = tmp_path / "pre.py"
    post = tmp_path / "post.py"
    pre.write_text(CODE)
    post.write_text(CODE_V2)
    return pre, post


@pytest.fixture
def sql_pair(tmp_path: Path):
    pre = tmp_path / "v1.sql"
    post = tmp_path / "v2.sql"
    pre.write_text("CREATE TABLE t (id INT);")
    post.write_text("DROP TABLE accounts CASCADE;")
    return pre, post


@pytest.fixture
def verifier_unavailable(monkeypatch):
    monkeypatch.setattr(governance, "UNITY_AVAILABLE", False)


@pytest.fixture
def verifier_crashes(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(governance, "UNITY_AVAILABLE", True)
    monkeypatch.setattr(governance, "compute_semantic_delta", boom, raising=False)


def _no_harmless_classification(report: GovernanceReport) -> None:
    assert not any(
        r.door_type == DoorType.TWO_WAY and r.category == RiskCategory.LOCAL_REFACTOR and not r.requires_adr
        for r in report.risks
    )


# ---- engine ---------------------------------------------------------------

def test_missing_verifier_fails_gate(py_pair, verifier_unavailable):
    report = GovernanceEngine().audit_source_pair(*py_pair)
    assert report.verifier_status == VerifierStatus.UNAVAILABLE
    assert report.gate_failed is True
    assert "unity" in report.verifier_reason.lower()
    _no_harmless_classification(report)
    assert "GATE FAILED" in report.summary()


def test_crashing_verifier_fails_gate_with_reason(py_pair, verifier_crashes):
    report = GovernanceEngine().audit_source_pair(*py_pair)
    assert report.verifier_status == VerifierStatus.ERROR
    assert report.gate_failed is True
    assert "solver exploded" in report.verifier_reason
    _no_harmless_classification(report)
    assert "GATE FAILED" in report.summary()


def test_gate_failure_is_never_reported_as_safe(py_pair, verifier_unavailable):
    report = GovernanceEngine().audit_source_pair(*py_pair)
    assert report.autonomous_execution_permitted is False
    assert report.adr_draft is None or "verifier" in report.adr_draft.lower()


def test_non_code_artifact_is_pattern_scanned_not_gate_failed(sql_pair, verifier_unavailable):
    report = GovernanceEngine().audit_source_pair(*sql_pair)
    assert report.gate_failed is False
    assert report.verifier_status == VerifierStatus.NOT_APPLICABLE
    assert report.door_type == DoorType.ONE_WAY
    assert "pattern" in report.summary().lower()


def test_explicit_pattern_only_is_labelled_unverified(py_pair, verifier_unavailable):
    report = GovernanceEngine().audit_source_pair(*py_pair, pattern_only=True)
    assert report.verifier_status == VerifierStatus.UNVERIFIED
    assert report.gate_failed is False
    assert report.autonomous_execution_permitted is False
    text = report.summary()
    assert "UNVERIFIED" in text
    assert "not semantic proof" in text.lower()


def test_pattern_only_does_not_invoke_verifier(py_pair, monkeypatch):
    def must_not_run(*_a, **_k):
        raise AssertionError("verifier must not run in pattern-only mode")

    monkeypatch.setattr(governance, "UNITY_AVAILABLE", True)
    monkeypatch.setattr(governance, "compute_semantic_delta", must_not_run, raising=False)
    report = GovernanceEngine().audit_source_pair(*py_pair, pattern_only=True)
    assert report.verifier_status == VerifierStatus.UNVERIFIED
