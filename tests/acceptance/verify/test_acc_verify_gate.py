"""(2) vacuity/consistency, (3) gate failure semantics, (4) patch rejection, (6) no PROVED without a solver."""
import ast
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from factory.verify import gate, solve
from factory.verify.consistency import compare_contracts, review_contract
from factory.verify.contracts import parse_contract
from vhelp import contract_doc, run_gate, verdicts, write_module

REPO = Path(__file__).resolve().parents[3]
X = {"x": "int"}


def cli(*args, pre=""):
    """Run `python -m factory.verify` in a subprocess; `pre` is Python run first (e.g. to break z3)."""
    code = pre + "\nimport sys\nfrom factory.verify.__main__ import main\nsys.exit(main(sys.argv[1:]))\n"
    env = dict(os.environ, PYTHONPATH=str(REPO))
    p = subprocess.run([sys.executable, "-c", code, *map(str, args)], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def write_contract(d: Path, doc, name="c.yaml") -> Path:
    p = d / name
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def findings(doc):
    return {f.code: f.severity for f in review_contract(parse_contract(doc)).findings}


def comparison(old, new):
    return {f.code: f.severity for f in compare_contracts(parse_contract(old), parse_contract(new)).findings}


# ------------------------------------------------------------------ (2) vacuity / consistency
GOOD = "def f(x: int) -> int:\n    return abs(x)\n"


@pytest.mark.parametrize("label,doc,code", [
    ("unsat_pre", contract_doc(X, pre=["x > 0", "x < 0"], post=["result >= 0"]), "PRECONDITION_UNSATISFIABLE"),
    ("int64_unsat_pre", contract_doc(X, pre=[f"x > {2**63}"], post=["result >= 0"], semantics="int64"), "PRECONDITION_UNSATISFIABLE"),
    ("contradictory", contract_doc(X, post=["result > 0", "result < 0"]), "POSTCONDITIONS_CONTRADICTORY"),
    ("tautology", contract_doc(X, post=["result == result"]), "VACUOUS_POSTCONDITION"),
    ("old_tautology", contract_doc(X, post=["old(x) == x"]), "VACUOUS_POSTCONDITION"),
    ("implied_by_pre", contract_doc(X, pre=["x > 0"], post=["x > 0 or result == 7"]), "VACUOUS_POSTCONDITION"),
    ("dead_error", contract_doc(X, pre=["x < 0"], post=["result >= 0"], errors=[{"exception": "ValueError", "when": "x > 5"}]),
     "ERROR_CONDITION_UNREACHABLE"),
    ("overlapping_errors", contract_doc(X, post=["result >= 0"], errors=[{"exception": "ValueError", "when": "x < 0"},
                                                                        {"exception": "KeyError", "when": "x < 5"}]),
     "ERROR_CONDITIONS_OVERLAP"),
])
def test_review_flags_and_gate_never_passes_quietly(tmp_path, label, doc, code):
    assert findings(doc).get(code) == "error", findings(doc)
    rep = run_gate(tmp_path, GOOD, doc)
    assert rep.exit_code != 0, f"{label}: a vacuous/inconsistent contract passed the gate"
    rc, out = cli("check-contracts", write_contract(tmp_path, doc))
    assert rc == gate.EXIT_CONTRACT_REVIEW and code in out, out


def test_unsat_precondition_obligations_are_vacuous_not_proved(tmp_path):
    rep = run_gate(tmp_path, GOOD, contract_doc(X, pre=["x > 0", "x < 0"], post=["result >= 0"]), review=False)
    vs = verdicts(rep)
    assert all(o["verdict"] != "PROVED" and o["vacuous"] for o in vs.values()), vs
    assert rep.exit_code == gate.EXIT_VACUOUS


def test_int64_range_tautology_is_flagged(tmp_path):
    """Under checked int64 every returned int is in range, so this postcondition constrains nothing."""
    doc = contract_doc(X, post=[f"result >= {-2**63} and result <= {2**63 - 1}"], semantics="int64")
    rep = run_gate(tmp_path, "def f(x: int) -> int:\n    return x // 2\n", doc)
    assert rep.exit_code != 0, f"tautology PROVED quietly: {verdicts(rep)['post-1']['verdict']}"


def test_postconditions_that_can_never_apply_are_flagged_before_code(tmp_path):
    """The declared errors cover every permitted input, so no postcondition is ever exercised."""
    doc = contract_doc(X, pre=["x >= 0"], post=["result > 100"], errors=[{"exception": "ValueError", "when": "x >= 0"}])
    assert any(sev == "error" for sev in findings(doc).values()), findings(doc)


def test_compare_precondition_strengthening_is_an_error():
    old = contract_doc(X, pre=["x >= 0"], post=["result >= 0"])
    new = contract_doc(X, pre=["x >= 1"], post=["result >= 0"])
    assert comparison(old, new).get("PRECONDITION_STRENGTHENED") == "error"


def test_compare_weakened_precondition_must_keep_invariant():
    old = contract_doc(X, pre=["x >= 0"], inv=["result >= 0"], post=["result == x"])
    dropped = contract_doc(X, post=["result == x"])
    kept = contract_doc(X, post=["result == abs(x)"], inv=["result >= 0"])
    got = comparison(old, dropped)
    assert got.get("PRECONDITION_WEAKENED") == "info" and got.get("INVARIANT_NOT_RETAINED") == "error", got
    assert all(s != "error" for s in comparison(old, kept).values()), comparison(old, kept)


def test_compare_approval_for_one_scope_does_not_cover_another():
    old = contract_doc(X, pre=["x >= 0"], inv=["result >= 0"], post=["result == x"])
    new = contract_doc(X, pre=["x >= 1"], post=["result == x - 5"],
                       approved_change={"reason": "callers never pass 0", "scope": ["preconditions"]})
    got = comparison(old, new)
    assert got.get("PRECONDITION_STRENGTHENED") == "info"
    assert got.get("INVARIANT_NOT_RETAINED") == "error", got


def test_compare_weakened_postcondition_and_dropped_error():
    old = contract_doc(X, post=["result >= x"], errors=[{"exception": "ValueError", "when": "x < -100"}])
    new = contract_doc(X, post=["result >= x - 1"])
    got = comparison(old, new)
    assert got.get("POSTCONDITION_NOT_RETAINED") == "error" and got.get("ERROR_NOT_RETAINED") == "error", got


def test_compare_signature_change_is_not_text_compared():
    old = contract_doc(X, post=["result >= 0"])
    new = contract_doc({"y": "int"}, post=["result >= 0"])
    assert comparison(old, new) == {"COMPARISON_UNSUPPORTED": "error"}


def test_check_contracts_against_cli_exit(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    write_contract(tmp_path / "old", contract_doc(X, pre=["x >= 0"], post=["result >= 0"]))
    write_contract(tmp_path / "new", contract_doc(X, pre=["x >= 5"], post=["result >= 0"]))
    rc, out = cli("check-contracts", tmp_path / "new", "--against", tmp_path / "old")
    assert rc == gate.EXIT_CONTRACT_REVIEW and "PRECONDITION_STRENGTHENED" in out, out


# ------------------------------------------------------------------ (3) gate failure semantics
def _verify(tmp_path, src, doc, *extra, pre=""):
    if src is not None:
        write_module(tmp_path, src)
    c = write_contract(tmp_path, doc)
    return cli("verify", c, "--root", tmp_path, "--report", tmp_path / "r.json", *extra, pre=pre)


def test_z3_missing_fails_closed(tmp_path):
    block = "import sys\nsys.modules['z3'] = None\n"
    rc, out = _verify(tmp_path, GOOD, contract_doc(X, post=["result >= 0"]), pre=block)
    assert rc == gate.EXIT_Z3_MISSING and "Z3_MISSING" in out, out
    rc, out = cli("check-contracts", tmp_path / "c.yaml", pre=block)
    assert rc == gate.EXIT_Z3_MISSING, out


def test_broken_z3_is_a_crash_not_a_pass(tmp_path):
    """Fail closed with the documented crash code and a written report, not an uncaught traceback (exit 1)."""
    rc, out = _verify(tmp_path, GOOD, contract_doc(X, post=["result >= 0"]),
                      pre="import z3\ndef _boom(*a, **k):\n    raise RuntimeError('broken z3')\nz3.Solver = _boom\n")
    assert rc in (gate.EXIT_CRASH, gate.EXIT_Z3_MISSING), (rc, out)
    assert json.loads((tmp_path / "r.json").read_text())["passed"] is False


@pytest.mark.parametrize("label,src,doc,code,needle", [
    ("missing_function", "def g(x: int) -> int:\n    return x\n", contract_doc(X, post=["result >= 0"]), 11, "no function"),
    ("syntax_error", "def f(x: int) -> int\n    return x\n", contract_doc(X, post=["result >= 0"]), 11, "syntax error"),
    ("missing_module", None, contract_doc(X, post=["result >= 0"], symbol="nosuchmod_acc:f"), 11, "nosuchmod_acc"),
    ("import_time_error", "raise RuntimeError('boom at import')\ndef f(x: int) -> int:\n    return x\n",
     contract_doc(X, post=["result >= 0"]), 11, "importing failed"),
    ("param_mismatch", "def f(y: int) -> int:\n    return y\n", contract_doc(X, post=["result >= 0"]), 11, "differ"),
    ("unsupported_unrouted", "def f(x: int) -> int:\n    while x > 0:\n        x -= 1\n    return x\n",
     contract_doc(X, post=["result >= 0"]), 12, "loops"),
    ("model_mismatch", "def abs(v):\n    return v\n\n\ndef f(x: int) -> int:\n    return abs(x)\n",
     contract_doc(X, post=["result >= 0"]), 13, "MODEL_MISMATCH"),
    ("counterexample", "def f(x: int) -> int:\n    return x\n", contract_doc(X, post=["result >= 0"]), 16, "COUNTEREXAMPLE"),
    ("review_error", GOOD, contract_doc(X, post=["result == result"]), 17, "VACUOUS_POSTCONDITION"),
])
def test_each_failure_fails_closed_with_reason(tmp_path, label, src, doc, code, needle):
    rc, out = _verify(tmp_path, src, doc)
    assert rc == code and needle in out, (label, rc, out)
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["passed"] is False and report["reasons"], report


def test_predicate_naming_unknown_symbol_is_a_usage_failure(tmp_path):
    rc, out = _verify(tmp_path, GOOD, contract_doc(X, post=["result >= y"]))
    assert rc == gate.EXIT_USAGE and "free variable" in out, out


def test_no_contracts_fails(tmp_path):
    (tmp_path / "empty").mkdir()
    rc, out = cli("verify", tmp_path / "empty", "--root", tmp_path)
    assert rc == gate.EXIT_USAGE, out


def test_solver_timeout_fails_the_gate(tmp_path):
    src = "def f(x: int, y: int, z: int) -> int:\n    return x * x * x + y * y * y - z * z * z\n"
    doc = contract_doc({"x": "int", "y": "int", "z": "int"}, pre=["x > 0", "y > 0", "z > 0"], post=["result != 0"])
    rc, out = _verify(tmp_path, src, doc, "--timeout-ms", "1")
    assert rc in (gate.EXIT_TIMEOUT, gate.EXIT_UNKNOWN), (rc, out)


def test_exit_codes_are_distinct_per_failure_class():
    codes = [gate.EXIT_Z3_MISSING, gate.EXIT_CRASH, gate.EXIT_UNSUPPORTED_UNROUTED, gate.EXIT_MODEL_MISMATCH,
             gate.EXIT_UNKNOWN, gate.EXIT_TIMEOUT, gate.EXIT_COUNTEREXAMPLE, gate.EXIT_CONTRACT_REVIEW, gate.EXIT_VACUOUS]
    assert len(set(codes)) == len(codes) and 0 not in codes and gate.EXIT_USAGE not in codes


def test_routed_unsupported_is_visible_not_proved(tmp_path):
    src = "def f(x: int) -> int:\n    while x > 0:\n        x -= 1\n    return x\n"
    rc, out = _verify(tmp_path, src, contract_doc(X, post=["result >= 0"], route={"default": "property"}))
    report = json.loads((tmp_path / "r.json").read_text())
    obs = report["contracts"][0]["obligations"]
    assert rc == 0 and all(o["verdict"] == "UNSUPPORTED" and o["route"]["method"] == "property" for o in obs), obs


SIGNATURE_MISMATCH = {"return_type_mismatch": "def f(x: int) -> bool:\n    return x > 0\n",
                      "unannotated_extra_param": "def f(x, y):\n    return x\n"}


@pytest.mark.parametrize("label", sorted(SIGNATURE_MISMATCH))
def test_signature_mismatch_cannot_be_routed_away(tmp_path, label):
    """Skill: exit 11 is 'signature mismatch'. A route to tests must not hide that the contract names the wrong shape."""
    rc, out = _verify(tmp_path, SIGNATURE_MISMATCH[label], contract_doc(X, post=["result >= 0"], route={"default": "test"}))
    assert rc != 0, f"{label}: signature mismatch passed the gate via a route: {out}"


# ------------------------------------------------------------------ (4) patch rejection demo
BASE = ("def clamp(x: int, lo: int, hi: int) -> int:\n"
        "    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n")
HEAD = ("def clamp(x: int, lo: int, hi: int) -> int:\n"
        "    if x < lo:\n        return lo\n    if x > hi + 1:  # 'simplified' bound\n        return hi\n    return x\n")
CLAMP = contract_doc({"x": "int", "lo": "int", "hi": "int"}, pre=["lo <= hi"], symbol="accmod:clamp",
                     inv=[{"id": "inv-in-range", "expr": "lo <= result <= hi"}],
                     post=["(lo <= x <= hi) == (result == x)"])


def _plausible_unit_test(clamp):
    assert clamp(5, 0, 10) == 5 and clamp(-3, 0, 10) == 0 and clamp(99, 0, 10) == 10 and clamp(0, 0, 0) == 0


def test_patch_that_passes_unit_test_but_breaks_invariant_is_rejected(tmp_path):
    for src in (BASE, HEAD):
        ns: dict = {}
        exec(src, ns)
        _plausible_unit_test(ns["clamp"])
    base_dir, head_dir = tmp_path / "base", tmp_path / "head"
    base_dir.mkdir()
    head_dir.mkdir()
    rc, out = _verify(base_dir, BASE, CLAMP)
    assert rc == 0, out
    rc, out = _verify(head_dir, HEAD, CLAMP, "--regress-dir", head_dir / "regress")
    assert rc == gate.EXIT_COUNTEREXAMPLE and "inv-in-range" in out, out
    ce = [o for o in json.loads((head_dir / "r.json").read_text())["contracts"][0]["obligations"]
          if o["id"] == "inv-in-range"][0]["counterexample"]["inputs"]
    assert ce["x"] == ce["hi"] + 1
    # the generated regression fails on the head and passes once the base code is restored
    regs = sorted((head_dir / "regress").glob("test_regress_*inv_in_range*.py"))
    assert regs, list((head_dir / "regress").iterdir())
    with pytest.raises(AssertionError):
        runpy.run_path(str(regs[0]))["test_counterexample_is_fixed"]()
    (head_dir / "accmod.py").write_text(BASE, encoding="utf-8")
    runpy.run_path(str(regs[0]))["test_counterexample_is_fixed"]()


# ------------------------------------------------------------------ (6) no PROVED without a solver result
VERIFY_DIR = REPO / "factory" / "verify"


def _proved_producers():
    """Functions in factory/verify that construct PROVED (not just compare with it)."""
    out = set()
    for f in sorted(VERIFY_DIR.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for n in ast.walk(tree):
            hit = (isinstance(n, ast.Attribute) and n.attr == "PROVED" and isinstance(parents.get(n), (ast.Call, ast.keyword))) or \
                  (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Verdict") or \
                  (isinstance(n, ast.Constant) and n.value == "PROVED" and not isinstance(parents.get(n), ast.Assign))
            if hit:
                p = n
                while p in parents and not isinstance(p, ast.FunctionDef):
                    p = parents[p]
                out.add(f"{f.name}:{getattr(p, 'name', '<module>')}")
    return out


def test_only_the_unsat_path_and_the_cache_produce_proved():
    assert _proved_producers() == {"solve.py:_prove_from_unsat", "solve.py:from_dict"}, _proved_producers()


def test_prove_from_unsat_refuses_non_unsat():
    ob = solve.Obligation("post-1", "post", "result >= 0")
    with pytest.raises(AssertionError):
        solve._prove_from_unsat(ob, solve.Query("sat"), solve.Query("sat"), None)
    with pytest.raises(AssertionError):
        solve._prove_from_unsat(ob, solve.Query("unsat"), solve.Query("unsat"), None)
    with pytest.raises(AssertionError):
        solve._prove_from_unsat(ob, solve.Query("unsat"), solve.Query("sat"), solve.Query("unsat"))


@pytest.mark.parametrize("mod", ["solve.py", "irgen.py", "consistency.py", "gate.py", "contracts.py", "ir.py"])
def test_verdict_modules_import_no_text_matching(mod):
    tree = ast.parse((VERIFY_DIR / mod).read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & {"re", "difflib", "fnmatch"}, names
