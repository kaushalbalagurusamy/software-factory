"""Fail-closed governance: a missing or crashing required verifier must block.

These tests do not need Unity. They fake the verifier being unavailable or
raising by monkeypatching the governance module's flag and function, so they run
identically with or without a Unity checkout installed.
"""

from pathlib import Path

import pytest

import factory.governance as governance
import factory.synthesis as synthesis
from factory.governance import (
    DoorType,
    GovernanceEngine,
    GovernanceReport,
    RiskCategory,
    VerifierStatus,
)
from factory.synthesis import SynthesisEngine, SynthesisRequest

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


# ---- synthesis gate -------------------------------------------------------

def _repo_with_module(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    mod = tmp_path / "src" / "mod.py"
    mod.write_text(CODE)
    return mod


def _generator(prompt: str, iteration: int) -> str:
    return f"```file:src/mod.py\n{CODE_V2}```\n"


def test_synthesis_rejects_patch_when_verifier_unavailable(tmp_path, verifier_unavailable):
    mod = _repo_with_module(tmp_path)
    res = SynthesisEngine().execute_cycle(
        SynthesisRequest(spec_text="swap", spec_path=None, repo_dir=tmp_path, max_retries=2, mock_generator=_generator)
    )
    assert res.success is False
    assert "Governance Gate Failed" in res.error_message
    assert "unavailable" in res.error_message.lower()
    assert mod.read_text() == CODE  # rolled back
    assert res.receipt is None


def test_synthesis_rejects_patch_when_verifier_crashes(tmp_path, verifier_crashes):
    mod = _repo_with_module(tmp_path)
    res = SynthesisEngine().execute_cycle(
        SynthesisRequest(spec_text="swap", spec_path=None, repo_dir=tmp_path, max_retries=2, mock_generator=_generator)
    )
    assert res.success is False
    assert "Governance Gate Failed" in res.error_message
    assert "solver exploded" in res.error_message
    assert mod.read_text() == CODE


class _StubGovernance:
    """Verifier-independent stand-in that reports a clean, verified TWO_WAY result."""

    def evaluate_delta(self, pre, post):
        return GovernanceReport(door_type=DoorType.TWO_WAY, verifier_status=VerifierStatus.OK)


def test_synthesis_accepts_patch_with_verified_governance_and_zero_trust(tmp_path):
    """ZeroTrustGate and test execution still run and a verified patch still passes."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_mod.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n"
        "from src.mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    mod = _repo_with_module(tmp_path)
    res = SynthesisEngine(governance=_StubGovernance()).execute_cycle(
        SynthesisRequest(spec_text="swap", spec_path=None, repo_dir=tmp_path, max_retries=2, mock_generator=_generator)
    )
    assert res.success is True, res.error_message
    assert mod.read_text() == CODE_V2
    assert res.zero_trust_report is not None and res.zero_trust_report.passed


def test_unity_ir_extraction_errors_are_recorded_not_swallowed(tmp_path, monkeypatch):
    _repo_with_module(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("ir lowering broke")

    monkeypatch.setattr(synthesis, "UNITY_AVAILABLE", True)
    monkeypatch.setattr(synthesis, "compile_source", boom, raising=False)
    ctx = SynthesisEngine().extract_repo_context(tmp_path)
    assert "src/mod.py" not in ctx["unity_ir"]
    assert "ir lowering broke" in ctx["unity_ir_errors"]["src/mod.py"]
