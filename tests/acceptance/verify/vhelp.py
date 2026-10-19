"""Shared helpers for the independent acceptance tests of factory.verify.

The brute-force oracle here is written from the spec (docs/verification-ir.md section 3), not from
factory/verify/replay.py: it executes the real module with plain Python and evaluates the contract
predicate text with Python's own eval.
"""
from __future__ import annotations

import copy
import itertools
from pathlib import Path

from factory.verify import gate
from factory.verify.contracts import parse_contract

INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
SMALL = range(-6, 7)


def contract_doc(params, returns="int", pre=(), post=(), inv=(), errors=(), semantics="math_int",
                 symbol="accmod:f", **extra):
    doc = {
        "contract_id": "C-ACC-001", "requirement_ids": ["R-ACC-1"], "symbol": symbol,
        "state_scope": "pure", "semantics": semantics, "check_method": "solver", "concurrency": "none",
        "frame": "nothing", "params": dict(params), "returns": returns,
        "intended": {"preconditions": list(pre), "postconditions": list(post), "invariants": list(inv),
                     "errors": [dict(e) for e in errors]},
    }
    doc.update(extra)
    return doc


def write_module(dirpath: Path, src: str, name: str = "accmod") -> Path:
    p = Path(dirpath) / f"{name}.py"
    p.write_text(src, encoding="utf-8")
    return p


def run_gate(tmp_path, src, doc, *, review=True, cache=None, name="accmod", **kw):
    write_module(tmp_path, src, name)
    c = parse_contract(copy.deepcopy(doc), str(tmp_path / "contract.yaml"))
    rep = gate.run_gate([c], roots=[str(tmp_path)], cache_path=cache, review=review, **kw)
    return rep


def verdicts(rep) -> dict:
    out = {}
    for c in rep.contracts:
        for o in c.get("obligations", []):
            out[o["id"]] = o
    return out


# ------------------------------------------------------------------ independent oracle
def real_function(path: Path, name="f"):
    ns: dict = {"__name__": "acc_oracle"}
    exec(compile(Path(path).read_text(encoding="utf-8"), str(path), "exec"), ns)
    return ns[name]


def pred(text, args, result=None) -> bool:
    env = {"__builtins__": {"abs": abs, "min": min, "max": max, "True": True, "False": False},
           "old": lambda v: v}
    local = dict(args)
    if result is not None:
        local["result"] = result
    try:  # eval of contract predicate text written by these tests, with a minimal builtins table
        return bool(eval(text, env, local))
    except ZeroDivisionError:
        return False


def outcome(fn, args, int64=False):
    try:
        r = fn(**args)
    except Exception as e:  # noqa: BLE001 - the exception is the outcome
        return ("raise", type(e).__name__)
    if int64 and isinstance(r, int) and not isinstance(r, bool) and not INT64_MIN <= r <= INT64_MAX:
        return ("raise", "OverflowError")
    return ("return", r)


def _texts(doc):
    i = doc["intended"]
    return ([p if isinstance(p, str) else p["expr"] for p in i.get("preconditions", [])],
            i.get("errors", []))


def clause_text(doc, ob_id):
    i = doc["intended"]
    for kind, key in (("post", "postconditions"), ("inv", "invariants")):
        for n, c in enumerate(i.get(key, []), 1):
            cid = c.get("id", f"{kind}-{n}") if isinstance(c, dict) else f"{kind}-{n}"
            if cid == ob_id:
                return kind, (c["expr"] if isinstance(c, dict) else c)
    for e in i.get("errors", []):
        if e.get("id", f"err-{e['exception']}") == ob_id:
            return "err", e
    if ob_id == "no-undeclared-errors":
        return "undeclared", None
    raise KeyError(ob_id)


def violates(doc, ob_id, args, out) -> bool:
    pres, errs = _texts(doc)
    if not all(pred(p, args) for p in pres):
        return False
    kind, c = clause_text(doc, ob_id)
    if kind in ("post", "inv"):
        return out[0] == "return" and not pred(c, args, out[1])
    if kind == "err":
        return pred(c["when"], args) and out != ("raise", c["exception"])
    if out[0] != "raise":
        return False
    return not any(out[1] == e["exception"] and pred(e["when"], args) for e in errs)


def domain(params, ints=SMALL):
    names = list(params)
    vals = [list(ints) if params[n] == "int" else [False, True] for n in names]
    for combo in itertools.product(*vals):
        yield dict(zip(names, combo))


def assert_consistent(tmp_path, src, doc, expect=None, ints=SMALL, int64=False):
    """Every PROVED must survive brute force; every COUNTEREXAMPLE must reproduce on real Python.

    ``expect`` maps obligation id -> expected verdict (keeps the case meaningful).
    Returns the verdict map.
    """
    rep = run_gate(tmp_path, src, doc)
    vs = verdicts(rep)
    fn = real_function(tmp_path / "accmod.py")
    problems = []
    for oid, o in vs.items():
        bad = [a for a in domain(doc["params"], ints) if violates(doc, oid, a, outcome(fn, a, int64))]
        if o["verdict"] == "PROVED" and bad:
            problems.append(f"CRITICAL unsound PROVED: {oid} violated by real Python on {bad[:3]}")
        if o["verdict"] == "COUNTEREXAMPLE":
            a = o["counterexample"]["inputs"]
            if not violates(doc, oid, a, outcome(fn, a, int64)):
                problems.append(f"CRITICAL non-reproducing COUNTEREXAMPLE: {oid} at {a} -> {outcome(fn, a, int64)}")
    assert not problems, problems
    if expect:
        got = {k: vs[k]["verdict"] for k in expect}
        assert got == expect, (got, {k: vs[k].get("reason") for k in expect})
    return rep, vs
