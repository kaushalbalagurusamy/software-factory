"""
Tests for Software Factory Polyglot Dual-Anchor Transpiler.
Validates:
1. Cross-lingual parity synthesis (Python -> Go) with certified ΔS = ∅.
2. Formal detection of invariant divergence (e.g. missing locks).
3. Cryptographic parity certificate issuance.
4. CLI command integration (sf transpile).
"""

from pathlib import Path
import pytest

from factory.transpiler import PolyglotTranspiler, TranspilationResult
from factory.cli import main

UNITY_DIR = Path("/Users/kaushal/Projects/unity/examples/ledger")
LEDGER_PY = UNITY_DIR / "ledger.py"
LEDGER_GO = UNITY_DIR / "ledger.go"


def test_transpiler_python_to_go_parity(tmp_path: Path):
    """Verify that Python ledger transpiles to Go with mathematically certified ΔS = ∅."""
    transpiler = PolyglotTranspiler()
    out_go = tmp_path / "ledger.go"

    res = transpiler.synthesize(
        source_path=LEDGER_PY,
        target_lang="go",
        out_path=out_go,
    )

    assert res.success is True
    assert out_go.exists()
    assert res.certificate is not None
    assert res.certificate["cross_lingual_parity"] == "PROVEN (ΔS = ∅)"
    assert res.semantic_delta is not None
    assert res.semantic_delta.is_identical is True


def test_transpiler_catches_divergent_candidate(tmp_path: Path):
    """Verify that candidate with concurrency flaw is flagged and rejected."""
    # Mock generator that produces Go code omitting mutex locks
    def flawed_go_generator(prompt: str) -> str:
        return """
```go
package ledger

import "errors"

var ErrNotFound = errors.New("not found")

type Ledger struct {
    balances map[string]int64
}

func (l *Ledger) GetBalance(accountID string) (int64, error) {
    bal, exists := l.balances[accountID]
    if !exists {
        return 0, ErrNotFound
    }
    return bal, nil
}
```
"""
    transpiler = PolyglotTranspiler()
    out_go = tmp_path / "flawed_ledger.go"

    res = transpiler.synthesize(
        source_path=LEDGER_PY,
        target_lang="go",
        out_path=out_go,
        mock_generator=flawed_go_generator,
    )

    assert res.success is False
    assert res.certificate is None
    assert len(res.delta_violations) > 0


def test_transpiler_missing_source(tmp_path: Path):
    transpiler = PolyglotTranspiler()
    fake_source = tmp_path / "nonexistent.py"

    res = transpiler.synthesize(
        source_path=fake_source,
        target_lang="go",
    )
    assert res.success is False
    assert "does not exist" in res.error_message


def test_cli_transpile_command(tmp_path: Path, capsys):
    out_go = tmp_path / "cli_ledger.go"
    ret = main([
        "transpile",
        "--source", str(LEDGER_PY),
        "--target-lang", "go",
        "--out", str(out_go),
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "CERTIFIED (ΔS = ∅)" in captured.out
    assert "PROVEN (ΔS = ∅)" in captured.out
