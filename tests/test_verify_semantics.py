"""Differential test: the z3 model of generated programs must agree with real Python execution."""

import ast

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from factory.verify import irgen, replay
from factory.verify.loader import Target
from factory.verify.solve import require_z3

z3 = require_z3()

SMALL = st.integers(-6, 6)
EDGE = st.sampled_from([-(2**63), 2**63 - 1, 2**62, -(2**62), 2**32, 0, 1, -1])
VALUE = st.one_of(SMALL, EDGE)


def int_expr(depth):
    leaf = st.one_of(st.sampled_from(["x", "y"]), SMALL.map(str))
    if depth == 0:
        return leaf
    sub = int_expr(depth - 1)
    binop = st.tuples(sub, st.sampled_from(["+", "-", "*", "//", "%"]), sub).map(lambda t: f"({t[0]} {t[1]} {t[2]})")
    neg = sub.map(lambda e: f"(-{e})")
    call1 = sub.map(lambda e: f"abs({e})")
    call2 = st.tuples(st.sampled_from(["min", "max"]), sub, sub).map(lambda t: f"{t[0]}({t[1]}, {t[2]})")
    cond = st.tuples(sub, st.sampled_from(["<", "<=", "==", "!=", ">", ">="]), sub, sub, sub).map(
        lambda t: f"({t[3]} if {t[0]} {t[1]} {t[2]} else {t[4]})")
    return st.one_of(leaf, binop, neg, call1, call2, cond)


def model_outcome(fn_ast, semantics, args):
    """Evaluate the z3 path model on concrete inputs; returns ('return', v) or ('raise', exc)."""
    func = irgen.parse_function(fn_ast, "int")
    env, _ = irgen.make_params(z3, func.params, semantics)
    paths = irgen.execute(z3, func, env, semantics)
    subs = [(env[k], z3.IntVal(v)) for k, v in args.items()]
    hits = []
    for p in paths:
        if z3.is_true(z3.simplify(z3.substitute(p.cond, *subs))):
            hits.append(p)
    assert len(hits) == 1, f"paths must partition the inputs, got {len(hits)}"
    p = hits[0]
    if p.kind == "raise":
        return ("raise", p.exc)
    return ("return", z3.simplify(z3.substitute(p.value, *subs)).as_long())


@pytest.mark.parametrize("semantics", ["math_int", "int64"])
@settings(max_examples=400, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_translator_agrees_with_python(semantics, data):
    expr = data.draw(int_expr(3))
    x, y = data.draw(VALUE), data.draw(VALUE)
    src = f"def f(x: int, y: int) -> int:\n    return {expr}\n"
    node = ast.parse(src).body[0]
    t = Target("m:f", "<gen>", src, ast.parse(src), node, None, "", {})
    ns = {}
    exec(src, ns)
    t.func = ns["f"]
    real = replay.call_target(t, {"x": x, "y": y}, semantics)
    got = model_outcome(node, semantics, {"x": x, "y": y})
    if real.kind == "return":
        assert got == ("return", real.value), (src, x, y)
    else:
        assert got == ("raise", real.exc), (src, x, y, real)


@settings(max_examples=100, deadline=None)
@given(a=st.integers(-50, 50), b=st.integers(-50, 50).filter(lambda v: v != 0))
def test_floor_div_mod_match_python_exactly(a, b):
    env = {"a": z3.IntVal(a), "b": z3.IntVal(b)}
    assert z3.simplify(irgen.floordiv_expr(z3, env["a"], env["b"])).as_long() == a // b
    assert z3.simplify(irgen.mod_expr(z3, env["a"], env["b"])).as_long() == a % b


def test_bool_logic_short_circuit_faults_are_guarded():
    # (b != 0 and a // b > 0): the division only faults when b == 0 is *not* guarded away
    src = "def f(a: int, b: int) -> bool:\n    return b != 0 and a // b > 0\n"
    node = ast.parse(src).body[0]
    func = irgen.parse_function(node, "bool")
    env, _ = irgen.make_params(z3, func.params, "math_int")
    paths = irgen.execute(z3, func, env, "math_int")
    s = z3.Solver()
    s.add(env["b"] == 0, z3.Or(*[p.cond for p in paths if p.kind == "raise"]))
    assert s.check() == z3.unsat  # no ZeroDivisionError: short-circuit protects it
    ns = {}
    exec(src, ns)
    assert ns["f"](5, 0) is False
