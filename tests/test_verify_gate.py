import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from factory.verify import gate, solve
from test_verify_support import FIXTURES, clamp_contract, make

REPO = Path(__file__).resolve().parent.parent
DIV_ERR = [{"exception": "ZeroDivisionError", "when": "b == 0"}]


def run(contracts, **kw):
    kw.setdefault("roots", [FIXTURES])
    return gate.run_gate(contracts, **kw)


def codes(rep):
    return {r["code"] for r in rep.reasons}


# ------------------------------------------------------------------ passing
def test_gate_passes_known_good_with_full_report():
    rep = run([clamp_contract()])
    assert rep.passed and rep.exit_code == gate.EXIT_OK and not rep.reasons
    d = rep.as_dict()
    assert d["tool_versions"]["z3"] and d["tool_versions"]["python"]
    c = d["contracts"][0]
    assert c["contract_id"] == "C-TEST-001"
    assert len(c["hashes"]["implementation"]) == 64 and len(c["hashes"]["contract"]) == 64
    assert isinstance(c["hashes"]["dependencies"], dict)
    assert c["assumptions"] and any("math_int" in a for a in c["assumptions"])
    assert {o["verdict"] for o in c["obligations"]} == {"PROVED"}
    json.dumps(d)  # serialisable


def test_routed_unsupported_passes_but_is_visible():
    c = make("impls_unsupported:sum_to", {"n": "int"}, post=["result >= 0"], route={"default": "property"})
    rep = run([c])
    assert rep.passed
    obs = rep.as_dict()["contracts"][0]["obligations"]
    assert all(o["verdict"] == "UNSUPPORTED" and o["route"] == {"method": "property"} for o in obs)


# ------------------------------------------------------------ failing modes
def test_unrouted_unsupported_fails_gate():
    c = make("impls_unsupported:calls_helper", {"x": "int"}, post=["result > x"])
    rep = run([c])
    assert not rep.passed and rep.exit_code == gate.EXIT_UNSUPPORTED_UNROUTED
    assert "UNSUPPORTED_UNROUTED" in codes(rep)


def test_counterexample_fails_gate_with_reason():
    rep = run([clamp_contract("impls_bad:clamp_wrong_comparison")])
    assert rep.exit_code == gate.EXIT_COUNTEREXAMPLE and "COUNTEREXAMPLE" in codes(rep)
    assert any("inputs" in r["message"] or r.get("obligation") for r in rep.reasons)


def test_model_mismatch_fails_gate(monkeypatch):
    from factory.verify import irgen
    monkeypatch.setattr(irgen, "floordiv_expr", lambda z3, a, b: a / b)
    c = make("impls_good:floor_div", {"a": "int", "b": "int"}, pre=["b != 0"], post=["b > 0 or a - b * result <= 0"])
    rep = run([c])
    assert rep.exit_code == gate.EXIT_MODEL_MISMATCH and "MODEL_MISMATCH" in codes(rep)


def test_timeout_fails_gate():
    c = make("impls_hard:cubes", {"x": "int", "y": "int", "z": "int"}, pre=["x > 1", "y > 1", "z > 1"], post=["result != 0"])
    rep = run([c], timeout_ms=30)
    assert not rep.passed
    assert rep.exit_code in (gate.EXIT_TIMEOUT, gate.EXIT_UNKNOWN)
    assert codes(rep) & {"TIMEOUT", "UNKNOWN"}


def test_vacuous_contract_fails_gate():
    c = make("impls_good:clamp", pre=["lo > hi and lo < hi"], post=["result >= lo"])
    rep = run([c])
    assert not rep.passed and rep.exit_code == gate.EXIT_CONTRACT_REVIEW
    assert {"VACUOUS", "CONTRACT_REVIEW"} <= codes(rep)
    # even with the review stage off, the solver stage itself refuses to call a vacuous obligation proved
    rep2 = run([c], review=False)
    assert rep2.exit_code == gate.EXIT_VACUOUS and "VACUOUS" in codes(rep2)


def test_contract_review_error_fails_gate_before_trusting_proof():
    # contradictory postconditions: reviewed as an error even if the solver says something
    c = make("impls_good:my_abs", {"x": "int"}, post=["result > x", "result < x"])
    rep = run([c])
    assert not rep.passed and "CONTRACT_REVIEW" in codes(rep)


def test_missing_z3_fails_gate(monkeypatch):
    monkeypatch.setitem(sys.modules, "z3", None)  # import z3 -> ImportError
    rep = run([clamp_contract()])
    assert not rep.passed and rep.exit_code == gate.EXIT_Z3_MISSING and "Z3_MISSING" in codes(rep)
    assert rep.as_dict()["tool_versions"]["z3"] is None


def test_missing_z3_not_masked_by_routed_contract(monkeypatch):
    monkeypatch.setitem(sys.modules, "z3", None)
    c = make("impls_unsupported:sum_to", {"n": "int"}, post=["result >= 0"], route={"default": "test"})
    assert run([c]).exit_code == gate.EXIT_Z3_MISSING


def test_extraction_crash_fails_gate(tmp_path):
    c = make("nosuchmod:f", {"x": "int"}, post=["result > 0"])
    rep = gate.run_gate([c], roots=[tmp_path])
    assert rep.exit_code == gate.EXIT_CRASH and "CRASH" in codes(rep)


def test_translation_crash_fails_gate_not_unsupported(monkeypatch):
    from factory.verify import irgen

    def boom(*a, **k):
        raise RuntimeError("translator exploded")
    monkeypatch.setattr(irgen, "execute", boom)
    rep = run([clamp_contract()])
    assert rep.exit_code == gate.EXIT_CRASH
    assert any("translator exploded" in r["message"] for r in rep.reasons)


def test_signature_mismatch_fails_gate():
    c = make("impls_good:clamp", {"x": "int"}, post=["result > 0"])
    assert run([c]).exit_code == gate.EXIT_CRASH


def test_no_contracts_fails_closed():
    assert run([]).exit_code != gate.EXIT_OK


def test_duplicate_or_retired_contract_ids_fail():
    a, b = clamp_contract(cid="C-DUP-001"), clamp_contract(cid="C-DUP-001")
    assert run([a, b]).exit_code == gate.EXIT_CONTRACT_REVIEW
    assert run([clamp_contract(cid="C-OLD-001")], retired_ids=["C-OLD-001"]).exit_code == gate.EXIT_CONTRACT_REVIEW


def test_exit_codes_are_distinct_and_nonzero():
    names = [n for n in dir(gate) if n.startswith("EXIT_") and n != "EXIT_OK"]
    vals = [getattr(gate, n) for n in names]
    assert len(set(vals)) == len(vals) and all(v != 0 for v in vals)
    assert gate.EXIT_OK == 0


# ------------------------------------------------- the patch-that-used-to-pass
def test_patch_passing_old_tests_but_violating_invariant_is_rejected():
    contract = make("discount_base:apply_discount", {"price": "int", "discount": "int"},
                    pre=["price >= 0", "discount >= 0"],
                    post=["result == price - discount or result == 0"],
                    inv=["result >= 0"])
    # example tests that "used to pass" on both versions
    import importlib.util

    def load(name):
        spec = importlib.util.spec_from_file_location(name, FIXTURES / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    for mod in (load("discount_base"), load("discount_head")):
        assert mod.apply_discount(100, 30) == 70 and mod.apply_discount(50, 50) == 0
    base = run([contract])
    assert base.passed, base.reasons
    head_contract = make("discount_head:apply_discount", {"price": "int", "discount": "int"},
                         pre=["price >= 0", "discount >= 0"], post=["result == price - discount or result == 0"],
                         inv=["result >= 0"])
    head = run([head_contract])
    assert not head.passed and head.exit_code == gate.EXIT_COUNTEREXAMPLE
    ce = next(o for c in head.as_dict()["contracts"] for o in c["obligations"] if o["verdict"] == "COUNTEREXAMPLE")
    assert ce["id"] == "inv-1" and ce["counterexample"]["inputs"]["discount"] > ce["counterexample"]["inputs"]["price"]
    # same contract, source overridden to the head version via source_file
    over = gate.run_gate([contract], source_files={"discount_base:apply_discount": FIXTURES / "discount_head.py"})
    assert over.exit_code == gate.EXIT_COUNTEREXAMPLE
    fixed = gate.run_gate([contract], source_files={"discount_base:apply_discount": FIXTURES / "discount_fixed.py"})
    assert fixed.passed


# --------------------------------------------------------------------- cache
def test_cache_hit_then_invalidation(tmp_path):
    cache = tmp_path / "cache.json"
    c = clamp_contract()
    first = run([c], cache_path=cache)
    assert first.passed and not first.as_dict()["contracts"][0]["cache_hit"]
    assert cache.exists() and json.loads(cache.read_text())["entries"]
    second = run([c], cache_path=cache)
    assert second.as_dict()["contracts"][0]["cache_hit"] and second.passed
    strip = lambda rep: [{**o, "cached": None} for o in rep.as_dict()["contracts"][0]["obligations"]]  # noqa: E731
    assert strip(second) == strip(first)
    assert all(o["cached"] for o in second.as_dict()["contracts"][0]["obligations"])
    assert not any(o["cached"] for o in first.as_dict()["contracts"][0]["obligations"])

    # contract changes -> miss
    c2 = make("impls_good:clamp", pre=["lo <= hi"], post=["result >= lo"])
    assert not run([c2], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    # implementation changes -> miss (and the new result is recomputed, not served)
    src = tmp_path / "impls_good.py"
    src.write_text((FIXTURES / "impls_good.py").read_text())
    # an identical copy elsewhere has the same implementation hash: a legitimate hit (the key is content, not path)
    a = gate.run_gate([c], roots=[tmp_path], cache_path=cache)
    assert a.as_dict()["contracts"][0]["cache_hit"]
    src.write_text(src.read_text().replace("if x < lo:\n        return lo", "if x > lo:\n        return lo"))
    b = gate.run_gate([c], roots=[tmp_path], cache_path=cache)
    assert not b.as_dict()["contracts"][0]["cache_hit"] and b.exit_code == gate.EXIT_COUNTEREXAMPLE
    # formatting/comment-only change does not change the implementation (AST) hash
    src.write_text((FIXTURES / "impls_good.py").read_text().replace("def my_abs", "# a comment\n\n\ndef my_abs"))
    assert gate.run_gate([c], roots=[tmp_path], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_cache_invalidated_by_z3_version_assumptions_and_dependencies(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    c = clamp_contract()
    run([c], cache_path=cache)
    monkeypatch.setattr(solve, "z3_version", lambda: "9.9.9")
    monkeypatch.setattr(gate, "z3_version", lambda: "9.9.9")
    assert not run([c], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    monkeypatch.undo()
    c3 = clamp_contract(assumptions=["an extra stated assumption"])
    assert not run([c3], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    # a same-module dependency edit changes the dependency hash even though the function body is identical
    dep = tmp_path / "d.py"
    dep.write_text("def helper(x: int) -> int:\n    return x + 1\n\n\ndef f(x: int) -> int:\n    return helper(x)\n")
    cd = make("d:f", {"x": "int"}, post=["result > x"], route={"default": "test"})
    first = gate.run_gate([cd], roots=[tmp_path], cache_path=cache)
    assert first.passed and "helper" in first.as_dict()["contracts"][0]["hashes"]["dependencies"]
    assert gate.run_gate([cd], roots=[tmp_path], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]
    dep.write_text(dep.read_text().replace("x + 1", "x - 1"))
    assert not gate.run_gate([cd], roots=[tmp_path], cache_path=cache).as_dict()["contracts"][0]["cache_hit"]


def test_failures_are_never_cached(tmp_path):
    cache = tmp_path / "c.json"
    bad = clamp_contract("impls_bad:clamp_wrong_comparison")
    run([bad], cache_path=cache)
    again = run([bad], cache_path=cache)
    assert not again.as_dict()["contracts"][0]["cache_hit"] and not again.passed


def test_corrupt_cache_is_ignored_not_trusted(tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text("{not json")
    rep = run([clamp_contract()], cache_path=cache)
    assert rep.passed and not rep.as_dict()["contracts"][0]["cache_hit"]


# ----------------------------------------------------------------------- CLI
def cli(*args, cwd=None):
    env = {"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, "-m", "factory.verify", *args], capture_output=True, text=True, cwd=cwd or REPO, env=env)


def write_contract(tmp_path, name, **kw):
    c = clamp_contract(**kw)
    p = tmp_path / name
    p.write_text(yaml.safe_dump(c.raw))
    return p


def test_cli_check_contracts_ok_and_bad(tmp_path):
    good = write_contract(tmp_path, "good.yaml")
    r = cli("check-contracts", str(good))
    assert r.returncode == 0, r.stdout + r.stderr
    bad = tmp_path / "bad.yaml"
    d = dict(yaml.safe_load(good.read_text()))
    d["intended"]["preconditions"] = ["lo > hi and lo < hi"]
    bad.write_text(yaml.safe_dump(d))
    r = cli("check-contracts", str(bad))
    assert r.returncode == gate.EXIT_CONTRACT_REVIEW and "PRECONDITION_UNSATISFIABLE" in r.stdout


def test_cli_check_contracts_against_old_version(tmp_path):
    old = write_contract(tmp_path, "old.yaml")
    d = yaml.safe_load(old.read_text())
    d["intended"]["preconditions"] = ["lo <= hi", "x > 0"]
    new = tmp_path / "new.yaml"
    new.write_text(yaml.safe_dump(d))
    r = cli("check-contracts", str(new), "--against", str(old))
    assert r.returncode == gate.EXIT_CONTRACT_REVIEW and "PRECONDITION_STRENGTHENED" in r.stdout


def test_cli_verify_and_report(tmp_path):
    good = write_contract(tmp_path, "good.yaml", symbol="impls_good:clamp")
    out = tmp_path / "report.json"
    r = cli("verify", str(good), "--root", str(FIXTURES), "--report", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["passed"] is True and data["tool_versions"]["z3"]
    r2 = cli("report", str(out))
    assert r2.returncode == 0 and "PROVED" in r2.stdout
    bad = write_contract(tmp_path, "bad.yaml", symbol="impls_bad:clamp_wrong_comparison")
    rb = cli("verify", str(bad), "--root", str(FIXTURES), "--report", str(tmp_path / "r2.json"), "--regress-dir", str(tmp_path / "reg"))
    assert rb.returncode == gate.EXIT_COUNTEREXAMPLE
    assert list((tmp_path / "reg").glob("test_*.py"))
    assert cli("report", str(tmp_path / "r2.json")).returncode == gate.EXIT_COUNTEREXAMPLE


def test_cli_missing_contract_file_fails_closed(tmp_path):
    r = cli("verify", str(tmp_path / "nope.yaml"), "--root", str(FIXTURES))
    assert r.returncode != 0


def test_cli_malformed_contract_fails_closed(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("contract_id: x\n")
    r = cli("check-contracts", str(p))
    assert r.returncode == gate.EXIT_USAGE and "missing required" in (r.stdout + r.stderr)


# --------------------------------------------------------- no-fallback guard
def test_no_regex_or_text_fallback_modules():
    import factory.verify.consistency as consistency
    import factory.verify.gate as gate
    from factory.verify import irgen
    for mod in (solve, irgen, consistency, gate):
        tree = ast.parse(inspect.getsource(mod))
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not imported & {"re", "difflib", "fnmatch", "glob"}, (mod.__name__, imported)


