"""
Tests for Software Factory Autonomous Synthesis Engine.
Validates:
1. Multi-format patch parsing (JSON, fenced blocks).
2. Autonomous synthesis cycle with test-time compute reflection.
3. One-Way Door rollback and governance feedback loop.
4. Epistemic Zero-Trust reward-hacking rejection.
5. Multi-iteration self-repair convergence.
6. Cryptographic receipt issuance.
"""

from pathlib import Path
import pytest

from factory.synthesis import (
    SynthesisEngine,
    SynthesisRequest,
    SynthesisResult,
    PatchParser,
)
from factory.governance import GovernanceEngine
from factory.zero_trust import ZeroTrustGate
from factory.cli import main


def test_patch_parser_json():
    raw_response = """
Here is the proposed patch:
```json
{
  "files": [
    {
      "path": "src/calculator.py",
      "content": "def add(a, b):\\n    return a + b\\n"
    }
  ]
}
```
Done!
"""
    files = PatchParser.parse_files(raw_response)
    assert "src/calculator.py" in files
    assert "return a + b" in files["src/calculator.py"]


def test_patch_parser_fenced_blocks():
    raw_response = """
I have implemented the feature:

```file:src/core.py
def process(data):
    return data.strip()
```

And added the test:
```python file:tests/test_core.py
from src.core import process

def test_process():
    assert process("  hello  ") == "hello"
```
"""
    files = PatchParser.parse_files(raw_response)
    assert "src/core.py" in files
    assert "tests/test_core.py" in files
    assert "return data.strip()" in files["src/core.py"]


def test_synthesis_dry_run(tmp_path: Path):
    engine = SynthesisEngine()
    req = SynthesisRequest(
        spec_text="Add multiply function",
        spec_path=None,
        repo_dir=tmp_path,
        dry_run=True,
    )
    res = engine.execute_cycle(req)
    assert res.success is True
    assert res.receipt is not None
    assert res.receipt["mode"] == "dry_run"


def test_synthesis_zero_trust_reward_hacking_rejection(tmp_path: Path):
    """Ensure synthesis rejects candidates that weaken or drop existing test assertions."""
    # Setup repo with an existing test
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_math.py"
    test_file.write_text("def test_one():\n    assert 1 == 1\n    assert 2 == 2\n")

    # Mock generator that attempts reward-hacking by dropping an assertion
    def reward_hack_generator(prompt: str, iteration: int) -> str:
        return """
```file:tests/test_math.py
def test_one():
    assert 1 == 1
```
"""

    engine = SynthesisEngine()
    req = SynthesisRequest(
        spec_text="Refactor test",
        spec_path=None,
        repo_dir=tmp_path,
        max_retries=2,
        mock_generator=reward_hack_generator,
    )
    res = engine.execute_cycle(req)
    assert res.success is False
    assert "Zero-Trust" in res.error_message or "weakened" in res.error_message
    # Assert original test was atomically preserved/rolled back
    assert "assert 2 == 2" in test_file.read_text()


def test_synthesis_governance_one_way_door_rejection(tmp_path: Path):
    """Ensure candidate that weakens concurrency locks is rejected by Governance Gate."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    ledger_file = src_dir / "ledger.py"
    ledger_file.write_text(
        "import threading\n"
        "class Ledger:\n"
        "    def __init__(self):\n"
        "        self.mu = threading.Lock()\n"
        "        self.balance = 0\n"
        "    def deposit(self, amt):\n"
        "        with self.mu:\n"
        "            self.balance += amt\n"
    )

    # Mock generator attempts to remove mutex lock (One-Way Door)
    def unsafe_generator(prompt: str, iteration: int) -> str:
        return """
```file:src/ledger.py
class Ledger:
    def __init__(self):
        self.balance = 0
    def deposit(self, amt):
        self.balance += amt
```
"""

    engine = SynthesisEngine()
    req = SynthesisRequest(
        spec_text="Simplify deposit",
        spec_path=None,
        repo_dir=tmp_path,
        max_retries=2,
        mock_generator=unsafe_generator,
    )
    res = engine.execute_cycle(req)
    assert res.success is False
    assert "Governance Rejection" in res.error_message or "One-Way Door" in res.error_message
    # Assert original mutex was atomically restored
    assert "self.mu" in ledger_file.read_text()


def test_synthesis_self_repair_convergence(tmp_path: Path):
    """Ensure synthesis engine reflects on test failures and converges on subsequent iteration."""
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_feature.py").write_text(
        "from src.feature import get_status\n"
        "def test_status():\n"
        "    assert get_status() == 'ACTIVE'\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "feature.py").write_text("def get_status():\n    return 'PENDING'\n")

    # Iteration 1 returns wrong value; Iteration 2 fixes it based on reflection feedback
    def dynamic_generator(prompt: str, iteration: int) -> str:
        if iteration == 1:
            return """
```file:src/feature.py
def get_status():
    return 'WRONG_VALUE'
```
"""
        else:
            assert "Test Execution Failure" in prompt or "WRONG_VALUE" in prompt
            return """
```file:src/feature.py
def get_status():
    return 'ACTIVE'
```
"""

    engine = SynthesisEngine()
    req = SynthesisRequest(
        spec_text="Make status return ACTIVE",
        spec_path=None,
        repo_dir=tmp_path,
        max_retries=3,
        mock_generator=dynamic_generator,
    )
    res = engine.execute_cycle(req)
    assert res.success is True
    assert res.iterations == 2
    assert res.receipt is not None
    assert "src/feature.py" in res.modified_files
    assert (tmp_path / "src" / "feature.py").read_text().strip() == "def get_status():\n    return 'ACTIVE'"


def test_cli_run_dry_run(tmp_path: Path, capsys):
    spec = tmp_path / "spec.md"
    spec.write_text("# Feature\nAdd basic greeting endpoint.\n")

    ret = main(["run", "--spec", str(spec), "--repo", str(tmp_path), "--dry-run"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "TWO-WAY DOOR DETECTED" in captured.out
    assert "SYNTHESIS CYCLE COMPLETE" in captured.out
    assert "dry_run" in captured.out
