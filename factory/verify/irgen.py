"""Source -> IR -> verification conditions.

``parse_function`` turns a Python function (``ast``) into the IR of ir.py,
rejecting everything outside the subset with a specific reason.
``Translator`` maps IR expressions to z3 under one of two integer semantics, and
``execute`` symbolically executes a function into a list of :class:`Path`
(path condition + outcome).  Division by zero, and int64 overflow, are
*error outcomes*, never silently approximated.  See docs/verification-ir.md.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import ir
from .ir import BOOL, INT, TYPES, Unsupported

INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
MAX_PATHS = 512


# ------------------------------------------------------------- source -> IR
def find_function(tree: ast.Module, qualname: str):
    """Locate ``qualname`` (dotted, functions/classes only) in a module AST."""
    node: Any = tree
    for part in qualname.split("."):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child.name == part:
                node = child
                break
        else:
            return None
    return node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None


def _always_exits(stmts) -> bool:
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, (ir.Return, ir.Raise)):
        return True
    if isinstance(last, ir.If):
        return _always_exits(last.body) and _always_exits(last.orelse)
    return False


def parse_function(fn: ast.AST, returns: Optional[str] = None) -> ir.Func:
    """Build IR from a ``FunctionDef`` node or raise :class:`Unsupported`."""
    if isinstance(fn, ast.AsyncFunctionDef):
        raise Unsupported("async functions are not supported")
    if not isinstance(fn, ast.FunctionDef):
        raise Unsupported("not a function definition")
    if fn.decorator_list:
        raise Unsupported("decorated functions are not supported")
    a = fn.args
    if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
        raise Unsupported("*args, **kwargs, keyword-only and positional-only parameters are not supported")
    params: List[Tuple[str, str]] = []
    for arg in a.args:
        ann = arg.annotation
        if not (isinstance(ann, ast.Name) and ann.id in TYPES):
            raise Unsupported(f"parameter '{arg.arg}' needs an 'int' or 'bool' annotation (methods/other types unsupported)")
        params.append((arg.arg, ann.id))
    rty = returns
    if isinstance(fn.returns, ast.Name) and fn.returns.id in TYPES:
        if returns is not None and fn.returns.id != returns:
            raise Unsupported(f"return annotation {fn.returns.id} disagrees with contract returns {returns}")
        rty = fn.returns.id
    elif fn.returns is not None:
        raise Unsupported("return annotation other than int/bool is not supported")
    if rty is None:
        raise Unsupported("return type unknown: annotate '-> int' or '-> bool'")
    scope = dict(params)
    body = _stmts(fn.body, scope, rty, is_body=True)
    if not _always_exits(body):
        raise Unsupported("a path may fall off the end of the function (implicit None return)")
    return ir.Func(fn.name, tuple(params), rty, tuple(body))


def _stmts(nodes, scope: Dict[str, str], rty: str, is_body=False) -> List[Any]:
    out: List[Any] = []
    for i, n in enumerate(nodes):
        if is_body and i == 0 and isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            continue  # docstring
        out.extend(_stmt(n, scope, rty))
    return out


def _expr(node, scope) -> Any:
    return ir.ExprParser(scope).parse(node)


def _stmt(n: ast.AST, scope: Dict[str, str], rty: str) -> List[Any]:
    if isinstance(n, ast.Pass):
        return []
    if isinstance(n, ast.Return):
        if n.value is None:
            raise Unsupported("bare 'return' (None) is not supported")
        e = _expr(n.value, scope)
        if e.ty != rty:
            raise Unsupported(f"returns a {e.ty} where {rty} is declared")
        return [ir.Return(e)]
    if isinstance(n, ast.Assign):
        if len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
            if len(n.targets) == 1 and isinstance(n.targets[0], (ast.Attribute, ast.Subscript)):
                raise Unsupported("mutation of attributes/items is not supported")
            raise Unsupported("only single-name assignment is supported")
        return [_assign(n.targets[0].id, _expr(n.value, scope), scope)]
    if isinstance(n, ast.AnnAssign):
        if not isinstance(n.target, ast.Name) or n.value is None or not (isinstance(n.annotation, ast.Name) and n.annotation.id in TYPES):
            raise Unsupported("annotated assignment must be 'name: int|bool = expr'")
        v = _expr(n.value, scope)
        if v.ty != n.annotation.id:
            raise Unsupported("annotation disagrees with assigned value type")
        return [_assign(n.target.id, v, scope)]
    if isinstance(n, ast.AugAssign):
        if not isinstance(n.target, ast.Name):
            raise Unsupported("mutation of attributes/items is not supported")
        synthetic = ast.BinOp(left=ast.Name(id=n.target.id, ctx=ast.Load()), op=n.op, right=n.value)
        return [_assign(n.target.id, _expr(synthetic, scope), scope)]
    if isinstance(n, ast.If):
        t = _expr(n.test, scope)
        if t.ty != BOOL:
            raise Unsupported("'if' on a non-bool test (truthiness) is not supported")
        # branch-local scopes: a name bound in only one branch is still tracked per path
        sb, so = dict(scope), dict(scope)
        body, orelse = _stmts(n.body, sb, rty), _stmts(n.orelse, so, rty)
        for k, v in list(sb.items()) + list(so.items()):
            if k in scope and scope[k] != v:
                raise Unsupported(f"variable '{k}' changes type")
            scope.setdefault(k, v)
        return [ir.If(t, tuple(body), tuple(orelse))]
    if isinstance(n, ast.Raise):
        exc = n.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if n.cause is not None or not isinstance(exc, ast.Name):
            raise Unsupported("raise must name an exception class, e.g. raise ValueError('...')")
        if isinstance(n.exc, ast.Call) and any(not isinstance(x, ast.Constant) for x in list(n.exc.args) + [k.value for k in n.exc.keywords]):
            raise Unsupported("exception constructor arguments must be constants")
        return [ir.Raise(exc.id)]
    if isinstance(n, ast.Assert):
        raise Unsupported("assert is not supported")
    if isinstance(n, (ast.Global, ast.Nonlocal)):
        raise Unsupported("global/nonlocal state is not supported")
    if isinstance(n, ast.Expr):
        raise Unsupported("expression statements (calls with effects) are not supported")
    if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
        raise Unsupported("nested definitions are not supported")
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        raise Unsupported("imports inside functions are not supported")
    if isinstance(n, (ast.Delete,)):
        raise Unsupported("del is not supported")
    raise ir._unsupported_node(n)


def _assign(name: str, value, scope: Dict[str, str]) -> ir.Assign:
    if name in scope and scope[name] != value.ty:
        raise Unsupported(f"variable '{name}' changes type from {scope[name]} to {value.ty}")
    scope[name] = value.ty
    return ir.Assign(name, value)


# ------------------------------------------------------------ IR -> z3
@dataclass
class Path:
    cond: Any  # z3 BoolRef over the (symbolic) parameters
    kind: str  # 'return' | 'raise'
    value: Any = None  # z3 expression for return paths
    exc: Optional[str] = None


def floordiv_expr(z3, a, b):
    """Python ``a // b`` for b != 0: floor, via z3's Euclidean div (floor for b > 0)."""
    return z3.If(b > 0, a / b, (-a) / (-b))


def mod_expr(z3, a, b):
    """Python ``a % b`` for b != 0: result has the sign of b."""
    return a - b * floordiv_expr(z3, a, b)


class Translator:
    """IR expression -> (z3 value, ordered fault list).

    A *fault* is ``(condition, exception_name)`` raised while evaluating.  Faults
    of operands guarded by short-circuiting are themselves guarded.  When
    ``checked`` is true (int64 implementation semantics) every arithmetic result
    outside the int64 range adds an ``OverflowError`` fault.
    """

    def __init__(self, z3, *, checked: bool, result=None):
        self.z3 = z3
        self.checked = checked
        self.result = result

    def _range_fault(self, v):
        z3 = self.z3
        return (z3.Or(v < INT64_MIN, v > INT64_MAX), "OverflowError")

    def expr(self, e, env: Dict[str, Any], old: Optional[Dict[str, Any]] = None):
        z3 = self.z3
        if isinstance(e, ir.Const):
            if e.ty == INT:
                if self.checked and not INT64_MIN <= e.value <= INT64_MAX:
                    raise Unsupported(f"integer literal {e.value} is outside the int64 range")
                return z3.IntVal(e.value), []
            return z3.BoolVal(e.value), []
        if isinstance(e, ir.Var):
            if e.name not in env:
                raise Unsupported(f"possibly unbound local variable '{e.name}'")
            return env[e.name], []
        if isinstance(e, ir.Old):
            return (old if old is not None else env)[e.name], []
        if isinstance(e, ir.Result):
            if self.result is None:
                raise Unsupported("'result' used outside a postcondition")
            return self.result, []
        if isinstance(e, ir.Unary):
            a, f = self.expr(e.a, env, old)
            if e.op == "not":
                return z3.Not(a), f
            if e.op == "pos":
                return a, f
            v = -a
            return v, f + ([self._range_fault(v)] if self.checked else [])
        if isinstance(e, ir.Bin):
            a, fa = self.expr(e.a, env, old)
            b, fb = self.expr(e.b, env, old)
            faults = fa + fb
            if e.op == "add":
                v = a + b
            elif e.op == "sub":
                v = a - b
            elif e.op == "mul":
                v = a * b
            else:
                faults = faults + [(b == 0, "ZeroDivisionError")]
                v = floordiv_expr(z3, a, b) if e.op == "floordiv" else mod_expr(z3, a, b)
            if self.checked:
                faults = faults + [self._range_fault(v)]
            return v, faults
        if isinstance(e, ir.Cmp):
            a, fa = self.expr(e.a, env, old)
            b, fb = self.expr(e.b, env, old)
            ops = {"eq": lambda: a == b, "ne": lambda: a != b, "lt": lambda: a < b,
                   "le": lambda: a <= b, "gt": lambda: a > b, "ge": lambda: a >= b}
            return ops[e.op](), fa + fb
        if isinstance(e, ir.BoolOp):
            val, faults = self.expr(e.operands[0], env, old)
            guard = val if e.op == "and" else z3.Not(val)  # when the next operand is evaluated
            for o in e.operands[1:]:
                v, f = self.expr(o, env, old)
                faults = faults + [(z3.And(guard, c), x) for c, x in f]
                val = z3.And(val, v) if e.op == "and" else z3.Or(val, v)
                guard = z3.And(guard, v) if e.op == "and" else z3.And(guard, z3.Not(v))
            return val, faults
        if isinstance(e, ir.IfExp):
            t, ft = self.expr(e.test, env, old)
            a, fa = self.expr(e.a, env, old)
            b, fb = self.expr(e.b, env, old)
            faults = ft + [(z3.And(t, c), x) for c, x in fa] + [(z3.And(z3.Not(t), c), x) for c, x in fb]
            return z3.If(t, a, b), faults
        if isinstance(e, ir.Call):
            vals, faults = [], []
            for x in e.args:
                v, f = self.expr(x, env, old)
                vals.append(v)
                faults += f
            if e.fn == "abs":
                v = z3.If(vals[0] >= 0, vals[0], -vals[0])
                if self.checked:
                    faults = faults + [self._range_fault(v)]
                return v, faults
            v = vals[0]
            for w in vals[1:]:
                v = z3.If(w < v, w, v) if e.fn == "min" else z3.If(w > v, w, v)
            return v, faults
        raise Unsupported(f"unhandled IR node {type(e).__name__}")


def defined(z3, faults):
    """Condition under which a predicate/expression evaluates without fault."""
    return z3.And(*[z3.Not(c) for c, _ in faults]) if faults else z3.BoolVal(True)


def make_params(z3, params, semantics: str):
    """Fresh symbolic parameters plus the implicit domain constraint."""
    env, dom = {}, []
    for name, ty in params:
        if ty == INT:
            v = z3.Int(name)
            if semantics == "int64":
                dom += [v >= INT64_MIN, v <= INT64_MAX]
        else:
            v = z3.Bool(name)
        env[name] = v
    return env, (z3.And(*dom) if dom else z3.BoolVal(True))


def execute(z3, func: ir.Func, params_env: Dict[str, Any], semantics: str) -> List[Path]:
    """Symbolically execute ``func``; fork on every branch, no merging, no approximation."""
    tr = Translator(z3, checked=(semantics == "int64"))
    paths: List[Path] = []

    def emit(p: Path):
        paths.append(p)
        if len(paths) > MAX_PATHS:
            raise Unsupported(f"more than {MAX_PATHS} paths (path explosion); not approximated")

    def run(stmts, env, cond):
        if not stmts:
            raise Unsupported("a path falls off the end of the function")  # guarded by _always_exits
        s, rest = stmts[0], stmts[1:]
        if isinstance(s, ir.Raise):
            emit(Path(cond, "raise", exc=s.exc))
            return
        if isinstance(s, ir.If):
            t, faults = tr.expr(s.test, env)
            cond = split_faults(faults, cond)
            run(list(s.body) + list(rest), env, z3.And(cond, t))
            run(list(s.orelse) + list(rest), env, z3.And(cond, z3.Not(t)))
            return
        v, faults = tr.expr(s.value, env)
        cond = split_faults(faults, cond)
        if isinstance(s, ir.Return):
            emit(Path(cond, "return", value=v))
            return
        env2 = dict(env)
        env2[s.name] = v
        run(rest, env2, cond)

    def split_faults(faults, cond):
        for c, exc in faults:
            emit(Path(z3.And(cond, c), "raise", exc=exc))
            cond = z3.And(cond, z3.Not(c))
        return cond

    run(list(func.body), dict(params_env), z3.BoolVal(True))
    return paths
