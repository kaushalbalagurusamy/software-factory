"""
Tests for Software Factory Invariant Governance Engine.
Verifies One-Way vs. Two-Way Door classifications backed by Unity-IR and SMT solvers.
"""

from pathlib import Path
import pytest
from factory.governance import GovernanceEngine, DoorType, RiskCategory

# Paths to Unity golden examples
UNITY_EXAMPLES_DIR = Path("/Users/kaushal/Documents/Github/unity/examples/ledger")
LEDGER_PY = UNITY_EXAMPLES_DIR / "ledger.py"


@pytest.fixture
def governance_engine() -> GovernanceEngine:
    return GovernanceEngine()


def test_identical_source_is_two_way_door(governance_engine: GovernanceEngine):
    """Auditing identical files should report a Two-Way Door with zero risks."""
    report = governance_engine.audit_source_pair(LEDGER_PY, LEDGER_PY)
    assert report.door_type == DoorType.TWO_WAY
    assert not report.is_one_way_door
    if report.semantic_delta:
        assert report.semantic_delta.is_identical


def test_concurrency_lock_removal_is_one_way_door(governance_engine: GovernanceEngine, tmp_path: Path):
    """Removing threading.Lock (with self.mu) from ledger.py must trigger a critical One-Way Door."""
    orig_code = LEDGER_PY.read_text()
    # Remove the `with self.mu:` block
    mutated_code = orig_code.replace("with self.mu:", "if True:")
    mutated_file = tmp_path / "unsafe_ledger.py"
    mutated_file.write_text(mutated_code)

    report = governance_engine.audit_source_pair(LEDGER_PY, mutated_file)

    assert report.door_type == DoorType.ONE_WAY
    assert report.is_one_way_door
    assert any(r.category == RiskCategory.CONCURRENCY_MUTATION for r in report.risks)
    assert report.adr_draft is not None
    assert "Architectural Invariant Review" in report.adr_draft


def test_purity_degradation_is_one_way_door(governance_engine: GovernanceEngine, tmp_path: Path):
    """Mutating get_balance (pure) into a state-mutating function must trigger a One-Way Door."""
    orig_code = LEDGER_PY.read_text()
    mutated_code = orig_code.replace(
        "return self.balances[account_id]",
        'self.balances["audit_log"] = 1\n            return self.balances[account_id]',
    )
    mutated_file = tmp_path / "impure_ledger.py"
    mutated_file.write_text(mutated_code)

    report = governance_engine.audit_source_pair(LEDGER_PY, mutated_file)

    assert report.door_type == DoorType.ONE_WAY
    assert report.is_one_way_door
    assert any(r.category == RiskCategory.PURITY_DEGRADATION for r in report.risks)


def test_destructive_sql_pattern_is_one_way_door(governance_engine: GovernanceEngine, tmp_path: Path):
    """SQL schema drops must trigger a high blast-radius One-Way Door."""
    safe_migration = "-- V1: Add users table\nCREATE TABLE users (id SERIAL PRIMARY KEY, email TEXT);"
    drop_migration = "-- V2: Drop accounts table\nDROP TABLE accounts CASCADE;"

    pre_file = tmp_path / "v1.sql"
    post_file = tmp_path / "v2.sql"
    pre_file.write_text(safe_migration)
    post_file.write_text(drop_migration)

    report = governance_engine.audit_source_pair(pre_file, post_file)

    assert report.door_type == DoorType.ONE_WAY
    assert any(r.category == RiskCategory.SCHEMA_MUTATION for r in report.risks)
    assert any("DROP TABLE" in r.description for r in report.risks)
