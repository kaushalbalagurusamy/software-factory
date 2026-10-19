"""Intermediate representation (IR) for the contract verifier.

The IR is deliberately tiny.  Both implementation bodies and contract
predicates are parsed from Python ``ast`` into the same expression nodes, so a
single semantic model (``irgen``) serves both.  Anything outside the subset
raises :class:`Unsupported` with a specific reason; nothing is approximated.

See docs/verification-ir.md for the full description.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

INT = "int"
BOOL = "bool"
TYPES = (INT, BOOL)
BUILTIN_FUNCS = ("abs", "min", "max")


class Unsupported(Exception):
    """A construct outside the verified subset.  ``reason`` is shown to users."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ----------------------------------------------------------------- expressions
@dataclass(frozen=True)
class Const:
    value: object
    ty: str


@dataclass(frozen=True)
class Var:
    name: str
    ty: str


@dataclass(frozen=True)
class Result:
    ty: str


@dataclass(frozen=True)
class Old:
    name: str
    ty: str


@dataclass(frozen=True)
class Unary:
    op: str  # neg | pos | not
    a: object
    ty: str


@dataclass(frozen=True)
class Bin:
    op: str  # add | sub | mul | floordiv | mod
    a: object
    b: object
    ty: str = INT


@dataclass(frozen=True)
class Cmp:
    op: str  # eq ne lt le gt ge
    a: object
    b: object
    ty: str = BOOL


@dataclass(frozen=True)
class BoolOp:
    op: str  # and | or
    operands: Tuple[object, ...]
    ty: str = BOOL


@dataclass(frozen=True)
class IfExp:
    test: object
    a: object
    b: object
    ty: str = INT


@dataclass(frozen=True)
class Call:
    fn: str  # abs | min | max
    args: Tuple[object, ...]
    ty: str = INT


# ------------------------------------------------------------------ statements
@dataclass(frozen=True)
class Assign:
    name: str
    value: object


@dataclass(frozen=True)
class If:
    test: object
    body: Tuple[object, ...]
    orelse: Tuple[object, ...]


@dataclass(frozen=True)
class Return:
    value: object


@dataclass(frozen=True)
class Raise:
    exc: str


@dataclass(frozen=True)
class Func:
    name: str
    params: Tuple[Tuple[str, str], ...]
    returns: str
    body: Tuple[object, ...]


# --------------------------------------------------------------------- parsing
_BIN = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.FloorDiv: "floordiv", ast.Mod: "mod"}
_CMP = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le", ast.Gt: "gt", ast.GtE: "ge"}

_NODE_REASONS = {
    ast.While: "loops (while) are not supported",
    ast.For: "loops (for) are not supported",
    ast.Try: "try/except is not supported",
    ast.With: "with-blocks are not supported",
    ast.Lambda: "lambda is not supported",
    ast.ListComp: "comprehensions are not supported",
    ast.SetComp: "comprehensions are not supported",
    ast.DictComp: "comprehensions are not supported",
    ast.GeneratorExp: "comprehensions are not supported",
    ast.Attribute: "attribute access is not supported",
    ast.Subscript: "subscripts are not supported",
    ast.List: "container literals are not supported",
    ast.Tuple: "tuples are not supported",
    ast.Dict: "container literals are not supported",
    ast.Set: "container literals are not supported",
    ast.JoinedStr: "strings are not supported",
    ast.Await: "async is not supported",
    ast.Yield: "generators are not supported",
    ast.NamedExpr: "assignment expressions are not supported",
    ast.Starred: "star-expressions are not supported",
}


def _unsupported_node(node: ast.AST) -> Unsupported:
    for cls, reason in _NODE_REASONS.items():
        if isinstance(node, cls):
            return Unsupported(reason)
    return Unsupported(f"{type(node).__name__} is not supported")


class ExprParser:
    """Parse a Python ``ast`` expression into IR with static typing.

    ``scope`` maps names to ``int``/``bool``.  ``predicate=True`` additionally
    admits ``result`` and ``old(name)`` (contract language).
    """

    def __init__(self, scope: Dict[str, str], *, predicate: bool = False, result_ty: Optional[str] = None):
        self.scope = scope
        self.predicate = predicate
        self.result_ty = result_ty

    def parse(self, node: ast.AST):
        m = getattr(self, "_" + type(node).__name__, None)
        if m is None:
            raise _unsupported_node(node)
        return m(node)

    def _Constant(self, n: ast.Constant):
        v = n.value
        if isinstance(v, bool):
            return Const(v, BOOL)
        if isinstance(v, int):
            return Const(v, INT)
        if isinstance(v, float):
            raise Unsupported("floating-point values are not modelled")
        raise Unsupported(f"constant of type {type(v).__name__} is not supported")

    def _Name(self, n: ast.Name):
        if self.predicate and n.id == "result" and "result" not in self.scope:
            if self.result_ty is None:
                raise Unsupported("'result' is not available here")
            return Result(self.result_ty)
        if n.id in self.scope:
            return Var(n.id, self.scope[n.id])
        if self.predicate and n.id in ("True", "False"):
            return Const(n.id == "True", BOOL)
        raise Unsupported(f"free variable or global '{n.id}' is not supported")

    def _UnaryOp(self, n: ast.UnaryOp):
        a = self.parse(n.operand)
        if isinstance(n.op, ast.Not):
            if a.ty != BOOL:
                raise Unsupported("'not' on a non-bool operand (truthiness) is not supported")
            return Unary("not", a, BOOL)
        if isinstance(n.op, (ast.USub, ast.UAdd)):
            if a.ty != INT:
                raise Unsupported("unary +/- on a bool operand is not supported")
            return Unary("neg" if isinstance(n.op, ast.USub) else "pos", a, INT)
        raise Unsupported(f"unary operator {type(n.op).__name__} is not supported")

    def _BinOp(self, n: ast.BinOp):
        op = _BIN.get(type(n.op))
        if op is None:
            raise Unsupported(
                f"operator {type(n.op).__name__} is not supported (true division, powers and bit-level "
                "operators are not modelled)"
            )
        a, b = self.parse(n.left), self.parse(n.right)
        if a.ty != INT or b.ty != INT:
            raise Unsupported("arithmetic on bool operands is not supported")
        return Bin(op, a, b)

    def _Compare(self, n: ast.Compare):
        operands = [self.parse(n.left)] + [self.parse(c) for c in n.comparators]
        parts = []
        for i, o in enumerate(n.ops):
            op = _CMP.get(type(o))
            if op is None:
                raise Unsupported(f"comparison {type(o).__name__} is not supported")
            a, b = operands[i], operands[i + 1]
            if a.ty != b.ty:
                raise Unsupported("comparison between int and bool operands is not supported")
            if a.ty == BOOL and op not in ("eq", "ne"):
                raise Unsupported("ordering comparison on bool operands is not supported")
            parts.append(Cmp(op, a, b))
        return parts[0] if len(parts) == 1 else BoolOp("and", tuple(parts))

    def _BoolOp(self, n: ast.BoolOp):
        ops = tuple(self.parse(v) for v in n.values)
        if any(o.ty != BOOL for o in ops):
            raise Unsupported("'and'/'or' on non-bool operands (value-returning semantics) is not supported")
        return BoolOp("and" if isinstance(n.op, ast.And) else "or", ops)

    def _IfExp(self, n: ast.IfExp):
        t, a, b = self.parse(n.test), self.parse(n.body), self.parse(n.orelse)
        if t.ty != BOOL:
            raise Unsupported("conditional on a non-bool test is not supported")
        if a.ty != b.ty:
            raise Unsupported("conditional expression branches have different types")
        return IfExp(t, a, b, a.ty)

    def _Call(self, n: ast.Call):
        if not isinstance(n.func, ast.Name):
            raise Unsupported("call to a non-name callee is not supported")
        fn = n.func.id
        if n.keywords:
            raise Unsupported(f"call to '{fn}' with keyword arguments is not supported")
        if self.predicate and fn == "old":
            if len(n.args) != 1 or not isinstance(n.args[0], ast.Name) or n.args[0].id not in self.scope:
                raise Unsupported("old() takes exactly one parameter name")
            return Old(n.args[0].id, self.scope[n.args[0].id])
        if fn in BUILTIN_FUNCS and fn not in self.scope:
            args = tuple(self.parse(a) for a in n.args)
            if any(a.ty != INT for a in args):
                raise Unsupported(f"{fn}() on non-int arguments is not supported")
            if fn == "abs" and len(args) != 1:
                raise Unsupported("abs() takes exactly one argument")
            if fn != "abs" and len(args) < 2:
                raise Unsupported(f"{fn}() with fewer than two arguments is not supported")
            return Call(fn, args)
        raise Unsupported(f"call to '{fn}' is not supported (only abs/min/max builtins are modelled)")


def parse_predicate(text: str, scope: Dict[str, str], result_ty: str):
    """Parse a contract-language predicate; raises ``Unsupported`` (with a reason)."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as e:
        raise Unsupported(f"syntax error: {e.msg}") from None
    expr = ExprParser(scope, predicate=True, result_ty=result_ty).parse(tree.body)
    if expr.ty != BOOL:
        raise Unsupported("a predicate must be a boolean expression")
    return expr


def walk_names(expr, acc: Optional[set] = None) -> set:
    """Names of parameters referenced by an IR expression (including via old())."""
    acc = set() if acc is None else acc
    if isinstance(expr, (Var, Old)):
        acc.add(expr.name)
    elif isinstance(expr, Unary):
        walk_names(expr.a, acc)
    elif isinstance(expr, (Bin, Cmp)):
        walk_names(expr.a, acc)
        walk_names(expr.b, acc)
    elif isinstance(expr, BoolOp):
        for o in expr.operands:
            walk_names(o, acc)
    elif isinstance(expr, IfExp):
        for o in (expr.test, expr.a, expr.b):
            walk_names(o, acc)
    elif isinstance(expr, Call):
        for o in expr.args:
            walk_names(o, acc)
    return acc


def mentions_result(expr) -> bool:
    if isinstance(expr, Result):
        return True
    if isinstance(expr, Unary):
        return mentions_result(expr.a)
    if isinstance(expr, (Bin, Cmp)):
        return mentions_result(expr.a) or mentions_result(expr.b)
    if isinstance(expr, BoolOp):
        return any(mentions_result(o) for o in expr.operands)
    if isinstance(expr, IfExp):
        return any(mentions_result(o) for o in (expr.test, expr.a, expr.b))
    if isinstance(expr, Call):
        return any(mentions_result(o) for o in expr.args)
    return False
