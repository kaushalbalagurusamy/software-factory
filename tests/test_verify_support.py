"""Shared helpers for the verify tests (no tests here)."""

from pathlib import Path

from factory.verify.contracts import parse_contract
from factory.verify.loader import load_target

FIXTURES = Path(__file__).parent / "fixtures" / "verify"


def make(symbol="impls_good:clamp", params=None, returns="int", pre=(), post=(), errors=(), inv=(),
         semantics="math_int", method="solver", cid="C-TEST-001", **extra):
    doc = {
        "contract_id": cid, "requirement_ids": ["REQ-1"], "symbol": symbol, "state_scope": "pure",
        "semantics": semantics, "check_method": method, "concurrency": "none", "frame": "nothing",
        "params": params or {"x": "int", "lo": "int", "hi": "int"}, "returns": returns,
        "intended": {"preconditions": list(pre), "postconditions": list(post),
                     "errors": list(errors), "invariants": list(inv)},
    }
    doc.update(extra)
    return parse_contract(doc, "<test>")


def target_for(contract, root=FIXTURES):
    return load_target(contract.symbol, roots=[root])


def clamp_contract(symbol="impls_good:clamp", **kw):
    return make(symbol, pre=["lo <= hi"],
                post=["result >= lo", "result <= hi", "x < lo or x > hi or result == x"], **kw)


def verdicts(result):
    return {o.id: o.verdict.value for o in result.obligations}
