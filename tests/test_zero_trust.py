"""
Tests for Epistemic Zero-Trust Verification Substrate.
Verifies cryptographic baseline locking and anti-reward-hacking AST assertion guards.
"""

from pathlib import Path
import pytest
from factory.zero_trust import BaselineHashGuard, ZeroTrustGate


@pytest.fixture
def mock_repo_dir(tmp_path: Path) -> Path:
    repo = tmp_path / "mock_repo"
    repo.mkdir()
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    # Create a realistic test file
    test_file = tests_dir / "test_ledger.py"
    test_file.write_text("""
def test_deposit():
    balance = 100
    deposit = 50
    balance += deposit
    assert balance == 150
    assert balance > 0

def test_withdraw():
    balance = 150
    assert balance >= 50
""")
    return repo


def test_baseline_hash_computes_manifest(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)
    assert len(manifest) == 1
    assert "tests/test_ledger.py" in manifest
    assert len(manifest["tests/test_ledger.py"]) == 64  # Valid SHA-256


def test_zero_trust_passes_when_untouched(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)
    orig_content = {"tests/test_ledger.py": (mock_repo_dir / "tests/test_ledger.py").read_text()}

    gate = ZeroTrustGate()
    report = gate.audit_patch(
        root_dir=mock_repo_dir,
        baseline_manifest=manifest,
        original_contents=orig_content,
    )
    assert report.passed
    assert not report.baseline_result.reward_hacking_detected


def test_zero_trust_rejects_deleted_test_file(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)

    # Delete the test file
    (mock_repo_dir / "tests/test_ledger.py").unlink()

    gate = ZeroTrustGate()
    report = gate.audit_patch(root_dir=mock_repo_dir, baseline_manifest=manifest)

    assert not report.passed
    assert "tests/test_ledger.py" in report.baseline_result.deleted_files
    assert report.baseline_result.reward_hacking_detected


def test_zero_trust_rejects_assertion_dropping(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)
    orig_text = (mock_repo_dir / "tests/test_ledger.py").read_text()

    # Modify test file by removing an assertion
    weakened_text = orig_text.replace("assert balance > 0", "# dropped assertion")
    (mock_repo_dir / "tests/test_ledger.py").write_text(weakened_text)

    gate = ZeroTrustGate()
    report = gate.audit_patch(
        root_dir=mock_repo_dir,
        baseline_manifest=manifest,
        original_contents={"tests/test_ledger.py": orig_text},
    )

    assert not report.passed
    assert "tests/test_ledger.py" in report.baseline_result.weakened_files
    assert report.baseline_result.reward_hacking_detected
    assert any("Assertion count dropped" in v for v in report.baseline_result.violations)


def test_zero_trust_rejects_skip_injection(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)
    orig_text = (mock_repo_dir / "tests/test_ledger.py").read_text()

    # Inject @pytest.mark.skip onto test_deposit
    skipped_text = orig_text.replace(
        "def test_deposit():",
        "@pytest.mark.skip(reason='bypass test')\ndef test_deposit():",
    )
    (mock_repo_dir / "tests/test_ledger.py").write_text(skipped_text)

    gate = ZeroTrustGate()
    report = gate.audit_patch(
        root_dir=mock_repo_dir,
        baseline_manifest=manifest,
        original_contents={"tests/test_ledger.py": orig_text},
    )

    assert not report.passed
    assert len(report.baseline_result.skipped_tests) > 0
    assert report.baseline_result.reward_hacking_detected
    assert any("injected skip decorator" in v for v in report.baseline_result.violations)


def test_zero_trust_rejects_trivial_assert(mock_repo_dir: Path):
    guard = BaselineHashGuard()
    manifest = guard.compute_manifest(mock_repo_dir)
    orig_text = (mock_repo_dir / "tests/test_ledger.py").read_text()

    # Replace real assertion with `assert True`
    trivial_text = orig_text.replace("assert balance == 150", "assert True")
    (mock_repo_dir / "tests/test_ledger.py").write_text(trivial_text)

    gate = ZeroTrustGate()
    report = gate.audit_patch(
        root_dir=mock_repo_dir,
        baseline_manifest=manifest,
        original_contents={"tests/test_ledger.py": orig_text},
    )

    assert not report.passed
    assert report.baseline_result.reward_hacking_detected
    assert any("trivial assertions" in v for v in report.baseline_result.violations)
