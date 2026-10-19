"""Gate: run contracts against implementations and fail closed.

Every outcome other than a discharged (PROVED) or visibly *routed* obligation
fails the gate with a distinct non-zero exit code and a reason.  Nothing is
classified as harmless: a missing z3, a crash while extracting or translating,
an unrouted UNSUPPORTED obligation, MODEL_MISMATCH, UNKNOWN or TIMEOUT all fail.
"""

from __future__ import annotations

import hashlib
import json
import platform
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .consistency import review_contract
from .contracts import Contract, check_ids
from .loader import BindingError, LoadError, Target, load_target
from .solve import (ContractResult, ExtractionError, ObligationResult, SolverUnavailable, Verdict, obligations_of,
                    z3_version, verify_contract)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_Z3_MISSING = 10
EXIT_CRASH = 11
EXIT_UNSUPPORTED_UNROUTED = 12
EXIT_MODEL_MISMATCH = 13
EXIT_UNKNOWN = 14
EXIT_TIMEOUT = 15
EXIT_COUNTEREXAMPLE = 16
EXIT_CONTRACT_REVIEW = 17
EXIT_VACUOUS = 18
EXIT_BINDING = 19

_CODE_TO_EXIT = {
    "USAGE": EXIT_USAGE, "Z3_MISSING": EXIT_Z3_MISSING, "CRASH": EXIT_CRASH,
    "UNSUPPORTED_UNROUTED": EXIT_UNSUPPORTED_UNROUTED, "MODEL_MISMATCH": EXIT_MODEL_MISMATCH,
    "UNKNOWN": EXIT_UNKNOWN, "TIMEOUT": EXIT_TIMEOUT, "COUNTEREXAMPLE": EXIT_COUNTEREXAMPLE,
    "CONTRACT_REVIEW": EXIT_CONTRACT_REVIEW, "VACUOUS": EXIT_VACUOUS, "BINDING": EXIT_BINDING,
}
# most severe first: this decides the single process exit code; all reasons are still listed
_PRIORITY = ["Z3_MISSING", "CRASH", "BINDING", "MODEL_MISMATCH", "COUNTEREXAMPLE", "CONTRACT_REVIEW", "VACUOUS",
             "UNSUPPORTED_UNROUTED", "TIMEOUT", "UNKNOWN", "USAGE"]


@dataclass
class GateReport:
    reasons: List[dict] = field(default_factory=list)
    contracts: List[dict] = field(default_factory=list)
    tool_versions: Dict[str, Any] = field(default_factory=dict)
    results: List[Tuple[Contract, Optional[Target], Optional[ContractResult]]] = field(default_factory=list, repr=False)

    def add(self, code: str, message: str, contract_id: Optional[str] = None, obligation: Optional[str] = None):
        self.reasons.append({"code": code, "contract_id": contract_id, "obligation": obligation, "message": message})

    @property
    def exit_code(self) -> int:
        present = {r["code"] for r in self.reasons}
        for code in _PRIORITY:
            if code in present:
                return _CODE_TO_EXIT[code]
        return EXIT_OK

    @property
    def passed(self) -> bool:
        return self.exit_code == EXIT_OK

    def as_dict(self) -> dict:
        return {"passed": self.passed, "exit_code": self.exit_code, "reasons": self.reasons,
                "tool_versions": self.tool_versions, "contracts": self.contracts}


def tool_versions() -> Dict[str, Any]:
    try:
        z = z3_version()
    except SolverUnavailable:
        z = None
    return {"python": platform.python_version(), "z3": z, "factory_verify": __version__}


# ---------------------------------------------------------------- cache
def cache_key(contract: Contract, target: Target, assumptions: List[str], versions: dict) -> str:
    doc = {"impl": target.impl_hash, "deps": target.dep_hashes, "module": target.module_hash, "contract": contract.content_hash(),
           "z3": versions["z3"], "python": versions["python"], "tool": versions["factory_verify"],
           "assumptions": sorted(assumptions)}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def _load_cache(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            return data
    except (OSError, ValueError):
        pass  # unreadable or corrupt: treated as empty, never trusted
    return {"entries": {}}


def _result_to_dict(r: ContractResult) -> dict:
    return {"obligations": [dict(o.as_dict(), cached=False) for o in r.obligations],
            "precondition_satisfiable": r.precondition_satisfiable,
            "translation_unsupported": r.translation_unsupported}


def _cacheable(r: ContractResult) -> bool:
    return all(o.verdict is Verdict.PROVED or (o.verdict is Verdict.UNSUPPORTED and o.route is not None)
               for o in r.obligations)


# ------------------------------------------------------------------ run
def _obligation_reasons(rep: GateReport, cid: str, r: ContractResult):
    for o in r.obligations:
        if o.verdict is Verdict.PROVED:
            continue
        if o.verdict is Verdict.UNSUPPORTED:
            if o.route is None:
                rep.add("UNSUPPORTED_UNROUTED", f"{o.reason}; no route to another check is declared", cid, o.id)
        elif o.verdict is Verdict.COUNTEREXAMPLE:
            rep.add("COUNTEREXAMPLE", f"{o.text!r} violated for inputs {o.counterexample['inputs']} "
                    f"(real outcome {o.replay['outcome']})", cid, o.id)
        elif o.verdict is Verdict.MODEL_MISMATCH:
            rep.add("MODEL_MISMATCH", o.reason, cid, o.id)
        elif o.verdict is Verdict.TIMEOUT:
            rep.add("TIMEOUT", o.reason, cid, o.id)
        elif o.vacuous:
            rep.add("VACUOUS", o.reason, cid, o.id)
        else:
            rep.add("UNKNOWN", o.reason, cid, o.id)


def run_gate(contracts: List[Contract], *, roots=(), source_files: Optional[Dict[str, Any]] = None,
             timeout_ms: int = 5000, cache_path=None, retired_ids: Optional[List[str]] = None,
             review: bool = True, sample_check: bool = True) -> GateReport:
    rep = GateReport()
    rep.tool_versions = tool_versions()
    if not contracts:
        rep.add("USAGE", "no contracts given; an empty gate cannot pass")
        return rep
    if rep.tool_versions["z3"] is None:
        rep.add("Z3_MISSING", "z3 is required for verification and cannot be imported; this is a gate failure, "
                "not a harmless refactor")
        return rep
    for problem in check_ids(contracts, retired_ids):
        rep.add("CONTRACT_REVIEW", problem)
    cache = _load_cache(cache_path) if cache_path else None
    dirty = False
    for c in contracts:
        entry: Dict[str, Any] = {"contract_id": c.contract_id, "symbol": c.symbol, "semantics": c.semantics,
                                 "requirement_ids": c.requirement_ids, "cache_hit": False}
        rep.contracts.append(entry)
        try:
            src = (source_files or {}).get(c.symbol)
            target = load_target(c.symbol, roots=roots, source_file=src)
        except BindingError as e:
            rep.add(e.code, f"refusing to verify: {e}", c.contract_id)
            entry["error"] = str(e)
            verdict = Verdict.MODEL_MISMATCH if e.code == "MODEL_MISMATCH" else Verdict.UNKNOWN
            entry["obligations"] = [ObligationResult(o.id, o.kind, o.text, verdict, f"{e.code}: {e}").as_dict()
                                    for o in obligations_of(c)]
            rep.results.append((c, None, None))
            continue
        except Exception as e:  # noqa: BLE001 - reported as a gate failure, not swallowed
            rep.add("CRASH", f"could not load implementation: {type(e).__name__}: {e}", c.contract_id)
            entry["error"] = str(e)
            rep.results.append((c, None, None))
            continue
        entry["hashes"] = {"implementation": target.impl_hash, "dependencies": target.dep_hashes,
                           "contract": c.content_hash()}
        entry["source_file"] = target.file
        entry["module_hash"] = target.module_hash
        if review:
            try:
                rr = review_contract(c)
            except SolverUnavailable as e:
                rep.add("Z3_MISSING", str(e), c.contract_id)
                return rep
            except Exception as e:  # noqa: BLE001 - e.g. a broken z3 at run time: crash, not a traceback
                rep.add("CRASH", f"contract review crashed: {type(e).__name__}: {e}", c.contract_id)
                entry["error"] = traceback.format_exc(limit=3)
                rep.results.append((c, target, None))
                continue
            entry["review"] = rr.as_dict()
            for f in rr.findings:
                if f.severity == "error":
                    rep.add("CONTRACT_REVIEW", f"{f.code}: {f.message}", c.contract_id, f.obligation)
        from .solve import IMPLICIT_ASSUMPTIONS, SEMANTIC_ASSUMPTIONS
        assumptions = list(c.assumptions) + [SEMANTIC_ASSUMPTIONS[c.semantics]] + IMPLICIT_ASSUMPTIONS
        key = cache_key(c, target, assumptions, rep.tool_versions)
        result: Optional[ContractResult] = None
        if cache is not None and key in cache["entries"]:
            try:
                d = cache["entries"][key]
                obs = [ObligationResult.from_dict(o) for o in d["obligations"]]
                for o in obs:
                    o.cached = True  # reported as "PROVED (cached)"; a cache file is not evidence of a fresh proof
                result = ContractResult(c.contract_id, c.symbol, c.semantics, obs,
                                        d["precondition_satisfiable"], d["translation_unsupported"], assumptions, True)
            except (KeyError, TypeError, ValueError):
                result = None  # malformed entry: recompute
        if result is None:
            try:
                result = verify_contract(c, target, timeout_ms=timeout_ms, sample_check=sample_check)
            except SolverUnavailable as e:
                rep.add("Z3_MISSING", str(e), c.contract_id)
                rep.results.append((c, target, None))
                return rep
            except Exception as e:  # noqa: BLE001
                rep.add("CRASH", f"verification crashed: {type(e).__name__}: {e}", c.contract_id)
                entry["error"] = traceback.format_exc(limit=3)
                rep.results.append((c, target, None))
                continue
            if cache is not None and _cacheable(result):
                cache["entries"][key] = _result_to_dict(result)
                dirty = True
        entry.update({"cache_hit": result.cache_hit, "assumptions": result.assumptions,
                      "precondition_satisfiable": result.precondition_satisfiable,
                      "translation_unsupported": result.translation_unsupported,
                      "obligations": [o.as_dict() for o in result.obligations]})
        rep.results.append((c, target, result))
        _obligation_reasons(rep, c.contract_id, result)
    if cache is not None and dirty:
        Path(cache_path).write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return rep
