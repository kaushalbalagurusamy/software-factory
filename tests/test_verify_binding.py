"""Soundness regressions: verify the function Python really binds, and fail closed on ambiguity."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from factory.verify import consistency as cons
from factory.verify import gate
from factory.verify.loader import BindingError, load_target
from test_verify_support import make

REPO = Path(__file__).resolve().parent.parent
X = {"x": "int"}


def gate_for(tmp_path, src, contract=None, **kw):
    (tmp_path / "m.py").write_text(src)
    return gate.run_gate([contract or make("m:f", X, post=["result >= 0"])], roots=[tmp_path], **kw)


GOOD = "def f(x: int) -> int:\n    return max(x, 0)\n"


@pytest.mark.parametrize("src", [
    GOOD + "\n\ndef f(x: int) -> int:\n    return -1\n",                                # redefinition
    GOOD + "\n\ng = lambda x: -1\nf = g\n",                                              # rebinding
    "if True:\n    def f(x: int) -> int:\n        return x\nelse:\n    def f(x: int) -> int:\n        return -x\n",
    GOOD + "\nfrom os.path import *\n",                                                   # star import
    GOOD + "\n\ndef patch():\n    global f\n    f = None\n",                              # global rebinding
    GOOD + "\ndel f\nf = 1\n",
    "import f\n" + GOOD,
])
def test_ambiguous_target_binding_is_refused(tmp_path, src):
    rep = gate_for(tmp_path, src)
    assert rep.exit_code == gate.EXIT_BINDING and {r["code"] for r in rep.reasons} == {"BINDING"}
    obs = rep.as_dict()["contracts"][0]["obligations"]
    assert obs and all(o["verdict"] != "PROVED" for o in obs)


def test_refusal_applies_even_with_routes(tmp_path):
    c = make("m:f", X, post=["result >= 0"], route={"default": "test"})
    rep = gate_for(tmp_path, GOOD + "\nf = abs\n", c)
    assert rep.exit_code == gate.EXIT_BINDING


@pytest.mark.parametrize("name", ["abs", "min", "max"])
def test_called_builtin_shadowed_at_module_level_is_refused(tmp_path, name):
    src = f"def {name}(*a):\n    return a[0]\n\n\ndef f(x: int) -> int:\n    return {name}(x, 0) if True else 0\n"
    rep = gate_for(tmp_path, src)
    assert rep.exit_code == gate.EXIT_MODEL_MISMATCH and "rebound or shadowed" in rep.reasons[0]["message"]


def test_called_builtin_shadowed_by_local_is_refused_but_a_plain_parameter_is_fine(tmp_path):
    rep = gate_for(tmp_path, "def f(x: int) -> int:\n    abs = lambda v: v\n    return abs(x)\n")
    assert rep.exit_code != 0
    ok = gate_for(tmp_path, "def f(max: int) -> int:\n    return max + 1\n", make("m:f", {"max": "int"}, post=["result > max"]))
    assert ok.passed
    unused = gate_for(tmp_path, "def max(a, b):\n    return a\n\n\ndef f(x: int) -> int:\n    return x\n",
                      make("m:f", X, post=["result == x"]))
    assert unused.passed  # shadow exists but the function never calls it


def test_loader_resolves_the_bound_object_and_rejects_mismatch(tmp_path):
    (tmp_path / "m.py").write_text(GOOD)
    t = load_target("m:f", roots=[tmp_path])
    assert t.func.__code__.co_firstlineno == t.node.lineno and t.namespace["f"] is t.func and len(t.module_hash) == 64


@pytest.mark.parametrize("semantics", ["math_int", "int64"])
def test_redefinition_never_proves_the_first_def(tmp_path, semantics):
    src = GOOD + "\n\ndef f(x: int) -> int:\n    return -1 if x == 50 else max(x, 0)\n"
    rep = gate_for(tmp_path, src, make("m:f", X, post=["result >= 0"], semantics=semantics))
    assert rep.exit_code == gate.EXIT_BINDING


def test_int64_replay_runs_the_bound_function_and_flags_divergence(tmp_path):
    from factory.verify import replay
    (tmp_path / "m.py").write_text("def f(x: int) -> int:\n    return x + 1\n")
    t = load_target("m:f", roots=[tmp_path])
    assert replay.call_target(t, {"x": 4}, "int64").value == 5
    t.func = lambda x: 99  # the bound object differs from the parsed AST
    assert replay.call_target(t, {"x": 4}, "int64").kind == "diverged"


def test_int64_module_defined_exception_resolves_from_module_namespace(tmp_path):
    src = "class Bad(ValueError):\n    pass\n\n\ndef f(x: int) -> int:\n    if x < 0:\n        raise Bad('neg')\n    return x\n"
    c = make("m:f", X, post=["result >= 0"], errors=[{"exception": "Bad", "when": "x < 0"}], semantics="int64")
    assert gate_for(tmp_path, src, c).passed


# --------------------------------------------------------------- signature
@pytest.mark.parametrize("src", [
    "def f(x: int) -> bool:\n    return x > 0\n",
    "def f(x, y):\n    return x\n",
    "def f(x):\n    return x\n",
    "def f(x: int, *rest: int) -> int:\n    return x\n",
    "def f(x: int, y: int = 0) -> int:\n    return x\n",
])
@pytest.mark.parametrize("route", [None, "test"])
def test_signature_mismatch_is_always_exit_11(tmp_path, src, route):
    c = make("m:f", X, post=["result >= 0"], **({"route": {"default": route}} if route else {}))
    rep = gate_for(tmp_path, src, c)
    assert rep.exit_code == gate.EXIT_CRASH, rep.reasons


def test_signature_mismatch_even_for_non_solver_contract(tmp_path):
    c = make("m:f", X, post=["result >= 0"], method="test")
    assert gate_for(tmp_path, "def f(x: int, y: int) -> int:\n    return x\n", c).exit_code == gate.EXIT_CRASH


# ------------------------------------------------------------------- cache
def test_module_level_change_outside_the_function_invalidates_cache(tmp_path):
    cache = tmp_path / "c.json"
    src = "K = 1\n\n\n" + GOOD
    assert gate_for(tmp_path, src, cache_path=cache).passed
    again = gate_for(tmp_path, src, cache_path=cache)
    assert again.as_dict()["contracts"][0]["cache_hit"] and all(o["cached"] for o in again.as_dict()["contracts"][0]["obligations"])
    assert not gate_for(tmp_path, src.replace("K = 1", "K = 2"), cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_cli_labels_cached_and_no_cache_ignores_it(tmp_path):
    (tmp_path / "m.py").write_text(GOOD)
    cy = tmp_path / "c.yaml"
    cy.write_text(yaml.safe_dump(make("m:f", X, post=["result >= 0"]).raw))
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    base = [sys.executable, "-m", "factory.verify", "verify", str(cy), "--root", str(tmp_path)]
    run = lambda *a: subprocess.run(base + list(a), capture_output=True, text=True, env=env)  # noqa: E731
    assert "(cached)" not in run("--cache", str(tmp_path / "p.json")).stdout
    assert "PROVED (cached)" in run("--cache", str(tmp_path / "p.json")).stdout
    out = run("--cache", str(tmp_path / "p.json"), "--no-cache")
    assert "(cached)" not in out.stdout and out.returncode == 0


def test_forged_cache_file_is_only_trusted_when_a_cache_is_requested(tmp_path):
    # documents the limit: a hand-written entry for the right key forges a pass, hence --no-cache for release
    cache = tmp_path / "c.json"
    assert gate_for(tmp_path, GOOD, cache_path=cache).passed
    d = json.loads(cache.read_text())
    (k, v), = d["entries"].items()
    bad = "def f(x: int) -> int:\n    return -1\n"
    assert gate_for(tmp_path, bad).exit_code == gate.EXIT_COUNTEREXAMPLE   # no cache: failure is seen


# ---------------------------------------------------------------- crashes
def test_broken_z3_at_run_time_is_exit_11_with_report(tmp_path, monkeypatch):
    import z3
    monkeypatch.setattr(z3, "Solver", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken z3")))
    rep = gate_for(tmp_path, GOOD)
    assert rep.exit_code == gate.EXIT_CRASH and any("broken z3" in r["message"] for r in rep.reasons)
    assert rep.as_dict()["passed"] is False


# ----------------------------------------------------------------- review
def test_int64_range_tautology_is_vacuous_in_review():
    c = make("m:f", X, post=[f"result >= {-2**63} and result <= {2**63 - 1}"], semantics="int64")
    r = cons.review_contract(c)
    assert any(f.code == "VACUOUS_POSTCONDITION" and f.severity == "error" for f in r.findings)
    # but the same predicate is a real constraint under unbounded math_int
    c2 = make("m:f", X, post=[f"result >= {-2**63} and result <= {2**63 - 1}"])
    assert cons.review_contract(c2).ok


def test_errors_covering_every_allowed_input_make_postconditions_unreachable():
    c = make("m:f", X, pre=["x >= 0"], post=["result > 100"], errors=[{"exception": "ValueError", "when": "x >= 0"}])
    r = cons.review_contract(c)
    assert [f.code for f in r.findings] == ["POSTCONDITIONS_NEVER_APPLY"] and not r.ok
    partial = make("m:f", X, pre=["x >= 0"], post=["result > 100"], errors=[{"exception": "ValueError", "when": "x > 5"}])
    assert cons.review_contract(partial).ok
