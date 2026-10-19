"""Contract file format (YAML) and loader.

A contract is an independent, executable statement of *intended* behaviour for
one symbol.  ``observed`` notes about current code live in their own section and
are never parsed into obligations.  See skills/contract-verify/SKILL.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .ir import TYPES, Unsupported, mentions_result, parse_predicate

CHECK_METHODS = ("solver", "property", "test", "integration", "e2e", "telemetry")
SEMANTICS = ("math_int", "int64")
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1

_TOP_REQUIRED = (
    "contract_id", "requirement_ids", "symbol", "state_scope", "semantics", "check_method",
    "concurrency", "frame", "params", "returns", "intended",
)
_TOP_OPTIONAL = ("assumptions", "route", "observed", "approved_change", "description")
_INTENDED_KEYS = ("preconditions", "postconditions", "errors", "invariants")
_APPROVAL_SCOPES = ("preconditions", "postconditions", "invariants", "errors", "frame",
                    "concurrency", "semantics", "signature")


class ContractError(Exception):
    """The contract file is malformed or uses a predicate outside the language."""


@dataclass(frozen=True)
class Clause:
    id: str
    kind: str  # pre | post | inv
    text: str
    expr: Any
    check_method: Optional[str] = None


@dataclass(frozen=True)
class ErrorClause:
    id: str
    exception: str
    when_text: str
    when: Any
    check_method: Optional[str] = None


@dataclass
class Contract:
    contract_id: str
    requirement_ids: List[str]
    symbol: str
    state_scope: str
    semantics: str
    check_method: str
    concurrency: Any
    frame: List[str]
    params: Tuple[Tuple[str, str], ...]
    returns: str
    preconditions: List[Clause]
    postconditions: List[Clause]
    errors: List[ErrorClause]
    invariants: List[Clause]
    assumptions: List[str] = field(default_factory=list)
    route: Dict[str, Any] = field(default_factory=dict)
    observed: Any = None
    approved_change: Optional[dict] = None
    source_path: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def module_name(self) -> str:
        return self.symbol.split(":", 1)[0]

    @property
    def qualname(self) -> str:
        return self.symbol.split(":", 1)[1]

    @property
    def scope(self) -> Dict[str, str]:
        return dict(self.params)

    def obligation_clauses(self) -> List[Any]:
        return list(self.postconditions) + list(self.invariants) + list(self.errors)

    def content_hash(self) -> str:
        """Hash of everything that can affect a verdict (``observed`` is excluded)."""
        doc = {k: v for k, v in self.raw.items() if k not in ("observed", "description")}
        return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()


def _fail(src: str, msg: str):
    raise ContractError(f"{src}: {msg}")


def _check_id(src: str, cid: Any):
    ok = (isinstance(cid, str) and "-" in cid and cid[0].isalpha() and len(cid) >= 3
          and all(c.isalnum() or c in "-._" for c in cid))
    if not ok:
        _fail(src, f"contract_id {cid!r} must look like 'C-CLAMP-001' (letters/digits/-._, with a dash)")


def _method(src: str, m: Any, where: str) -> Optional[str]:
    if m is None:
        return None
    if m not in CHECK_METHODS:
        _fail(src, f"{where}: check_method {m!r} not in {list(CHECK_METHODS)}")
    return m


def _pred(src: str, text: Any, scope: Dict[str, str], result_ty: str, where: str):
    if not isinstance(text, str) or not text.strip():
        _fail(src, f"{where}: predicate must be a non-empty string")
    try:
        return parse_predicate(text, scope, result_ty)
    except Unsupported as e:
        _fail(src, f"{where}: predicate {text!r} rejected: {e.reason}")


def _clauses(src, items, kind, scope, result_ty) -> List[Clause]:
    out = []
    for i, it in enumerate(items or [], 1):
        where = f"intended.{kind}[{i}]"
        if isinstance(it, str):
            cid, text, cm = f"{kind}-{i}", it, None
        elif isinstance(it, dict):
            extra = set(it) - {"id", "expr", "check_method"}
            if extra or "expr" not in it:
                _fail(src, f"{where}: expected keys id/expr/check_method, got {sorted(it)}")
            cid, text, cm = str(it.get("id", f"{kind}-{i}")), it["expr"], _method(src, it.get("check_method"), where)
        else:
            _fail(src, f"{where}: must be a string or mapping")
        out.append(Clause(cid, kind, text, _pred(src, text, scope, result_ty, where), cm))
    return out


def parse_contract(doc: Any, source: str = "<contract>") -> Contract:
    if not isinstance(doc, dict):
        _fail(source, "top level must be a mapping")
    missing = [k for k in _TOP_REQUIRED if k not in doc]
    if missing:
        _fail(source, f"missing required keys: {missing}")
    unknown = set(doc) - set(_TOP_REQUIRED) - set(_TOP_OPTIONAL)
    if unknown:
        _fail(source, f"unknown keys: {sorted(unknown)}")
    _check_id(source, doc["contract_id"])
    reqs = doc["requirement_ids"]
    if not (isinstance(reqs, list) and reqs and all(isinstance(r, str) and r for r in reqs)):
        _fail(source, "requirement_ids must be a non-empty list of strings")
    sym = doc["symbol"]
    if not (isinstance(sym, str) and sym.count(":") == 1 and all(sym.split(":"))):
        _fail(source, "symbol must be 'module:qualname'")
    if not isinstance(doc["state_scope"], str) or not doc["state_scope"]:
        _fail(source, "state_scope must be a non-empty string ('pure' for the solver)")
    if doc["semantics"] not in SEMANTICS:
        _fail(source, f"semantics must be one of {list(SEMANTICS)}")
    method = _method(source, doc["check_method"], "check_method")
    if method is None:
        _fail(source, "check_method is required")
    conc = doc["concurrency"]
    if conc in (None, "", [], {}):
        _fail(source, "concurrency must be stated explicitly (use 'none' if there is none)")
    frame = doc["frame"]
    if frame == "nothing":
        frame = []
    if not (isinstance(frame, list) and all(isinstance(f, str) for f in frame)):
        _fail(source, "frame must be 'nothing' or a list of state names that may change")
    if doc["state_scope"] == "pure" and frame:
        _fail(source, "a pure contract cannot declare changeable state in frame")
    params = doc["params"]
    if not (isinstance(params, dict) and all(isinstance(k, str) and v in TYPES for k, v in params.items())):
        _fail(source, f"params must map names to one of {list(TYPES)}")
    if "result" in params:
        _fail(source, "a parameter cannot be named 'result'")
    if doc["returns"] not in TYPES:
        _fail(source, f"returns must be one of {list(TYPES)}")
    intended = doc["intended"]
    if not isinstance(intended, dict) or set(intended) - set(_INTENDED_KEYS):
        _fail(source, f"intended must be a mapping with keys from {list(_INTENDED_KEYS)}")
    scope, rty = dict(params), doc["returns"]
    pre = _clauses(source, intended.get("preconditions"), "pre", scope, rty)
    post = _clauses(source, intended.get("postconditions"), "post", scope, rty)
    inv = _clauses(source, intended.get("invariants"), "inv", scope, rty)
    errs = []
    for i, e in enumerate(intended.get("errors") or [], 1):
        where = f"intended.errors[{i}]"
        if not (isinstance(e, dict) and "exception" in e and "when" in e and not set(e) - {"id", "exception", "when", "check_method"}):
            _fail(source, f"{where}: expected keys exception/when (and optional id/check_method)")
        exc = e["exception"]
        if not (isinstance(exc, str) and exc.isidentifier()):
            _fail(source, f"{where}: exception must be a class name")
        errs.append(ErrorClause(str(e.get("id", f"err-{exc}")), exc, e["when"],
                                _pred(source, e["when"], scope, rty, where + ".when"),
                                _method(source, e.get("check_method"), where)))
    # result cannot appear in preconditions or error conditions
    for p in pre:
        if mentions_result(p.expr):
            _fail(source, f"precondition {p.text!r} may not mention result")
    for e in errs:
        if mentions_result(e.when):
            _fail(source, f"error condition {e.when_text!r} may not mention result")
    if not (post or inv or errs):
        _fail(source, "a contract with no postconditions, invariants or errors has no obligations")
    ids = [c.id for c in post + inv + errs]
    if len(set(ids)) != len(ids):
        _fail(source, f"obligation ids must be unique, got {ids}")
    route = doc.get("route") or {}
    if not isinstance(route, dict):
        _fail(source, "route must be a mapping obligation-id (or 'default') -> check method")
    for k, v in route.items():
        m = v.get("method") if isinstance(v, dict) else v
        if m == "solver" or m not in CHECK_METHODS:
            _fail(source, f"route[{k!r}] must name a non-solver check method, got {m!r}")
        if k != "default" and k not in ids and k != "no-undeclared-errors":
            _fail(source, f"route names unknown obligation {k!r}")
    approved = doc.get("approved_change")
    if approved is not None:
        if not (isinstance(approved, dict) and isinstance(approved.get("reason"), str) and approved["reason"].strip()):
            _fail(source, "approved_change requires a non-empty 'reason'")
        bad = [s for s in approved.get("scope", []) if s not in _APPROVAL_SCOPES]
        if bad:
            _fail(source, f"approved_change.scope has unknown entries {bad}; allowed {list(_APPROVAL_SCOPES)}")
    assumptions = doc.get("assumptions") or []
    if not (isinstance(assumptions, list) and all(isinstance(a, str) for a in assumptions)):
        _fail(source, "assumptions must be a list of strings")
    return Contract(
        contract_id=doc["contract_id"], requirement_ids=list(reqs), symbol=sym,
        state_scope=doc["state_scope"], semantics=doc["semantics"], check_method=method,
        concurrency=conc, frame=list(frame), params=tuple(params.items()), returns=rty,
        preconditions=pre, postconditions=post, errors=errs, invariants=inv,
        assumptions=list(assumptions), route=dict(route), observed=doc.get("observed"),
        approved_change=approved, source_path=source if source != "<contract>" else None, raw=doc,
    )


def load_contract_text(text: str, source: str = "<contract>") -> Contract:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        _fail(source, f"invalid YAML: {e}")
    return parse_contract(doc, source)


def load_contract(path) -> Contract:
    p = Path(path)
    return load_contract_text(p.read_text(encoding="utf-8"), str(p))


def load_contracts(paths) -> List[Contract]:
    """Load files and/or directories (``*.yaml``/``*.yml``; ``RETIRED.yaml`` skipped)."""
    out: List[Contract] = []
    for raw in paths:
        p = Path(raw)
        files = sorted(f for f in p.rglob("*") if f.suffix in (".yaml", ".yml") and f.name != "RETIRED.yaml") if p.is_dir() else [p]
        if p.is_dir() and not files:
            raise ContractError(f"{p}: directory contains no contract files")
        out.extend(load_contract(f) for f in files)
    return out


def check_ids(contracts: List[Contract], retired_ids: Optional[List[str]] = None) -> List[str]:
    """Return problems with contract_id stability: duplicates, or reuse of a retired id."""
    problems, seen = [], {}
    for c in contracts:
        if c.contract_id in seen:
            problems.append(f"contract_id {c.contract_id} is used by both {seen[c.contract_id]} and {c.source_path}")
        seen[c.contract_id] = c.source_path
        if retired_ids and c.contract_id in retired_ids:
            problems.append(f"contract_id {c.contract_id} is retired and must never be reused ({c.source_path})")
    return problems


def load_retired(path) -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(doc.get("retired", []))
