"""Obligation discharge with z3 and mandatory replay of counterexamples.

Verdicts: PROVED, COUNTEREXAMPLE, UNSUPPORTED, UNKNOWN, TIMEOUT, MODEL_MISMATCH.

The only way to obtain PROVED is ``_prove_from_unsat``, which requires the
solver to have answered ``unsat`` on ``P AND T_impl AND NOT Q`` *and* the
non-vacuity checks (P satisfiable, relevant paths reachable) to have passed.
There is no regex, text-equality or syntactic fallback anywhere in this module;
tests enforce that by inspecting this file.
"""

from __future__ import annotations

import importlib
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from . import ir, irgen, replay
from .contracts import Contract, INT64_MAX, INT64_MIN
from .ir import BOOL, INT, Unsupported


class SolverUnavailable(Exception):
    """z3 could not be imported.  A required verifier that is missing fails the gate."""


class ExtractionError(Exception):
    """The implementation does not match the contract signature (a gate failure, not UNSUPPORTED)."""


class Verdict(str, Enum):
    PROVED = "PROVED"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    MODEL_MISMATCH = "MODEL_MISMATCH"


def require_z3():
    try:
        return importlib.import_module("z3")
    except ImportError as e:
        raise SolverUnavailable(f"z3 is required but cannot be imported: {e}") from e


def z3_version() -> str:
    return require_z3().get_version_string()


@dataclass
class Obligation:
    id: str
    kind: str  # post | inv | err | undeclared
    text: str
    clause: Any = None
    declared_method: Optional[str] = None


@dataclass
class ObligationResult:
    id: str
    kind: str
    text: str
    verdict: Verdict
    reason: str = ""
    route: Optional[dict] = None
    counterexample: Optional[dict] = None
    replay: Optional[dict] = None
    vacuous: bool = False

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["verdict"] = self.verdict.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "ObligationResult":
        d = dict(d)
        d["verdict"] = Verdict(d["verdict"])
        return ObligationResult(**d)


IMPLICIT_ASSUMPTIONS = [
    "Parameters have exactly the int/bool types annotated; no other types reach the function.",
    "The function is pure and terminates (supported subset has no loops or calls).",
    "abs/min/max and the exception class names are the Python builtins (not shadowed).",
    "Exceptions are matched by class name.",
    "Predicates are evaluated over the original argument values; old(x) equals x for a pure function.",
    "Predicate sub-expressions that fault (e.g. division by zero) make the predicate false.",
    "z3 answers are trusted; every COUNTEREXAMPLE is replayed against the real code and every PROVED "
    "obligation is cross-checked on sampled inputs, but PROVED is not a machine-checked proof certificate.",
]
SEMANTIC_ASSUMPTIONS = {
    "math_int": "math_int: int arithmetic is unbounded mathematical integers (matches Python ints).",
    "int64": "int64: parameters are in [-2^63, 2^63-1]; any arithmetic result outside that range is an "
             "OverflowError outcome (checked arithmetic, not wraparound).",
}


@dataclass
class ContractResult:
    contract_id: str
    symbol: str
    semantics: str
    obligations: List[ObligationResult] = field(default_factory=list)
    precondition_satisfiable: Optional[bool] = None
    translation_unsupported: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    cache_hit: bool = False


def obligations_of(contract: Contract) -> List[Obligation]:
    obs = [Obligation(c.id, "post", c.text, c, c.check_method) for c in contract.postconditions]
    obs += [Obligation(c.id, "inv", c.text, c, c.check_method) for c in contract.invariants]
    obs += [Obligation(e.id, "err", f"{e.exception} when {e.when_text}", e, e.check_method) for e in contract.errors]
    obs.append(Obligation("no-undeclared-errors", "undeclared",
                          "the function raises only declared exceptions, only under their stated conditions"))
    return obs


def route_for(contract: Contract, ob_id: str) -> Optional[dict]:
    r = contract.route.get(ob_id, contract.route.get("default"))
    if r is None:
        return None
    return dict(r) if isinstance(r, dict) else {"method": r}


# ---------------------------------------------------------------- solver glue
@dataclass
class Query:
    status: str  # 'sat' | 'unsat' | 'unknown'
    model: Any = None
    reason: str = ""


def _query(z3, formulas, timeout_ms: int) -> Query:
    s = z3.Solver()
    s.set("timeout", int(timeout_ms))
    for f in formulas:
        s.add(f)
    r = s.check()
    if r == z3.sat:
        return Query("sat", s.model())
    if r == z3.unsat:
        return Query("unsat")
    return Query("unknown", reason=str(s.reason_unknown()))


def _unknown_verdict(q: Query) -> Verdict:
    low = q.reason.lower()
    return Verdict.TIMEOUT if ("timeout" in low or "canceled" in low) else Verdict.UNKNOWN


def _prove_from_unsat(ob: Obligation, violation: Query, p_sat: Query, relevance: Optional[Query]) -> ObligationResult:
    """The single producer of PROVED.  Requires an unsat violation query and non-vacuity."""
    assert violation.status == "unsat" and p_sat.status == "sat"
    assert relevance is None or relevance.status == "sat"
    return ObligationResult(ob.id, ob.kind, ob.text, Verdict.PROVED,
                            "solver proved P AND T_impl AND NOT Q unsatisfiable; P and relevant paths satisfiable")


def _model_args(z3, model, params) -> Dict[str, Any]:
    out = {}
    for name, ty in params:
        v = model.eval(z3.Int(name) if ty == INT else z3.Bool(name), model_completion=True)
        out[name] = v.as_long() if ty == INT else bool(z3.is_true(v))
    return out


# ------------------------------------------------------- python-side oracle
def violated(contract: Contract, ob: Obligation, args: Dict[str, Any], outcome: replay.Outcome) -> bool:
    """Does the *real* outcome on ``args`` violate the obligation (Python semantics)?"""
    if not all(replay.holds(p.expr, args) for p in contract.preconditions):
        return False
    if ob.kind in ("post", "inv"):
        return outcome.kind == "return" and not replay.holds(ob.clause.expr, args, outcome.value)
    if ob.kind == "err":
        return replay.holds(ob.clause.when, args) and not (outcome.kind == "raise" and outcome.exc == ob.clause.exception)
    declared = any(replay.holds(e.when, args) and outcome.exc == e.exception for e in contract.errors)
    return outcome.kind == "raise" and not declared


def _sample_inputs(contract: Contract, extra: List[Dict[str, Any]], n: int = 200) -> List[Dict[str, Any]]:
    rng = random.Random(0xC0FFEE)
    hi = INT64_MAX if contract.semantics == "int64" else 10**6
    pool = [-3, -2, -1, 0, 1, 2, 3, 7, -7, 10, 100, -100]
    if contract.semantics == "int64":
        pool += [INT64_MAX, INT64_MIN, INT64_MAX - 1, INT64_MIN + 1, 2**32, -(2**32)]
    out = list(extra)
    for _ in range(n):
        args = {}
        for name, ty in contract.params:
            if ty == BOOL:
                args[name] = rng.random() < 0.5
            else:
                args[name] = rng.choice(pool) if rng.random() < 0.6 else rng.randint(-hi, hi) if hi < 10**7 else rng.randint(INT64_MIN, INT64_MAX)
        out.append(args)
    return out


def _enumerate_models(z3, base, params, count: int, timeout_ms: int) -> List[Dict[str, Any]]:
    s = z3.Solver()
    s.set("timeout", int(timeout_ms))
    s.add(base)
    out = []
    while len(out) < count and s.check() == z3.sat:
        args = _model_args(z3, s.model(), params)
        out.append(args)
        s.add(z3.Or(*[(z3.Int(n) if t == INT else z3.Bool(n)) != args[n] for n, t in params]))
    return out


# --------------------------------------------------------------- main entry
def verify_contract(contract: Contract, target, *, timeout_ms: int = 5000, sample_check: bool = True) -> ContractResult:
    """Verify every obligation of ``contract`` against the real ``target`` implementation."""
    z3 = require_z3()
    res = ContractResult(contract.contract_id, contract.symbol, contract.semantics)
    res.assumptions = list(contract.assumptions) + [SEMANTIC_ASSUMPTIONS[contract.semantics]] + IMPLICIT_ASSUMPTIONS
    obligations = obligations_of(contract)
    solver_obs: List[Obligation] = []
    for ob in obligations:
        method = ob.declared_method or contract.check_method
        if method != "solver":
            res.obligations.append(ObligationResult(
                ob.id, ob.kind, ob.text, Verdict.UNSUPPORTED,
                f"declared check_method={method}; the solver does not discharge this obligation",
                route={"method": method}))
        else:
            solver_obs.append(ob)
    if not solver_obs:
        return res

    def unsupported_all(reason: str):
        res.translation_unsupported = reason
        for ob in solver_obs:
            res.obligations.append(ObligationResult(ob.id, ob.kind, ob.text, Verdict.UNSUPPORTED, reason,
                                                    route=route_for(contract, ob.id)))
        return res

    if contract.state_scope != "pure":
        return unsupported_all(f"state_scope is {contract.state_scope!r}; the solver verifies pure functions only")
    try:
        func = irgen.parse_function(target.node, contract.returns)
    except Unsupported as e:
        return unsupported_all(e.reason)
    if dict(func.params) != dict(contract.params):
        raise ExtractionError(f"{contract.symbol}: function parameters {list(func.params)} differ from contract params {list(contract.params)}")

    env, dom = irgen.make_params(z3, contract.params, contract.semantics)
    try:
        paths = irgen.execute(z3, func, env, contract.semantics)
    except Unsupported as e:
        return unsupported_all(e.reason)

    # contract-side predicates (mathematical, faults make a predicate false)

    def pred(expr, result=None):
        t = irgen.Translator(z3, checked=False, result=result)
        v, f = t.expr(expr, env)
        return z3.And(irgen.defined(z3, f), v)

    P = z3.And(dom, *[pred(p.expr) for p in contract.preconditions])
    p_sat = _query(z3, [P], timeout_ms)
    if p_sat.status != "unsat":
        res.precondition_satisfiable = True if p_sat.status == "sat" else None
    else:
        res.precondition_satisfiable = False
    ret_paths = [p for p in paths if p.kind == "return"]
    raise_paths = [p for p in paths if p.kind == "raise"]
    result_sort = z3.Int("result") if contract.returns == INT else z3.Bool("result")

    proved: List[Tuple[Obligation, ObligationResult]] = []
    for ob in solver_obs:
        if p_sat.status == "unknown":
            res.obligations.append(ObligationResult(ob.id, ob.kind, ob.text, _unknown_verdict(p_sat),
                                                    f"could not decide whether the precondition is satisfiable: {p_sat.reason}"))
            continue
        if p_sat.status == "unsat":
            res.obligations.append(ObligationResult(
                ob.id, ob.kind, ob.text, Verdict.UNKNOWN,
                "VACUOUS: the precondition is unsatisfiable, so nothing is verified", vacuous=True))
            continue
        relevance_f = None
        if ob.kind in ("post", "inv"):
            q = pred(ob.clause.expr, result_sort)
            t_impl = z3.Or(*[z3.And(p.cond, result_sort == p.value) for p in ret_paths]) if ret_paths else z3.BoolVal(False)
            violation_f = z3.And(P, t_impl, z3.Not(q))
            relevance_f = z3.And(P, z3.Or(*[p.cond for p in ret_paths])) if ret_paths else z3.BoolVal(False)
        elif ob.kind == "err":
            w = pred(ob.clause.when)
            raising = z3.Or(*[p.cond for p in raise_paths if p.exc == ob.clause.exception]) if any(
                p.exc == ob.clause.exception for p in raise_paths) else z3.BoolVal(False)
            violation_f = z3.And(P, w, z3.Not(raising))
            relevance_f = z3.And(P, w)
        else:
            bad = []
            for p in raise_paths:
                declared = [pred(e.when) for e in contract.errors if e.exception == p.exc]
                bad.append(z3.And(p.cond, z3.Not(z3.Or(*declared)) if declared else z3.BoolVal(True)))
            violation_f = z3.And(P, z3.Or(*bad)) if bad else z3.BoolVal(False)
        rel_q = None
        if relevance_f is not None:
            rel_q = _query(z3, [relevance_f], timeout_ms)
            if rel_q.status == "unknown":
                res.obligations.append(ObligationResult(ob.id, ob.kind, ob.text, _unknown_verdict(rel_q),
                                                        f"could not decide path reachability: {rel_q.reason}"))
                continue
            if rel_q.status == "unsat":
                what = "no return path is reachable under the precondition" if ob.kind in ("post", "inv") \
                    else "the error condition can never hold under the precondition"
                res.obligations.append(ObligationResult(ob.id, ob.kind, ob.text, Verdict.UNKNOWN,
                                                        f"VACUOUS: {what}", vacuous=True))
                continue
        vq = _query(z3, [violation_f], timeout_ms)
        if vq.status == "unknown":
            res.obligations.append(ObligationResult(ob.id, ob.kind, ob.text, _unknown_verdict(vq),
                                                    f"solver gave no answer: {vq.reason}"))
        elif vq.status == "unsat":
            r = _prove_from_unsat(ob, vq, p_sat, rel_q)
            res.obligations.append(r)
            proved.append((ob, r))
        else:
            args = _model_args(z3, vq.model, contract.params)
            outcome = replay.call_target(target, args, contract.semantics)
            if violated(contract, ob, args, outcome):
                res.obligations.append(ObligationResult(
                    ob.id, ob.kind, ob.text, Verdict.COUNTEREXAMPLE,
                    "solver model replayed on the real implementation and violates the obligation",
                    counterexample={"inputs": args}, replay={"outcome": outcome.as_dict(), "reproduced": True}))
            else:
                res.obligations.append(ObligationResult(
                    ob.id, ob.kind, ob.text, Verdict.MODEL_MISMATCH,
                    "z3 reported a counterexample that the real implementation does not exhibit "
                    "(translator or semantics bug); the gate fails",
                    counterexample={"inputs": args}, replay={"outcome": outcome.as_dict(), "reproduced": False}))

    if proved and sample_check:
        extra = _enumerate_models(z3, P, contract.params, 8, timeout_ms)
        for args in _sample_inputs(contract, extra):
            outcome = None
            for ob, r in proved:
                if r.verdict is not Verdict.PROVED:
                    continue
                if outcome is None:
                    outcome = replay.call_target(target, args, contract.semantics)
                if violated(contract, ob, args, outcome):
                    r.verdict = Verdict.MODEL_MISMATCH
                    r.reason = ("z3 reported PROVED but the real implementation violates the obligation on a "
                                "sampled input (translator or semantics bug); the gate fails")
                    r.counterexample = {"inputs": args}
                    r.replay = {"outcome": outcome.as_dict(), "reproduced": True}
    return res
