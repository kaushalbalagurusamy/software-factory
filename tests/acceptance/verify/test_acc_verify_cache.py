"""(5) Proof cache: a stored PROVED must never be reused after anything that can change the verdict changes."""
import json
import sys

import pytest

from factory.verify import gate, solve
from vhelp import contract_doc, run_gate, verdicts

X = {"x": "int"}
GOOD = "def f(x: int) -> int:\n    return max(x, 0)\n"
DOC = contract_doc(X, post=["result >= 0"])


def _run(tmp_path, src, doc=DOC):
    rep = run_gate(tmp_path, src, doc, cache=str(tmp_path / "proofs.json"))
    return rep, rep.contracts[0]["cache_hit"]


def _prime(tmp_path, src=GOOD, doc=DOC):
    rep, hit = _run(tmp_path, src, doc)
    assert rep.exit_code == 0 and not hit, rep.reasons
    rep, hit = _run(tmp_path, src, doc)
    assert rep.exit_code == 0 and hit, "second identical run should be a cache hit"


def test_formatting_and_comments_keep_the_entry(tmp_path):
    _prime(tmp_path)
    _, hit = _run(tmp_path, "# header\n\n\ndef f(x: int) -> int:\n    # comment\n    return max(x,\n               0)\n")
    assert hit


def test_implementation_change_invalidates(tmp_path):
    _prime(tmp_path)
    rep, hit = _run(tmp_path, "def f(x: int) -> int:\n    return x\n")
    assert not hit and rep.exit_code == gate.EXIT_COUNTEREXAMPLE


def test_contract_change_invalidates(tmp_path):
    _prime(tmp_path)
    rep, hit = _run(tmp_path, GOOD, contract_doc(X, post=["result >= 1"]))
    assert not hit and rep.exit_code == gate.EXIT_COUNTEREXAMPLE


def test_dependency_change_invalidates(tmp_path):
    src = "class Bad(ValueError):\n    pass\n\n\ndef f(x: int) -> int:\n    if x < 0:\n        raise Bad('n')\n    return x\n"
    doc = contract_doc(X, post=["result >= 0"], errors=[{"exception": "Bad", "when": "x < 0"}])
    _prime(tmp_path, src, doc)
    _, hit = _run(tmp_path, src.replace("ValueError", "KeyError"), doc)
    assert not hit


@pytest.mark.parametrize("what", ["z3", "python", "tool", "assumptions"])
def test_tool_versions_and_assumptions_invalidate(tmp_path, monkeypatch, what):
    _prime(tmp_path)
    if what == "z3":
        monkeypatch.setattr(gate, "z3_version", lambda: "0.0.0-other")
    elif what == "python":
        monkeypatch.setattr(gate.platform, "python_version", lambda: "2.7.0")
    elif what == "tool":
        monkeypatch.setattr(gate, "__version__", "9.9.9")
    else:
        monkeypatch.setattr(solve, "IMPLICIT_ASSUMPTIONS", solve.IMPLICIT_ASSUMPTIONS + ["a new assumption"])
    _, hit = _run(tmp_path, GOOD)
    assert not hit, what


def test_failures_are_never_cached(tmp_path):
    bad = "def f(x: int) -> int:\n    return x\n"
    for _ in range(2):
        rep, hit = _run(tmp_path, bad)
        assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE and not hit


def test_corrupt_cache_is_ignored(tmp_path):
    (tmp_path / "proofs.json").write_text("{not json", encoding="utf-8")
    rep, hit = _run(tmp_path, "def f(x: int) -> int:\n    return x\n")
    assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE and not hit


# Module-level code outside the function's AST that changes what `f` really is.
STALE = {"redefinition": GOOD, "rebinding": GOOD}
AFTER = {
    "redefinition": GOOD + "\n\ndef f(x: int) -> int:\n    return -1\n",
    "rebinding": GOOD + "\n\ndef g(x: int) -> int:\n    return -1\n\n\nf = g\n",
}


@pytest.mark.parametrize("label", sorted(STALE))
def test_stale_proof_not_reused_when_module_rebinds(tmp_path, label):
    _prime(tmp_path, STALE[label])
    rep, hit = _run(tmp_path, AFTER[label])
    ns: dict = {}
    exec(AFTER[label], ns)
    assert ns["f"](x=-5) < 0, "fixture must really violate result >= 0 now"
    assert not (hit and rep.exit_code == 0), f"{label}: stale cached PROVED reused, gate passed; real f(-5) = {ns['f'](x=-5)}"


def test_shadowed_builtin_is_refused_and_never_cached(tmp_path):
    """The translator models the builtin max, so a module with its own max cannot be PROVED, fresh or cached.

    Restated from the earlier shadow_builtin stale-cache case after the fix: priming is now refused, which is the
    sound outcome (requirement 4). The stale-reuse assertion is kept for the changed module.
    """
    before = GOOD.replace("def f", "def max(a, b):\n    return a if a > b else b\n\n\ndef f")
    after = GOOD.replace("def f", "def max(a, b):\n    return a\n\n\ndef f")
    for src in (before, after):
        rep, hit = _run(tmp_path, src)
        assert rep.exit_code != 0 and not hit, rep.reasons
        assert all(o["verdict"] != "PROVED" for o in verdicts(rep).values()), verdicts(rep)
        cache = tmp_path / "proofs.json"
        assert not cache.exists() or json.loads(cache.read_text())["entries"] == {}


# patchmod.apply(f) runs at import of accmod; changing patchmod.py leaves accmod.py byte-identical.
PATCH_NOOP = "def apply(fn):\n    return None\n"
PATCH_BAD = (
    "def apply(fn):\n"
    "    def bad(x):\n        if x == 50:\n            return -1\n        return max(x, 0)\n"
    "    c = fn.__code__\n"
    "    fn.__code__ = bad.__code__.replace(co_name=c.co_name, co_firstlineno=c.co_firstlineno)\n"
)
PATCHED_MOD = "import patchmod\n\n\n" + GOOD + "\n\npatchmod.apply(f)\n"


def _fresh_import(monkeypatch, tmp_path, patch_src):
    (tmp_path / "patchmod.py").write_text(patch_src, encoding="utf-8")
    monkeypatch.delitem(sys.modules, "patchmod", raising=False)  # each CLI run is a fresh process


def test_stale_proof_not_reused_when_imported_module_patches_f(tmp_path, monkeypatch):
    """Cross-module construct the fixed gate still accepts: another repo module swaps f.__code__ at import time."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _fresh_import(monkeypatch, tmp_path, PATCH_NOOP)
    _prime_patched = [_run(tmp_path, PATCHED_MOD) for _ in range(2)]
    assert _prime_patched[0][0].exit_code == 0 and _prime_patched[1][1], "priming with a no-op patch should cache"
    _fresh_import(monkeypatch, tmp_path, PATCH_BAD)
    rep, hit = _run(tmp_path, PATCHED_MOD)
    ns = {"__name__": "check"}
    exec(compile((tmp_path / "accmod.py").read_text(), "accmod.py", "exec"), ns)
    assert ns["f"](x=50) == -1, "fixture must really violate result >= 0 now"
    assert not (hit and rep.exit_code == 0), "stale cached PROVED reused after patchmod.py changed what f computes"
    assert rep.exit_code != 0, f"gate passed although real f(50) == -1: {verdicts(rep)}"


def test_cache_entry_records_hash_inputs(tmp_path):
    _prime(tmp_path)
    entry = run_gate(tmp_path, GOOD, DOC, cache=str(tmp_path / "proofs.json")).contracts[0]
    assert set(entry["hashes"]) == {"implementation", "dependencies", "contract"}
    data = json.loads((tmp_path / "proofs.json").read_text())
    assert len(data["entries"]) == 1
