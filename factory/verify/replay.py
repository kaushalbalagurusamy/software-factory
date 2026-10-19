"""Independent Python-semantics oracle used to replay and cross-check z3 results.

Nothing here uses z3.  ``eval_expr`` interprets contract IR with real Python
integer semantics; ``call_target`` executes the real function (for int64, a copy
of its AST whose arithmetic is wrapped in a range check, still real Python).
"""

from __future__ import annotations

import ast
import builtins
import copy
from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import ir

INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1


class Undefined(Exception):
    """A predicate could not be evaluated (e.g. division by zero)."""


@dataclass
class Outcome:
    kind: str  # 'return' | 'raise'
    value: Any = None
    exc: Optional[str] = None

    def as_dict(self):
        return {"kind": self.kind, "value": self.value, "exc": self.exc}


def eval_expr(e, args: Dict[str, Any], result: Any = None):
    ev = lambda x: eval_expr(x, args, result)  # noqa: E731
    if isinstance(e, ir.Const):
        return e.value
    if isinstance(e, ir.Var):
        return args[e.name]
    if isinstance(e, ir.Old):
        return args[e.name]
    if isinstance(e, ir.Result):
        return result
    if isinstance(e, ir.Unary):
        a = ev(e.a)
        return (not a) if e.op == "not" else (-a if e.op == "neg" else a)
    if isinstance(e, ir.Bin):
        a, b = ev(e.a), ev(e.b)
        if e.op in ("floordiv", "mod") and b == 0:
            raise Undefined("division by zero in predicate")
        return {"add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b,
                "floordiv": lambda: a // b, "mod": lambda: a % b}[e.op]()
    if isinstance(e, ir.Cmp):
        a, b = ev(e.a), ev(e.b)
        return {"eq": a == b, "ne": a != b, "lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[e.op]
    if isinstance(e, ir.BoolOp):
        if e.op == "and":
            for o in e.operands:
                if not ev(o):
                    return False
            return True
        for o in e.operands:
            if ev(o):
                return True
        return False
    if isinstance(e, ir.IfExp):
        return ev(e.a) if ev(e.test) else ev(e.b)
    if isinstance(e, ir.Call):
        return {"abs": abs, "min": min, "max": max}[e.fn](*[ev(x) for x in e.args])
    raise TypeError(f"unknown IR node {e!r}")


def holds(expr, args, result=None) -> bool:
    """A predicate holds only if it evaluates (without fault) to true."""
    try:
        return bool(eval_expr(expr, args, result))
    except Undefined:
        return False


def _chk(v):
    if isinstance(v, int) and not isinstance(v, bool) and not INT64_MIN <= v <= INT64_MAX:
        raise OverflowError("int64 overflow")
    return v


class _Checked(ast.NodeTransformer):
    def visit_BinOp(self, n):
        self.generic_visit(n)
        return ast.copy_location(ast.Call(ast.Name("__chk", ast.Load()), [n], []), n)

    def visit_UnaryOp(self, n):
        self.generic_visit(n)
        if isinstance(n.op, ast.USub):
            return ast.copy_location(ast.Call(ast.Name("__chk", ast.Load()), [n], []), n)
        return n

    def visit_Call(self, n):
        self.generic_visit(n)
        if isinstance(n.func, ast.Name) and n.func.id == "abs":
            return ast.copy_location(ast.Call(ast.Name("__chk", ast.Load()), [n], []), n)
        return n

    def visit_AugAssign(self, n):
        self.generic_visit(n)
        target = ast.Name(n.target.id, ast.Load())
        val = ast.Call(ast.Name("__chk", ast.Load()), [ast.BinOp(target, n.op, n.value)], [])
        return ast.copy_location(ast.Assign([ast.Name(n.target.id, ast.Store())], val), n)


def checked_callable(node: ast.FunctionDef):
    """Compile a copy of the function with int64 range checks on arithmetic."""
    fn = copy.deepcopy(node)
    fn.decorator_list = []
    fn = _Checked().visit(fn)
    mod = ast.fix_missing_locations(ast.Module([fn], []))
    ns: Dict[str, Any] = {"__chk": _chk, "__builtins__": builtins}
    exec(compile(mod, "<int64-replay>", "exec"), ns)
    return ns[fn.name]


def call_target(target, args: Dict[str, Any], semantics: str) -> Outcome:
    """Run the real implementation on concrete inputs."""
    fn = checked_callable(target.node) if semantics == "int64" else target.func
    try:
        return Outcome("return", fn(**args))
    except Exception as e:  # noqa: BLE001 - the exception *is* the observed outcome
        return Outcome("raise", exc=type(e).__name__)


def call_symbol(symbol: str, source_file: str, args: Dict[str, Any], semantics: str = "math_int") -> Outcome:
    """Entry point used by generated regression tests."""
    from .loader import load_target

    return call_target(load_target(symbol, source_file=source_file), args, semantics)
