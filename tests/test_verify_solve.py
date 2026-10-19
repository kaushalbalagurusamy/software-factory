import ast
import inspect

import pytest

from factory.verify import irgen, solve
from factory.verify.loader import load_target
from factory.verify.solve import Verdict, verify_contract
from test_verify_support import FIXTURES, clamp_contract, make, target_for, verdicts

DIV_ERR = [{"exception": "ZeroDivisionError", "when": "b == 0"}]


def run(contract, **kw):
    return verify_contract(contract, target_for(contract), **kw)


# ------------------------------------------------------------- known good
def test_clamp_proved():
    r = run(clamp_contract())
    assert set(verdicts(r).values()) == {"PROVED"}
    assert r.precondition_satisfiable is True


def test_abs_proved():
    c = make("impls_good:my_abs", {"x": "int"}, post=["result >= 0", "result == x or result == -x"])
    assert set(verdicts(run(c)).values()) == {"PROVED"}


def test_floor_div_with_nonzero_precondition_proved():
    c = make("impls_good:floor_div", {"a": "int", "b": "int"}, pre=["b != 0"],
             post=["result * b <= a if b > 0 else result * b >= a", "result == a // b"])
    assert set(verdicts(run(c)).values()) == {"PROVED"}


def test_python_floor_semantics_negative_operands():
    # floor, not truncation: -7 // 2 == -4 and -7 % 2 == 1; 7 % -2 == -1
    c = make("impls_good:floor_mod", {"a": "int", "b": "int"}, pre=["b != 0"],
             post=["result == a - b * (a // b)", "b > 0 and 0 <= result < b or b < 0 and b < result <= 0"])
    assert set(verdicts(run(c)).values()) == {"PROVED"}


def test_declared_division_error_proved():
    c = make("impls_good:safe_div", {"a": "int", "b": "int"}, errors=DIV_ERR, post=["result == a // b"])
    assert set(verdicts(run(c)).values()) == {"PROVED"}


def test_builtin_min_max_and_bool_return():
    c = make("impls_good:max3", {"a": "int", "b": "int", "c": "int"},
             post=["result >= a and result >= b and result >= c", "result == a or result == b or result == c"])
    assert set(verdicts(run(c)).values()) == {"PROVED"}
    c2 = make("impls_good:is_even", {"n": "int"}, returns="bool", post=["result == (n % 2 == 0)", "result or n % 2 == 1"])
    assert set(verdicts(run(c2)).values()) == {"PROVED"}


# ------------------------------------------------------ intentionally bad
@pytest.mark.parametrize("fn", ["clamp_off_by_one", "clamp_wrong_comparison"])
def test_bad_clamp_counterexample_replayed(fn):
    r = run(clamp_contract(f"impls_bad:{fn}"))
    bad = [o for o in r.obligations if o.verdict is Verdict.COUNTEREXAMPLE]
    assert bad, verdicts(r)
    for o in bad:
        assert o.replay["reproduced"] is True
        args = o.counterexample["inputs"]
        assert args["lo"] <= args["hi"]  # satisfies the precondition
        # reproduce independently by calling the real function
        real = getattr(load_target(f"impls_bad:{fn}", roots=[FIXTURES]).func, "__call__")(**args)
        assert o.replay["outcome"]["value"] == real


def test_missing_guard_is_undeclared_error_counterexample():
    c = make("impls_bad:floor_div_no_guard", {"a": "int", "b": "int"}, post=["result == a // b"])
    r = run(c)
    v = verdicts(r)
    assert v["no-undeclared-errors"] == "COUNTEREXAMPLE"
    ce = next(o for o in r.obligations if o.id == "no-undeclared-errors")
    assert ce.counterexample["inputs"]["b"] == 0
    assert ce.replay["outcome"]["exc"] == "ZeroDivisionError"


def test_declared_error_not_actually_raised_is_counterexample():
    # the implementation never raises ValueError, contract says it must when x < 0
    c = make("impls_good:my_abs", {"x": "int"}, errors=[{"exception": "ValueError", "when": "x < 0"}], post=["result >= 0"])
    assert verdicts(run(c))["err-ValueError"] == "COUNTEREXAMPLE"


def test_spec_matching_buggy_impl_text_is_not_proved():
    # postcondition textually equals the (wrong) implementation; intent is x + 1
    wrong = make("impls_bad:add_two", {"x": "int"}, post=["result == x + 1"])
    assert verdicts(run(wrong))["post-1"] == "COUNTEREXAMPLE"
    # and a spec that merely restates the implementation proves only what the implementation does
    same = make("impls_bad:add_two", {"x": "int"}, post=["result == x + 2"])
    assert verdicts(run(same))["post-1"] == "PROVED"


# ------------------------------------------------------------ unsupported
def test_loop_unsupported_and_routed():
    c = make("impls_unsupported:sum_to", {"n": "int"}, post=["result >= 0"], route={"default": "property"})
    r = run(c)
    assert set(verdicts(r).values()) == {"UNSUPPORTED"}
    assert "loops" in r.translation_unsupported
    assert all(o.route == {"method": "property"} for o in r.obligations)


def test_call_unsupported_unrouted_has_no_route():
    c = make("impls_unsupported:calls_helper", {"x": "int"}, post=["result > x"])
    r = run(c)
    assert set(verdicts(r).values()) == {"UNSUPPORTED"}
    assert "helper" in r.translation_unsupported
    assert all(o.route is None for o in r.obligations)


def test_float_unsupported():
    c = make("impls_unsupported:uses_float", {"x": "int"}, post=["result <= x"])
    assert set(verdicts(run(c)).values()) == {"UNSUPPORTED"}


@pytest.mark.parametrize("src,reason", [
    ("def f(x: int) -> int:\n    for i in x:\n        pass\n    return x\n", "loops"),
    ("def f(x: int) -> int:\n    try:\n        return x\n    except Exception:\n        return 0\n", "try"),
    ("def f(x: int) -> int:\n    return [i for i in x]\n", "comprehensions"),
    ("def f(x: int) -> int:\n    return x.real\n", "attribute"),
    ("def f(x: int) -> int:\n    return g(x)\n", "call"),
    ("def f(x: int) -> int:\n    return x / 2\n", "division"),
    ("def f(x: int) -> int:\n    global G\n    return x\n", "global"),
    ("def f(x: int) -> int:\n    return G\n", "global"),
    ("def f(x: int) -> bool:\n    return x > 0\n", "disagrees"),
    ("def f(x) -> int:\n    return x\n", "annotation"),
    ("def f(x: int) -> int:\n    if x > 0:\n        return 1\n", "fall off"),
    ("def f(x: int) -> int:\n    if x:\n        return 1\n    return 2\n", "truthiness"),
    ("def f(x: int) -> int:\n    return 1.0\n", "floating"),
    ("def f(x: int) -> int:\n    y = 1 if x else 2\n    return y\n", "conditional"),
    ("def f(x: int) -> int:\n    if x > 0:\n        y = 1\n    else:\n        pass\n    return y\n", "unbound"),
    ("def f(x: int) -> int:\n    x.a = 1\n    return x\n", "mutation"),
    ("def f(x: int) -> int:\n    return x ** 2\n", "operator"),
])
def test_unsupported_constructs_have_specific_reasons(tmp_path, src, reason):
    p = tmp_path / "m.py"
    p.write_text(src)
    c = make("m:f", {"x": "int"}, post=["result >= 0"], route={"default": "test"})
    r = verify_contract(c, load_target("m:f", roots=[tmp_path]))
    assert set(verdicts(r).values()) == {"UNSUPPORTED"}, verdicts(r)
    assert reason in r.translation_unsupported.lower(), r.translation_unsupported


def test_non_solver_method_is_routed_not_solved():
    c = make("impls_good:clamp", post=["result >= lo"], method="integration")
    r = run(c)
    assert {o.verdict.value for o in r.obligations} == {"UNSUPPORTED"}
    assert all(o.route == {"method": "integration"} for o in r.obligations)


def test_per_obligation_method_override():
    c = make("impls_good:clamp", pre=["lo <= hi"], post=["result >= lo", {"id": "slow", "expr": "result <= hi", "check_method": "property"}])
    v = verdicts(run(c))
    assert v["post-1"] == "PROVED" and v["slow"] == "UNSUPPORTED"


def test_signature_mismatch_is_extraction_error():
    c = make("impls_good:clamp", {"x": "int", "lo": "int"}, post=["result >= lo"])
    with pytest.raises(solve.ExtractionError):
        run(c)


# -------------------------------------------------------- vacuity / honesty
def test_unsatisfiable_precondition_is_vacuous_not_proved():
    c = make("impls_good:clamp", pre=["lo > hi and lo < hi"], post=["result >= lo"])
    r = run(c)
    assert r.precondition_satisfiable is False
    assert all(o.vacuous and o.verdict is Verdict.UNKNOWN for o in r.obligations)
    assert Verdict.PROVED not in {o.verdict for o in r.obligations}


def test_unreachable_error_clause_is_vacuous():
    c = make("impls_good:safe_div", {"a": "int", "b": "int"}, pre=["b > 0"], errors=DIV_ERR, post=["result == a // b"])
    r = run(c)
    assert verdicts(r)["err-ZeroDivisionError"] == "UNKNOWN"
    assert next(o for o in r.obligations if o.id == "err-ZeroDivisionError").vacuous


def test_postcondition_with_no_reachable_return_is_vacuous(tmp_path):
    (tmp_path / "m.py").write_text("def f(x: int) -> int:\n    raise ValueError('always')\n")
    c = make("m:f", {"x": "int"}, post=["result == 12345"], errors=[{"exception": "ValueError", "when": "x == x"}])
    r = verify_contract(c, load_target("m:f", roots=[tmp_path]))
    assert verdicts(r)["post-1"] == "UNKNOWN" and r.obligations[0].vacuous


def test_translator_bug_is_model_mismatch(monkeypatch):
    # Break the floor-division model: z3's Euclidean div differs from Python floor for b < 0.
    monkeypatch.setattr(irgen, "floordiv_expr", lambda z3, a, b: a / b)
    c = make("impls_good:floor_div", {"a": "int", "b": "int"}, pre=["b != 0"], post=["b > 0 or a - b * result <= 0"])
    r = run(c)
    assert verdicts(r)["post-1"] == "MODEL_MISMATCH"
    o = r.obligations[0]
    assert o.replay["reproduced"] is False


def test_translator_bug_making_false_proof_is_caught_by_cross_check(monkeypatch):
    # Pretend ``a % b`` is always 0: z3 then "proves" result == 0 which the real code violates.
    monkeypatch.setattr(irgen, "mod_expr", lambda z3, a, b: a * 0)
    c = make("impls_good:floor_mod", {"a": "int", "b": "int"}, pre=["b != 0"], post=["result == 0"])
    r = run(c)
    assert verdicts(r)["post-1"] == "MODEL_MISMATCH"


# ----------------------------------------------------------------- timeouts
def test_hard_nonlinear_obligation_times_out_or_unknown():
    c = make("impls_hard:cubes", {"x": "int", "y": "int", "z": "int"},
             pre=["x > 1", "y > 1", "z > 1"], post=["result != 0"])
    r = run(c, timeout_ms=30)
    v = verdicts(r)["post-1"]
    assert v in ("TIMEOUT", "UNKNOWN"), v
    assert next(o for o in r.obligations if o.id == "post-1").reason


# ------------------------------------------------------------------- int64
def test_int64_overflow_refutes_what_math_int_proves():
    post = ["result > x"]
    math = make("impls_int64:add_one", {"x": "int"}, post=post, semantics="math_int")
    assert set(verdicts(run(math)).values()) == {"PROVED"}
    i64 = make("impls_int64:add_one", {"x": "int"}, post=post, semantics="int64")
    r = run(i64)
    v = verdicts(r)
    assert v["no-undeclared-errors"] == "COUNTEREXAMPLE"
    ce = next(o for o in r.obligations if o.id == "no-undeclared-errors")
    assert ce.counterexample["inputs"]["x"] == 2**63 - 1
    assert ce.replay["outcome"]["exc"] == "OverflowError"


def test_int64_guarded_version_proved_with_declared_overflow():
    c = make("impls_int64:add_one_guarded", {"x": "int"}, post=["result > x"],
             errors=[{"exception": "OverflowError", "when": "x == 9223372036854775807"}], semantics="int64")
    assert set(verdicts(run(c)).values()) == {"PROVED"}


def test_int64_literal_out_of_range_unsupported(tmp_path):
    (tmp_path / "m.py").write_text("def f(x: int) -> int:\n    return x + 9223372036854775808\n")
    c = make("m:f", {"x": "int"}, post=["result > x"], semantics="int64", route={"default": "test"})
    assert set(verdicts(verify_contract(c, load_target("m:f", roots=[tmp_path]))).values()) == {"UNSUPPORTED"}


# ---------------------------------------------- no syntactic fallback
SRC = inspect.getsource(solve)


def test_proved_only_produced_after_solver_unsat():
    tree = ast.parse(SRC)
    holders = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and n.attr == "PROVED" and isinstance(n.value, ast.Name) and n.value.id == "Verdict":
                if isinstance(getattr(n, "ctx", None), ast.Load):
                    holders.add(fn.name)
    # PROVED is *used* in exactly: the producer, and the cross-check that downgrades/looks it up
    assert "_prove_from_unsat" in holders
    prove_src = inspect.getsource(solve._prove_from_unsat)
    assert '"unsat"' in prove_src and "p_sat.status" in prove_src
    producers = [name for name in holders if name not in ("_prove_from_unsat",)]
    # any other mention is a comparison in a set/ is-check, never a constructor call
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in producers]:
        for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call)]:
            for a in call.args:
                assert not (isinstance(a, ast.Attribute) and a.attr == "PROVED"), fn.name
