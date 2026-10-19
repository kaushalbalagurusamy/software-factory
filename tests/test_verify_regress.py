import os
import subprocess
import sys
from pathlib import Path

import pytest

from factory.verify import gate, regress
from factory.verify.solve import Verdict
from test_verify_support import FIXTURES, clamp_contract, make

REPO = Path(__file__).resolve().parent.parent


def pytest_run(path: Path, cwd: Path):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(path)],
                          capture_output=True, text=True, cwd=cwd, env=env)


def roundtrip(tmp_path, contract, bad_src, fixed_src, symbol_module="m"):
    impl = tmp_path / f"{symbol_module}.py"
    impl.write_text(bad_src)
    rep = gate.run_gate([contract], roots=[tmp_path])
    assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE, rep.reasons
    files = regress.write_regressions(rep, tmp_path / "reg")
    assert files
    bad = pytest_run(tmp_path / "reg", tmp_path)
    assert bad.returncode != 0, bad.stdout          # fails on the buggy implementation
    impl.write_text(fixed_src)
    good = pytest_run(tmp_path / "reg", tmp_path)
    assert good.returncode == 0, good.stdout + good.stderr   # passes once fixed
    assert gate.run_gate([contract], roots=[tmp_path]).passed
    return files


def test_postcondition_counterexample_roundtrip(tmp_path):
    bad = "def f(x: int) -> int:\n    return x + 1 if x > 0 else x\n"
    fixed = "def f(x: int) -> int:\n    return x + 1\n"
    c = make("m:f", {"x": "int"}, post=["result == x + 1"])
    files = roundtrip(tmp_path, c, bad, fixed)
    text = files[0].read_text()
    assert "INPUTS" in text and "m:f" in text and "result == x + 1" in text
    assert files[0].name.startswith("test_regress_c_test_001_post_1")


def test_invariant_patch_regression_roundtrip(tmp_path):
    base = (FIXTURES / "discount_base.py").read_text().replace("def apply_discount", "def apply_discount")
    c = make("m:apply_discount", {"price": "int", "discount": "int"}, pre=["price >= 0", "discount >= 0"],
             post=["result == price - discount or result == 0"], inv=["result >= 0"])
    roundtrip(tmp_path, c, (FIXTURES / "discount_head.py").read_text(), base)


def test_undeclared_error_roundtrip_fix_by_guarding(tmp_path):
    bad = "def f(a: int, b: int) -> int:\n    return a // b\n"
    fixed = "def f(a: int, b: int) -> int:\n    if b == 0:\n        raise ZeroDivisionError('b')\n    return a // b\n"
    c = make("m:f", {"a": "int", "b": "int"}, post=["result == a // b"],
             errors=[{"exception": "ZeroDivisionError", "when": "b == 0"}])
    # the bad version *does* raise ZeroDivisionError at b == 0, which is declared: so this is actually fine.
    (tmp_path / "m.py").write_text(bad)
    assert gate.run_gate([c], roots=[tmp_path]).passed
    # an undeclared variant: contract declares nothing, bad raises, fix constrains the domain via contract precondition
    c2 = make("m:f", {"a": "int", "b": "int"}, post=["result == a // b"])
    rep = gate.run_gate([c2], roots=[tmp_path])
    assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE
    files = regress.write_regressions(rep, tmp_path / "reg")
    assert pytest_run(tmp_path / "reg", tmp_path).returncode != 0
    (tmp_path / "m.py").write_text("def f(a: int, b: int) -> int:\n    return a // b if b != 0 else 0\n")
    assert pytest_run(tmp_path / "reg", tmp_path).returncode == 0


def test_declared_error_regression_roundtrip(tmp_path):
    bad = "def f(a: int, b: int) -> int:\n    return a // b if b != 0 else 0\n"
    fixed = "def f(a: int, b: int) -> int:\n    if b == 0:\n        raise ZeroDivisionError('b')\n    return a // b\n"
    c = make("m:f", {"a": "int", "b": "int"}, errors=[{"exception": "ZeroDivisionError", "when": "b == 0"}],
             post=["result == a // b"])
    roundtrip(tmp_path, c, bad, fixed)


def test_int64_overflow_regression_roundtrip(tmp_path):
    bad = "def f(x: int) -> int:\n    return x + 1\n"
    fixed = "def f(x: int) -> int:\n    return x + 1 if x < 9223372036854775807 else x\n"  # saturating add
    c = make("m:f", {"x": "int"}, post=["result >= x"], semantics="int64")
    files = roundtrip(tmp_path, c, bad, fixed)
    assert "9223372036854775807" in files[0].read_text() and "'int64'" in files[0].read_text()


def test_regression_refuses_non_counterexample(tmp_path):
    rep = gate.run_gate([clamp_contract()], roots=[FIXTURES])
    c, t, r = rep.results[0]
    with pytest.raises(ValueError):
        regress.render_regression(c, r.obligations[0], t.file)
    assert regress.write_regressions(rep, tmp_path / "none") == []


def test_stale_bytecode_cannot_desync_source_and_executed_code(tmp_path):
    # same-size edit inside one mtime second: a cached .pyc would run the old code
    impl = tmp_path / "m.py"
    impl.write_text("def f(x: int) -> int:\n    return x + 1\n")
    c = make("m:f", {"x": "int"}, post=["result == x + 1"])
    assert gate.run_gate([c], roots=[tmp_path]).passed
    impl.write_text("def f(x: int) -> int:\n    return x + 2\n")
    rep = gate.run_gate([c], roots=[tmp_path])
    assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE
