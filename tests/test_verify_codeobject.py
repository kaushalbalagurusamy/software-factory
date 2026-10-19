"""V9: the bound function must be exactly the parsed def; the cache must see imported repo modules."""
import sys

import pytest

from factory.verify import gate, solve
from factory.verify.loader import BindingError, load_target
from test_verify_support import make

X = {"x": "int"}
GOOD = "def f(x: int) -> int:\n    return max(x, 0)\n"
SWAP = ("    def bad(x):\n        if x == 50:\n            return -1\n        return max(x, 0)\n"
        "    c = fn.__code__\n"
        "    fn.__code__ = bad.__code__.replace(co_name=c.co_name, co_firstlineno=c.co_firstlineno)\n")


def run(tmp_path, src, **kw):
    (tmp_path / "m.py").write_text(src)
    return gate.run_gate([make("m:f", X, post=["result >= 0"])], roots=[tmp_path], **kw)


@pytest.fixture
def patchmod(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "patchmod", raising=False)

    def write(body):
        (tmp_path / "patchmod.py").write_text(body)
        sys.modules.pop("patchmod", None)
    return write


@pytest.mark.parametrize("semantics", ["math_int", "int64"])
def test_in_module_code_swap_is_refused(tmp_path, semantics):
    src = GOOD + "\n\ndef _p(fn):\n" + SWAP + "\n\n_p(f)\n"
    (tmp_path / "m.py").write_text(src)
    rep = gate.run_gate([make("m:f", X, post=["result >= 0"], semantics=semantics)], roots=[tmp_path])
    assert rep.exit_code == gate.EXIT_BINDING and "compiled code" in rep.reasons[0]["message"]
    assert all(o["verdict"] != "PROVED" for o in rep.as_dict()["contracts"][0]["obligations"])


@pytest.mark.parametrize("patch", [
    "f.__defaults__ = (1,)",
    "f.__kwdefaults__ = {'k': 1}",
    "f.__wrapped__ = len",
    "f.__code__ = f.__code__.replace(co_consts=(None, 7))",
    "f.__code__ = (lambda x: x).__code__.replace(co_name='f', co_firstlineno=1)",
])
def test_other_function_object_tampering_is_refused(tmp_path, patch):
    rep = run(tmp_path, GOOD + f"\n{patch}\n")
    assert rep.exit_code == gate.EXIT_BINDING, rep.reasons


def test_closure_or_foreign_globals_are_refused(tmp_path):
    foreign = GOOD + "\nimport types\nf = types.FunctionType(f.__code__, {'max': max})\n"
    rep = run(tmp_path, foreign)
    assert rep.exit_code == gate.EXIT_BINDING


def test_untouched_function_and_literal_defaults_pass(tmp_path):
    assert run(tmp_path, GOOD).passed
    t = load_target("m:f", roots=[tmp_path])
    assert t.cacheable and t.imports_hash
    (tmp_path / "d.py").write_text("def f(x: int = 3) -> int:\n    return max(x, 0)\n")
    assert load_target("d:f", roots=[tmp_path]).func.__defaults__ == (3,)


def test_imported_module_swap_is_refused_and_cache_notices_change(tmp_path, patchmod):
    cache = tmp_path / "c.json"
    src = "import patchmod\n\n\n" + GOOD + "\npatchmod.apply(f)\n"
    patchmod("def apply(fn):\n    return None\n")
    assert run(tmp_path, src, cache_path=cache).passed
    assert run(tmp_path, src, cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    patchmod("def apply(fn):\n" + SWAP)
    rep = run(tmp_path, src, cache_path=cache)
    assert rep.exit_code == gate.EXIT_BINDING and not rep.as_dict()["contracts"][0]["cache_hit"]


def test_transitive_import_change_invalidates(tmp_path, patchmod):
    cache = tmp_path / "c.json"
    (tmp_path / "leaf.py").write_text("K = 1\n")
    patchmod("import leaf\n\n\ndef apply(fn):\n    return leaf.K\n")
    src = "import patchmod\n\n\n" + GOOD + "\npatchmod.apply(f)\n"
    assert run(tmp_path, src, cache_path=cache).passed
    assert run(tmp_path, src, cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    (tmp_path / "leaf.py").write_text("K = 2\n")
    assert not run(tmp_path, src, cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_unresolvable_import_disables_caching(tmp_path):
    cache = tmp_path / "c.json"
    src = "try:\n    import not_a_real_module_xyz\nexcept ImportError:\n    pass\n\n\n" + GOOD
    rep = run(tmp_path, src, cache_path=cache)
    assert rep.passed
    e = rep.as_dict()["contracts"][0]
    assert e["cacheable"] is False and "not cached" in e["cache_note"]
    assert not cache.exists() or not run(tmp_path, src, cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_stdlib_imports_do_not_disable_caching(tmp_path):
    cache = tmp_path / "c.json"
    src = "import math\nfrom os import path\n\n\n" + GOOD
    run(tmp_path, src, cache_path=cache)
    assert run(tmp_path, src, cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_boundary_samples_include_contract_and_function_constants(tmp_path):
    (tmp_path / "m.py").write_text("def f(x: int) -> int:\n    return -1 if x == 50 else max(x, 0)\n")
    c = make("m:f", X, post=["result >= 0 or x == 777"])
    t = load_target("m:f", roots=[tmp_path])
    consts = solve._constants(c, t)
    assert {49, 50, 51, 776, 777, 778} <= set(consts)
    xs = {a["x"] for a in solve._sample_inputs(c, [], consts)}
    assert {49, 50, 51, 777} <= xs


def test_single_point_divergence_is_found_by_boundary_samples(tmp_path):
    # a (simulated) translator bug that is only wrong at x == 50: random samples would essentially never hit it
    (tmp_path / "m.py").write_text("def f(x: int) -> int:\n    return -1 if x == 50 else max(x, 0)\n")
    c = make("m:f", X, post=["result >= 0"])
    t = load_target("m:f", roots=[tmp_path])
    # pretend z3 "proved" it: the cross-check samples alone must expose the violation at x == 50
    import factory.verify.replay as replay
    consts = solve._constants(c, t)
    bad = [a for a in solve._sample_inputs(c, [], consts)
           if solve.violated(c, solve.obligations_of(c)[0], a, replay.call_target(t, a, "math_int"))]
    assert {"x": 50} in bad
