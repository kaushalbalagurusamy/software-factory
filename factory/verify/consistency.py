"""Contract review before code, and old/new contract comparison.

Everything here is decided by z3 over the contract predicates; nothing compares
predicate *text*.  When two contracts cannot be compared semantically (for
example the signature changed), the report says ``COMPARISON_UNSUPPORTED``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import irgen
from .contracts import Contract
from .ir import INT
from .solve import require_z3

TIMEOUT_MS = 5000


@dataclass
class Finding:
    code: str
    severity: str  # error | info
    message: str
    obligation: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ReviewReport:
    contract_id: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def as_dict(self) -> dict:
        return {"contract_id": self.contract_id, "ok": self.ok, "findings": [f.as_dict() for f in self.findings]}


class _Z:
    """z3 helper bound to one parameter environment."""

    def __init__(self, params, semantics_list):
        self.z3 = require_z3()
        self.params = params
        self.env, _ = irgen.make_params(self.z3, params, "math_int")
        self.result_int = self.z3.Int("result")
        self.result_bool = self.z3.Bool("result")

    def dom(self, semantics: str):
        return irgen.make_params(self.z3, self.params, semantics)[1]

    def pred(self, expr, returns):
        z3 = self.z3
        t = irgen.Translator(z3, checked=False, result=self.result_int if returns == INT else self.result_bool)
        v, f = t.expr(expr, self.env)
        return z3.And(irgen.defined(z3, f), v)

    def P(self, c: Contract):
        return self.z3.And(self.dom(c.semantics), *[self.pred(p.expr, c.returns) for p in c.preconditions])

    def Q(self, c: Contract, with_inv=True):
        cl = list(c.postconditions) + (list(c.invariants) if with_inv else [])
        return [self.pred(x.expr, c.returns) for x in cl]

    def any_error(self, c: Contract):
        z3 = self.z3
        return z3.Or(*[self.pred(e.when, c.returns) for e in c.errors]) if c.errors else z3.BoolVal(False)

    def sat(self, *formulas):
        z3 = self.z3
        s = z3.Solver()
        s.set("timeout", TIMEOUT_MS)
        for f in formulas:
            s.add(f)
        r = s.check()
        if r == z3.sat:
            return "sat", s.model()
        return ("unsat", None) if r == z3.unsat else ("unknown", None)

    def inputs(self, model):
        z3 = self.z3
        out = {}
        for n, t in self.params:
            v = model.eval(self.env[n], model_completion=True)
            out[n] = v.as_long() if t == INT else bool(z3.is_true(v))
        return out


def _unknown(rep: ReviewReport, what: str, obligation=None):
    rep.findings.append(Finding("ANALYSIS_UNKNOWN", "error", f"solver could not decide: {what}", obligation))


def review_contract(c: Contract) -> ReviewReport:
    """Review a single contract before any code exists."""
    rep = ReviewReport(c.contract_id)
    z = _Z(c.params, None)
    z3 = z.z3
    P = z.P(c)
    st, _ = z.sat(P)
    if st == "unknown":
        _unknown(rep, "precondition satisfiability")
        return rep
    if st == "unsat":
        rep.findings.append(Finding(
            "PRECONDITION_UNSATISFIABLE", "error",
            "the preconditions (with the semantics' parameter domain) admit no input, so every postcondition "
            "would hold vacuously"))
        return rep
    clauses = list(c.postconditions) + list(c.invariants)
    for cl in clauses:
        q = z.pred(cl.expr, c.returns)
        st, _ = z.sat(z3.Not(q))
        if st == "unknown":
            _unknown(rep, "validity of a postcondition", cl.id)
        elif st == "unsat":
            rep.findings.append(Finding("VACUOUS_POSTCONDITION", "error",
                                        f"{cl.id} ({cl.text!r}) is valid on its own: it constrains nothing", cl.id))
            continue
        st, _ = z.sat(P, z3.Not(q))
        if st == "unknown":
            _unknown(rep, "implication by precondition", cl.id)
        elif st == "unsat":
            rep.findings.append(Finding("VACUOUS_POSTCONDITION", "error",
                                        f"{cl.id} ({cl.text!r}) is implied by the precondition alone for every result: "
                                        "it constrains nothing about the implementation", cl.id))
    if clauses:
        st, _ = z.sat(P, *[z.pred(cl.expr, c.returns) for cl in clauses])
        if st == "unsat":
            rep.findings.append(Finding("POSTCONDITIONS_CONTRADICTORY", "error",
                                        "no result can satisfy all postconditions and invariants together under the preconditions"))
        elif st == "unknown":
            _unknown(rep, "joint satisfiability of postconditions")
    for e in c.errors:
        st, _ = z.sat(P, z.pred(e.when, c.returns))
        if st == "unsat":
            rep.findings.append(Finding("ERROR_CONDITION_UNREACHABLE", "error",
                                        f"{e.id}: condition {e.when_text!r} can never hold under the preconditions", e.id))
        elif st == "unknown":
            _unknown(rep, "error condition reachability", e.id)
    for i, a in enumerate(c.errors):
        for b in c.errors[i + 1:]:
            if a.exception == b.exception:
                continue
            st, m = z.sat(P, z.pred(a.when, c.returns), z.pred(b.when, c.returns))
            if st == "sat":
                rep.findings.append(Finding("ERROR_CONDITIONS_OVERLAP", "error",
                                            f"{a.id} and {b.id} can both apply to the same input; which exception is raised is ambiguous",
                                            a.id, {"example": z.inputs(m)}))
    return rep


# --------------------------------------------------------------- comparison
def _approval(new: Contract, scope: str) -> Optional[str]:
    a = new.approved_change
    if a and scope in (a.get("scope") or []):
        return a["reason"]
    return None


def _flag(rep: ReviewReport, new: Contract, scope: str, code: str, message: str, obligation=None, detail=None):
    reason = _approval(new, scope)
    if reason:
        rep.findings.append(Finding(code, "info", f"{message} -- approved_change: {reason}", obligation, detail or {}))
    else:
        rep.findings.append(Finding(code, "error", message, obligation, detail or {}))


def compare_contracts(old: Contract, new: Contract) -> ReviewReport:
    """Is ``new`` an acceptable successor of ``old``?  Unapproved weakening/loss is an error."""
    rep = ReviewReport(new.contract_id)
    if old.contract_id != new.contract_id:
        rep.findings.append(Finding("CONTRACT_ID_CHANGED", "error",
                                    f"contract_id changed from {old.contract_id} to {new.contract_id}; ids are stable and never reused"))
    if dict(old.params) != dict(new.params) or old.returns != new.returns:
        _flag(rep, new, "signature", "COMPARISON_UNSUPPORTED",
              f"signature changed ({dict(old.params)} -> {old.returns} vs {dict(new.params)} -> {new.returns}); "
              "predicates over different parameters cannot be compared semantically, and text comparison is not proof")
        return rep
    if old.semantics != new.semantics:
        _flag(rep, new, "semantics", "SEMANTICS_CHANGED", f"integer semantics changed from {old.semantics} to {new.semantics}")
    if old.concurrency != new.concurrency:
        _flag(rep, new, "concurrency", "CONCURRENCY_CHANGED",
              f"concurrency scope changed ({old.concurrency!r} -> {new.concurrency!r}); declared scopes are opaque "
              "labels, so any change needs explicit approval (semantic comparison unsupported)")
    widened = sorted(set(new.frame) - set(old.frame))
    if widened or (old.state_scope == "pure" and new.state_scope != "pure"):
        _flag(rep, new, "frame", "FRAME_WIDENED",
              f"the frame (what may change) grew: new state {widened or [new.state_scope]} "
              "(identifier-level comparison; semantic frame comparison is unsupported)")
    z = _Z(new.params, None)
    z3 = z.z3
    Po, Pn = z.P(old), z.P(new)
    Wo, Wn = z.any_error(old), z.any_error(new)

    st, m = z.sat(Po, z3.Not(Pn))
    if st == "unknown":
        _unknown(rep, "precondition compatibility")
    elif st == "sat":
        _flag(rep, new, "preconditions", "PRECONDITION_STRENGTHENED",
              "the new precondition rejects inputs the old contract permitted (breaks callers)",
              detail={"counterexample": z.inputs(m)})
    st, m = z.sat(Pn, z3.Not(Po))
    if st == "sat":
        rep.findings.append(Finding(
            "PRECONDITION_WEAKENED", "info",
            "the new precondition admits inputs the old one excluded; every retained invariant and postcondition "
            "must hold there (checked below)", detail={"example": z.inputs(m)}))

    common = [Po, Pn, z3.Not(Wo), z3.Not(Wn)]
    new_q = z.Q(new)
    for cl in old.postconditions:
        st, m = z.sat(*common, *new_q, z3.Not(z.pred(cl.expr, old.returns)))
        if st == "unknown":
            _unknown(rep, "postcondition retention", cl.id)
        elif st == "sat":
            _flag(rep, new, "postconditions", "POSTCONDITION_NOT_RETAINED",
                  f"old postcondition {cl.id} ({cl.text!r}) is not implied by the new contract on inputs both permit",
                  cl.id, {"counterexample": z.inputs(m)})
    for cl in old.invariants:
        st, m = z.sat(Pn, z3.Not(Wn), *new_q, z3.Not(z.pred(cl.expr, old.returns)))
        if st == "unknown":
            _unknown(rep, "invariant retention", cl.id)
        elif st == "sat":
            _flag(rep, new, "invariants", "INVARIANT_NOT_RETAINED",
                  f"old invariant {cl.id} ({cl.text!r}) can be violated under the new contract (a guard protecting it was weakened or dropped)",
                  cl.id, {"counterexample": z.inputs(m)})
    for e in old.errors:
        same = [z.pred(n.when, new.returns) for n in new.errors if n.exception == e.exception]
        covered = z3.Or(*same) if same else z3.BoolVal(False)
        st, m = z.sat(Po, Pn, z.pred(e.when, old.returns), z3.Not(covered))
        if st == "unknown":
            _unknown(rep, "error retention", e.id)
        elif st == "sat":
            _flag(rep, new, "errors", "ERROR_NOT_RETAINED",
                  f"{e.exception} (when {e.when_text!r}) is no longer guaranteed on inputs both contracts permit",
                  e.id, {"counterexample": z.inputs(m)})
    st, m = z.sat(Po, Pn, z3.Not(Wo), Wn)
    if st == "sat":
        _flag(rep, new, "errors", "ERROR_ADDED",
              "the new contract raises on inputs where the old contract returned normally",
              detail={"counterexample": z.inputs(m)})
    return rep
