import pytest

from factory.verify import consistency as cons
from test_verify_support import make


def codes(report, severity=None):
    return {f.code for f in report.findings if severity in (None, f.severity)}


def test_clean_contract_has_no_findings():
    c = make(pre=["lo <= hi"], post=["result >= lo", "result <= hi"])
    r = cons.review_contract(c)
    assert r.ok and not r.findings


def test_unsatisfiable_precondition_flagged():
    c = make("impls_good:my_abs", {"x": "int"}, pre=["x > 0 and x < 0"], post=["result >= 0"])
    r = cons.review_contract(c)
    assert "PRECONDITION_UNSATISFIABLE" in codes(r, "error") and not r.ok


def test_unsatisfiable_through_multiple_clauses():
    c = make("impls_good:my_abs", {"x": "int"}, pre=["x > 5", "x < 3"], post=["result >= 0"])
    assert "PRECONDITION_UNSATISFIABLE" in codes(cons.review_contract(c))


def test_int64_domain_makes_precondition_unsatisfiable():
    c = make("impls_good:my_abs", {"x": "int"}, pre=["x > 9223372036854775807"], post=["result >= 0"], semantics="int64")
    assert "PRECONDITION_UNSATISFIABLE" in codes(cons.review_contract(c))


def test_contradictory_postconditions_flagged():
    c = make("impls_good:my_abs", {"x": "int"}, post=["result > x", "result < x"])
    assert "POSTCONDITIONS_CONTRADICTORY" in codes(cons.review_contract(c), "error")


def test_postcondition_contradicting_precondition_alone():
    c = make("impls_good:my_abs", {"x": "int"}, pre=["x > 0"], post=["result < 0 and x > 0 and result > 0"])
    assert "POSTCONDITIONS_CONTRADICTORY" in codes(cons.review_contract(c))


def test_tautological_postcondition_is_vacuous():
    c = make("impls_good:my_abs", {"x": "int"}, post=["result >= 0", "result == result", "x >= 0 or x < 0"])
    r = cons.review_contract(c)
    vac = [f for f in r.findings if f.code == "VACUOUS_POSTCONDITION"]
    assert {f.obligation for f in vac} == {"post-2", "post-3"}
    assert all(f.severity == "error" for f in vac)


def test_postcondition_implied_by_precondition_alone_is_vacuous():
    c = make("impls_good:my_abs", {"x": "int"}, pre=["x > 0"], post=["x >= 0", "result >= 0"])
    r = cons.review_contract(c)
    vac = [f for f in r.findings if f.code == "VACUOUS_POSTCONDITION"]
    assert [f.obligation for f in vac] == ["post-1"]
    assert "precondition alone" in vac[0].message


def test_vacuous_invariant():
    c = make("impls_good:my_abs", {"x": "int"}, post=["result >= 0"], inv=["x == x"])
    assert "VACUOUS_POSTCONDITION" in codes(cons.review_contract(c))


def test_overlapping_error_conditions_ambiguous():
    c = make("impls_good:safe_div", {"a": "int", "b": "int"},
             errors=[{"exception": "ValueError", "when": "b <= 0"}, {"exception": "ZeroDivisionError", "when": "b == 0"}],
             post=["result == a // b"])
    assert "ERROR_CONDITIONS_OVERLAP" in codes(cons.review_contract(c), "error")


def test_dead_error_condition_flagged():
    c = make("impls_good:safe_div", {"a": "int", "b": "int"}, pre=["b > 0"],
             errors=[{"exception": "ZeroDivisionError", "when": "b == 0"}], post=["result == a // b"])
    assert "ERROR_CONDITION_UNREACHABLE" in codes(cons.review_contract(c))


# ----------------------------------------------------------- old vs new
def pair(old_pre, new_pre, old_post=("result >= 0",), new_post=("result >= 0",), old_inv=(), new_inv=(), new_extra=None):
    kw = dict(symbol="impls_good:my_abs", params={"x": "int"})
    old = make(pre=old_pre, post=old_post, inv=old_inv, **kw)
    new = make(pre=new_pre, post=new_post, inv=new_inv, **(new_extra or {}), **kw)
    return old, new


def test_identical_contracts_compatible():
    old, new = pair(["x > 0"], ["x > 0"])
    assert cons.compare_contracts(old, new).ok


def test_precondition_strengthened_breaks_callers():
    old, new = pair(["x > -10"], ["x > 0"])
    r = cons.compare_contracts(old, new)
    f = [f for f in r.findings if f.code == "PRECONDITION_STRENGTHENED"]
    assert f and f[0].severity == "error" and not r.ok
    assert f[0].detail["counterexample"]["x"] <= 0 and f[0].detail["counterexample"]["x"] > -10


def test_precondition_strengthened_with_approval_is_accepted():
    old, new = pair(["x > -10"], ["x > 0"], new_extra={"approved_change": {"reason": "negative prices were never valid", "scope": ["preconditions"]}})
    r = cons.compare_contracts(old, new)
    f = [f for f in r.findings if f.code == "PRECONDITION_STRENGTHENED"]
    assert f and f[0].severity == "info" and "negative prices" in f[0].message
    assert r.ok


def test_approval_without_matching_scope_does_not_cover():
    old, new = pair(["x > -10"], ["x > 0"], new_extra={"approved_change": {"reason": "because", "scope": ["frame"]}})
    assert not cons.compare_contracts(old, new).ok


def test_precondition_weakened_must_retain_invariant():
    # dropping the x > 0 guard lets result == x go negative, breaking the old invariant
    old, new = pair(["x > 0"], [], old_post=["result > 0"], new_post=["result == x"], old_inv=["result >= 0"], new_inv=[])
    r = cons.compare_contracts(old, new)
    assert "INVARIANT_NOT_RETAINED" in codes(r, "error")
    assert "PRECONDITION_WEAKENED" in codes(r, "info")


def test_precondition_weakened_with_retained_guarantees_is_fine():
    old, new = pair(["x > 0"], [], old_post=["result > 0"], new_post=["result >= 0", "x <= 0 or result > 0"],
                    old_inv=["result >= 0"], new_inv=["result >= 0"])
    r = cons.compare_contracts(old, new)
    assert r.ok, [f.message for f in r.findings]
    assert "PRECONDITION_WEAKENED" in codes(r, "info")


def test_weakened_precondition_old_postcondition_not_implied():
    old, new = pair(["x > 0"], [], old_post=["result > 0"], new_post=["result >= 0"])
    assert "POSTCONDITION_NOT_RETAINED" in codes(cons.compare_contracts(old, new), "error")


def test_postcondition_dropped_flagged():
    old, new = pair([], [], old_post=["result >= 0", "result == x or result == -x"], new_post=["result >= 0"])
    r = cons.compare_contracts(old, new)
    f = [f for f in r.findings if f.code == "POSTCONDITION_NOT_RETAINED"]
    assert [x.obligation for x in f] == ["post-2"] and not r.ok


def test_postcondition_strengthened_ok():
    old, new = pair([], [], old_post=["result >= 0"], new_post=["result >= 0", "result >= x"])
    assert cons.compare_contracts(old, new).ok


def test_error_dropped_flagged():
    kw = dict(symbol="impls_good:safe_div", params={"a": "int", "b": "int"})
    old = make(errors=[{"exception": "ZeroDivisionError", "when": "b == 0"}], post=["result == a // b"], **kw)
    new = make(post=["result == a // b"], **kw)
    assert "ERROR_NOT_RETAINED" in codes(cons.compare_contracts(old, new), "error")


def test_frame_widened_and_concurrency_changed_flagged():
    old, new = pair([], [])
    new.state_scope = "stateful"
    new.frame = ["balances"]
    new.concurrency = "single writer under lock L"
    c = codes(cons.compare_contracts(old, new), "error")
    assert {"FRAME_WIDENED", "CONCURRENCY_CHANGED"} <= c


def test_semantics_change_flagged():
    old, new = pair([], [])
    new.semantics = "int64"
    assert "SEMANTICS_CHANGED" in codes(cons.compare_contracts(old, new), "error")


def test_signature_change_is_unsupported_comparison_not_text_equality():
    old = make("impls_good:my_abs", {"x": "int"}, pre=["x > 0"], post=["result >= 0"])
    new = make("impls_good:my_abs", {"x": "int", "y": "int"}, pre=["x > 0"], post=["result >= 0"])
    r = cons.compare_contracts(old, new)
    f = [f for f in r.findings if f.code == "COMPARISON_UNSUPPORTED"]
    assert f and "signature" in f[0].message and not r.ok


def test_contract_id_must_match():
    old, new = pair([], [])
    new.contract_id = "C-OTHER-001"
    assert "CONTRACT_ID_CHANGED" in codes(cons.compare_contracts(old, new), "error")


def test_textually_different_but_equivalent_preconditions_are_compatible():
    old, new = pair(["x > 0"], ["x >= 1"])
    assert cons.compare_contracts(old, new).ok  # semantic, not textual


def test_textually_identical_symbol_but_semantically_stronger_is_caught():
    old, new = pair(["x * 2 > 0"], ["x * 2 > 10"])
    assert "PRECONDITION_STRENGTHENED" in codes(cons.compare_contracts(old, new))
