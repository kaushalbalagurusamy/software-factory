"""(1) Unsound PROVED hunt: every verdict must agree with brute-force execution of the real function.

Each case states the expected verdicts so the case cannot silently become UNSUPPORTED; vhelp.assert_consistent
additionally checks PROVED against a brute-force domain and replays every COUNTEREXAMPLE with plain Python.
"""
import pytest

from vhelp import INT64_MAX, INT64_MIN, assert_consistent, contract_doc, real_function, run_gate, verdicts

P, PC = "PROVED", "COUNTEREXAMPLE"
AB = {"a": "int", "b": "int"}
X = {"x": "int"}

CASES = {
    # Python floor division / modulo with negative operands
    "floordiv_identity": ("def f(a: int, b: int) -> int:\n    return a // b\n",
                          contract_doc(AB, pre=["b != 0"], post=["a == b * result + a % b"]), {"post-1": P}),
    "floordiv_wrong_bound": ("def f(a: int, b: int) -> int:\n    return a // b\n",
                             contract_doc(AB, pre=["b != 0"], post=["result * b <= a"]), {"post-1": PC}),
    "floordiv_rounds_down": ("def f(a: int, b: int) -> int:\n    return a // b\n",
                             contract_doc(AB, pre=["b != 0"], post=["result * b == a or (result < 0) == (a * b < 0)"]),
                             {"post-1": P}),
    "mod_sign_of_divisor": ("def f(a: int, b: int) -> int:\n    return a % b\n",
                            contract_doc(AB, pre=["b != 0"], post=["(b > 0 and 0 <= result < b) or (b < 0 and b < result <= 0)"]),
                            {"post-1": P}),
    "mod_nonneg_wrong": ("def f(a: int, b: int) -> int:\n    return a % b\n",
                         contract_doc(AB, pre=["b != 0"], post=["result >= 0"]), {"post-1": PC}),
    "div_by_zero_undeclared": ("def f(a: int, b: int) -> int:\n    return a // b\n",
                               contract_doc(AB, post=["result == a // b"]),
                               {"post-1": P, "no-undeclared-errors": PC}),
    "div_by_zero_declared": ("def f(a: int, b: int) -> int:\n    return a % b\n",
                             contract_doc(AB, post=["result == a % b"], errors=[{"exception": "ZeroDivisionError", "when": "b == 0"}]),
                             {"post-1": P, "err-ZeroDivisionError": P, "no-undeclared-errors": P}),
    # large values (math_int has no overflow)
    "large_constants": ("def f(x: int) -> int:\n    return x * 100000000000000000000 - 99999999999999999999 * x\n",
                        contract_doc(X, post=["result == x"]), {"post-1": P}),
    # bool / int mixing through a ternary
    "bool_param_ternary": ("def f(p: bool, x: int) -> int:\n    return x if p else -x\n",
                           contract_doc({"p": "bool", "x": "int"}, post=["result == abs(x) or result == -abs(x)", "result >= 0"]),
                           {"post-1": P, "post-2": PC}),
    # short-circuit guards a fault, in both orders
    "and_guards_division": ("def f(x: int, y: int) -> bool:\n    return x != 0 and y // x > 1\n",
                            contract_doc({"x": "int", "y": "int"}, returns="bool", post=["result == (x != 0 and y // x > 1)"]),
                            {"post-1": P, "no-undeclared-errors": P}),
    "and_wrong_order_faults": ("def f(x: int, y: int) -> bool:\n    return y // x > 1 and x != 0\n",
                               contract_doc({"x": "int", "y": "int"}, returns="bool", post=["result == (y // x > 1 and x != 0)"]),
                               {"no-undeclared-errors": PC}),
    "or_guards_division": ("def f(x: int, y: int) -> bool:\n    return x == 0 or y % x == 0\n",
                           contract_doc({"x": "int", "y": "int"}, returns="bool", post=["result == (x == 0 or y % x == 0)"]),
                           {"post-1": P, "no-undeclared-errors": P}),
    # chained comparisons, including a faulting middle operand
    "chain_basic": ("def f(x: int, y: int) -> bool:\n    return 0 <= x < y\n",
                    contract_doc({"x": "int", "y": "int"}, returns="bool", post=["result == (x >= 0 and x < y)", "result == (0 <= x and 0 < y)"]),
                    {"post-1": P, "post-2": PC}),
    "chain_fault_middle": ("def f(x: int) -> bool:\n    return 0 < 10 // x < 5\n",
                           contract_doc(X, returns="bool", post=["result == (0 < 10 // x < 5)"]),
                           {"no-undeclared-errors": PC}),
    "chain_fault_short_circuit": ("def f(x: int) -> bool:\n    return x > 0 < 10 // x\n",
                                  contract_doc(X, returns="bool", post=["result == (0 < x <= 10)"]),
                                  {"post-1": P, "no-undeclared-errors": P}),
    # abs/min/max edges
    "max_minus_min": ("def f(a: int, b: int, c: int) -> int:\n    return max(a, b, c) - min(a, b, c)\n",
                      contract_doc({"a": "int", "b": "int", "c": "int"}, post=["result >= 0", "result == 0"]),
                      {"post-1": P, "post-2": PC}),
    "abs_minus_x": ("def f(x: int) -> int:\n    return abs(x) - x\n",
                    contract_doc(X, post=["result >= 0", "result % 2 == 0", "result == 0"]),
                    {"post-1": P, "post-2": P, "post-3": PC}),
    # conditional expression precedence: a if c else (b + 1)
    "ternary_precedence": ("def f(a: int, b: int) -> int:\n    return a if a > b else b + 1\n",
                           contract_doc(AB, post=["result == (a if a > b else b + 1)", "result == max(a, b) + 1"]),
                           {"post-1": P, "post-2": PC}),
    "neg_ternary_is_abs": ("def f(x: int) -> int:\n    return -x if x < 0 else x\n",
                           contract_doc(X, post=["result == abs(x)"]), {"post-1": P}),
    # augmented assignments incl. //= and %= with a negative multiplier
    "augassign_chain": ("def f(x: int) -> int:\n    y = x\n    y -= 3\n    y *= -2\n    y //= 4\n    y %= 5\n    return y\n",
                        contract_doc(X, post=["0 <= result < 5", "result == ((x - 3) * -2 // 4) % 5", "result == ((x - 3) * -2 // 4) % 5 + 0 * x and result != 4"]),
                        {"post-1": P, "post-2": P, "post-3": PC}),
    # early returns in nested ifs, a raise on one inner path, fall-through to a final return
    "nested_early_returns": (
        "def f(x: int, y: int) -> int:\n"
        "    if x > 0:\n        if y > 0:\n            return 1\n        elif y < 0:\n            return -1\n        return 0\n"
        "    else:\n        if y == 0:\n            raise ValueError('zero')\n"
        "    return 2\n",
        contract_doc({"x": "int", "y": "int"}, post=["-1 <= result <= 2", "x > 0 or result == 2", "result != 0"],
                     errors=[{"exception": "ValueError", "when": "x <= 0 and y == 0"}]),
        {"post-1": P, "post-2": P, "post-3": PC, "err-ValueError": P, "no-undeclared-errors": P}),
    "raise_condition_too_wide": ("def f(x: int) -> int:\n    if x < 0:\n        raise ValueError('neg')\n    return x\n",
                                 contract_doc(X, post=["result >= 0"], errors=[{"exception": "ValueError", "when": "x <= 0"}]),
                                 {"post-1": P, "err-ValueError": PC}),
    "raise_wrong_class": ("def f(x: int) -> int:\n    if x < 0:\n        raise KeyError('neg')\n    return x\n",
                          contract_doc(X, post=["result >= 0"], errors=[{"exception": "ValueError", "when": "x < 0"}]),
                          {"err-ValueError": PC, "no-undeclared-errors": PC}),
    # local variable shadowing a builtin name is not the builtin
    "param_named_max": ("def f(max: int) -> int:\n    return max + 1\n",
                        contract_doc({"max": "int"}, post=["result > max"]), {"post-1": P}),
    "bool_returning": ("def f(a: bool, b: bool) -> bool:\n    return a == b or not a\n",
                       contract_doc({"a": "bool", "b": "bool"}, returns="bool", post=["result == (not a or b)", "result"]),
                       {"post-1": P, "post-2": PC}),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_verdict_agrees_with_brute_force(tmp_path, name):
    src, doc, expect = CASES[name]
    assert_consistent(tmp_path, src, doc, expect)


# ----------------------------------------------------------------------------- int64
def _int64_oracle(tmp_path, src, doc, inputs, expect):
    rep = run_gate(tmp_path, src, doc)
    vs = verdicts(rep)
    assert {k: vs[k]["verdict"] for k in expect} == expect, {k: vs[k].get("reason") for k in vs}
    for o in vs.values():
        if o["verdict"] == "COUNTEREXAMPLE":
            a = o["counterexample"]["inputs"]
            assert all(INT64_MIN <= v <= INT64_MAX for v in a.values() if not isinstance(v, bool))
    return vs


def test_int64_increment_overflows_at_max(tmp_path):
    vs = _int64_oracle(tmp_path, "def f(x: int) -> int:\n    return x + 1\n",
                       contract_doc(X, post=["result == x + 1"], semantics="int64"), None,
                       {"post-1": P, "no-undeclared-errors": PC})
    assert vs["no-undeclared-errors"]["counterexample"]["inputs"] == {"x": INT64_MAX}
    assert vs["no-undeclared-errors"]["replay"]["outcome"]["exc"] == "OverflowError"


def test_int64_declared_overflow_is_proved(tmp_path):
    _int64_oracle(tmp_path, "def f(x: int) -> int:\n    return x + 1\n",
                  contract_doc(X, post=["result == x + 1"], errors=[{"exception": "OverflowError", "when": f"x == {INT64_MAX}"}],
                               semantics="int64"), None,
                  {"post-1": P, "err-OverflowError": P, "no-undeclared-errors": P})


@pytest.mark.parametrize("body,bad", [("x // -1", INT64_MIN), ("-x", INT64_MIN), ("abs(x)", INT64_MIN)])
def test_int64_min_edge_overflows(tmp_path, body, bad):
    vs = _int64_oracle(tmp_path, f"def f(x: int) -> int:\n    return {body}\n",
                       contract_doc(X, post=["result != 12345"], semantics="int64"), None,
                       {"no-undeclared-errors": PC})
    assert vs["no-undeclared-errors"]["counterexample"]["inputs"] == {"x": bad}


def test_math_int_has_no_overflow_at_int64_bounds(tmp_path):
    rep, vs = assert_consistent(tmp_path, "def f(x: int) -> int:\n    return x * x\n",
                                contract_doc(X, post=["result >= 0"]), {"post-1": P, "no-undeclared-errors": P},
                                ints=[INT64_MIN, -1, 0, 1, INT64_MAX])


# ------------------------------------------------- module-level code that changes what really runs
REDEF = ("def f(x: int) -> int:\n    return max(x, 0)\n\n\n"
         "def f(x: int) -> int:  # the second definition is the one Python binds\n"
         "    if x == 50:\n        return -1\n    return max(x, 0)\n")
REBIND = "def g(x: int) -> int:\n    return -1\n\n\ndef f(x: int) -> int:\n    return max(x, 0)\n\n\nf = g\n"
SHADOW = "def max(a, b):\n    return a\n\n\ndef f(x: int) -> int:\n    return max(x, 0)\n"


@pytest.mark.parametrize("semantics", ["math_int", "int64"])
@pytest.mark.parametrize("label", ["redefinition", "rebinding", "shadowed_builtin"])
def test_proved_matches_the_function_python_actually_binds(tmp_path, label, semantics):
    """CRITICAL if PROVED: the module binds a different `f` (or `max`) than the AST the translator read."""
    src = {"redefinition": REDEF, "rebinding": REBIND, "shadowed_builtin": SHADOW}[label]
    doc = contract_doc(X, post=["result >= 0"], semantics=semantics)
    rep = run_gate(tmp_path, src, doc)
    fn = real_function(tmp_path / "accmod.py")
    real_bad = [x for x in range(-60, 61) if fn(x=x) < 0]
    assert real_bad, "fixture must really violate the postcondition"
    v = verdicts(rep)["post-1"]["verdict"]
    assert v != "PROVED", f"unsound PROVED ({label}, {semantics}): real f violates result >= 0 at {real_bad[:3]}"
    assert rep.exit_code != 0, f"gate passed ({label}, {semantics}) although real f returns negatives at {real_bad[:3]}"


def test_int64_module_exception_class_is_not_a_model_mismatch(tmp_path):
    """A correct function raising a module-defined exception must not be rejected under int64."""
    src = "class Bad(ValueError):\n    pass\n\n\ndef f(x: int) -> int:\n    if x < 0:\n        raise Bad('neg')\n    return x\n"
    rep = run_gate(tmp_path, src, contract_doc(X, post=["result >= 0"], errors=[{"exception": "Bad", "when": "x < 0"}],
                                               semantics="int64"))
    got = {k: v["verdict"] for k, v in verdicts(rep).items()}
    assert got == {"post-1": P, "err-Bad": P, "no-undeclared-errors": P}, got
    assert rep.exit_code == 0


def test_undefined_exception_name_is_not_proved(tmp_path):
    src = "def f(x: int) -> int:\n    if x < 0:\n        raise NoSuchError('neg')\n    return x\n"
    rep = run_gate(tmp_path, src, contract_doc(X, post=["result >= 0"], errors=[{"exception": "NoSuchError", "when": "x < 0"}]))
    assert verdicts(rep)["err-NoSuchError"]["verdict"] != P  # real Python raises NameError
    assert rep.exit_code != 0


def test_falls_off_the_end_is_unsupported_not_proved(tmp_path):
    rep = run_gate(tmp_path, "def f(x: int) -> int:\n    if x > 0:\n        return 1\n", contract_doc(X, post=["result == 1"]))
    vs = verdicts(rep)
    assert all(o["verdict"] == "UNSUPPORTED" for o in vs.values()), vs
    assert "fall off" in vs["post-1"]["reason"]
    assert rep.exit_code == 12


@pytest.mark.parametrize("body,why", [
    ("return x or 1", "and'/'or"),
    ("return x if x else 1", "non-bool"),
    ("return True + x", "bool"),
    ("return x ** 2", "operator"),
    ("return x / 2", "operator"),
])
def test_value_returning_and_mixed_constructs_are_unsupported(tmp_path, body, why):
    rep = run_gate(tmp_path, f"def f(x: int) -> int:\n    {body}\n", contract_doc(X, post=["result >= 0"]))
    vs = verdicts(rep)
    assert {o["verdict"] for o in vs.values()} == {"UNSUPPORTED"}, vs
    assert why in vs["post-1"]["reason"]
    assert rep.exit_code == 12
