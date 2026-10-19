"""Locate and load the implementation behind a contract symbol."""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import builtins
import itertools
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .irgen import find_function

_counter = itertools.count()


class LoadError(Exception):
    """The implementation could not be located/parsed/imported (a gate failure)."""


class BindingError(LoadError):
    """The name Python binds is not (provably) the function that was parsed.  ``code`` is the gate reason."""

    def __init__(self, message: str, code: str = "BINDING"):
        super().__init__(message)
        self.code = code


MODELLED_BUILTINS = ("abs", "min", "max")


class _Bindings(ast.NodeVisitor):
    """Count module-scope bindings per name (nested function/class bodies are other scopes)."""

    def __init__(self):
        self.counts: Dict[str, int] = {}
        self.star = False

    def _bind(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1

    def visit_FunctionDef(self, n):
        self._bind(n.name)
        for d in n.decorator_list:
            self.visit(d)
        self._globals(n)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, n):
        self._bind(n.name)
        self._globals(n)

    def _globals(self, n):  # `global X` inside any function body can rebind a module name
        for sub in ast.walk(n):
            if isinstance(sub, ast.Global):
                for g in sub.names:
                    self._bind(g)

    def visit_Lambda(self, n):
        pass

    def visit_Name(self, n):
        if isinstance(n.ctx, (ast.Store, ast.Del)):
            self._bind(n.id)

    def visit_Import(self, n):
        for a in n.names:
            self._bind((a.asname or a.name).split(".")[0])

    def visit_ImportFrom(self, n):
        for a in n.names:
            if a.name == "*":
                self.star = True
            else:
                self._bind(a.asname or a.name)

    def visit_ExceptHandler(self, n):
        if n.name:
            self._bind(n.name)
        self.generic_visit(n)


def check_binding(tree: ast.Module, node: ast.AST, qualname: str) -> None:
    """Refuse modules where the parsed def might not be what Python binds (or where a modelled builtin is shadowed)."""
    b = _Bindings()
    b.visit(tree)
    top = qualname.split(".")[0]
    if b.star:
        raise BindingError("module has a star import, which can rebind the target or a modelled builtin")
    if b.counts.get(top, 0) != 1:
        raise BindingError(f"name {top!r} is defined or assigned {b.counts.get(top, 0)} times at module level; "
                           "the function Python binds is ambiguous, so the parsed def cannot be trusted")
    local = {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg)} if hasattr(node, "args") else set()
    local |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))}
    called = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for name in MODELLED_BUILTINS:
        # a rebinding only matters if the function calls it (a parameter merely named `max` is harmless)
        if name in called and (b.counts.get(name) or name in local):
            raise BindingError(f"builtin {name!r} is rebound or shadowed ("
                               f"{'in the function' if name in local else 'at module level'}); the model of "
                               f"{name} would differ from real execution (MODEL_MISMATCH)", code="MODEL_MISMATCH")


@dataclass
class Target:
    symbol: str
    file: str
    source: str
    tree: ast.Module
    node: ast.AST
    func: Callable
    impl_hash: str
    dep_hashes: Dict[str, str]
    namespace: Dict[str, Any] = None
    module_hash: str = ""
    imports_hash: str = ""
    cacheable: bool = True
    cache_note: str = ""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def impl_hash(node: ast.AST) -> str:
    """Hash of the function's AST (formatting and comments do not change it)."""
    return _sha(ast.dump(node, annotate_fields=True, include_attributes=False))


def dependency_hashes(tree: ast.Module, node: ast.AST) -> Dict[str, str]:
    """Hashes of same-module definitions the function refers to by free name.

    Builtins are covered by the recorded Python version; names that resolve to
    other modules are recorded as ``unresolved`` rather than guessed.
    """
    local = {a.arg for a in getattr(node, "args").args}
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            local.add(n.id)
    free = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                   and n.id not in local and not hasattr(builtins, n.id)})
    defs: Dict[str, ast.AST] = {}
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.ClassDef)):
            defs[top.name] = top
        elif isinstance(top, ast.Assign):
            for t in top.targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = top
        elif isinstance(top, (ast.Import, ast.ImportFrom)):
            for a in top.names:
                defs[(a.asname or a.name).split(".")[0]] = top
    out = {}
    for name in free:
        d = defs.get(name)
        out[name] = _sha(ast.dump(d)) if d is not None else "unresolved"
    return out


def _find_file(module: str, roots: List[Path]) -> Optional[Path]:
    rel = Path(*module.split("."))
    for r in roots:
        for cand in (r / (str(rel) + ".py"), r / rel / "__init__.py"):
            if cand.is_file():
                return cand
    return None


_CODE_FIELDS = ("co_code", "co_names", "co_varnames", "co_argcount", "co_posonlyargcount", "co_kwonlyargcount",
                "co_flags", "co_freevars", "co_cellvars")


def _code_sig(code):
    """Comparable view of a code object; nested code objects in co_consts are compared recursively."""
    consts = tuple(_code_sig(c) if isinstance(c, types.CodeType) else (type(c).__name__, c) for c in code.co_consts)
    return tuple(getattr(code, f) for f in _CODE_FIELDS) + (consts,)


def _find_code(code, qualname):
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            if c.co_qualname == qualname:
                return c
            found = _find_code(c, qualname)
            if found is not None:
                return found
    return None


def check_bound_object(modcode, obj, node, qualname, namespace) -> None:
    """The bound function must be exactly what compiling the parsed def produces (not a patched object)."""
    code = getattr(obj, "__code__", None)
    if code is None:
        return  # not a plain function (e.g. staticmethod); parse_function rejects decorated defs anyway
    expected = _find_code(modcode, qualname)
    if expected is None or _code_sig(expected) != _code_sig(code):
        raise BindingError(f"the compiled code of the bound {qualname!r} differs from the code compiled from the "
                           "parsed def: module-level code replaced __code__ (the parsed def is not what runs)")
    if getattr(obj, "__closure__", None) or getattr(obj, "__kwdefaults__", None) or hasattr(obj, "__wrapped__"):
        raise BindingError(f"the bound {qualname!r} has a closure, keyword defaults or __wrapped__ that the parsed def does not")
    if "." not in qualname and getattr(obj, "__globals__", None) is not namespace:
        raise BindingError(f"the bound {qualname!r} was defined in a different namespace")
    try:
        want = tuple(ast.literal_eval(d) for d in node.args.defaults) or None
    except ValueError:
        raise BindingError("a parameter default is not a literal, so it cannot be compared with the bound function")
    if (getattr(obj, "__defaults__", None) or None) != want:
        raise BindingError(f"the defaults of the bound {qualname!r} differ from the parsed def")


def _is_external(path: str) -> bool:
    import sysconfig
    roots = {sysconfig.get_paths().get(k) for k in ("stdlib", "platstdlib", "purelib", "platlib")}
    return any(r and path.startswith(r) for r in roots)


def imports_fingerprint(tree: ast.Module, path: Path, roots, depth: int = 6):
    """Hash of every repo module the target imports, transitively; stdlib/site-packages are not hashed.

    Returns (hash, cacheable, note).  Unresolvable imports or hitting the depth bound make it non-cacheable.
    """
    seen: Dict[str, str] = {}
    problems: List[str] = []

    def resolve(name: str, level: int, base: Path) -> Optional[Path]:
        if level:
            d = base
            for _ in range(level - 1):
                d = d.parent
            f = _find_file(name, [d]) if name else d / "__init__.py"
            return f if f and f.is_file() else None
        f = _find_file(name, [Path(r) for r in roots] + [base])
        if f:
            return f
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError, AttributeError):
            return None
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            return Path("<external>") if spec is not None else None
        return Path(spec.origin)

    def walk(t: ast.Module, base: Path, d: int):
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                targets = [(a.name, 0) for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                targets = [(n.module or "", n.level)] + [((n.module + "." if n.module else "") + a.name, n.level)
                                                         for a in n.names if a.name != "*"]
            else:
                continue
            for name, level in targets:
                f = resolve(name, level, base)
                if f is None:
                    if not (n.__class__ is ast.ImportFrom and name != (n.module or "")):  # submodule probes may miss
                        problems.append(f"unresolved import {name!r}")
                    continue
                if str(f) == "<external>" or _is_external(str(f)):
                    continue
                key = f"{level}:{name}"
                if str(f) in {v[0] for v in seen.values()}:
                    continue
                if d <= 0:
                    problems.append(f"import depth bound reached at {name!r}")
                    continue
                try:
                    src = f.read_text(encoding="utf-8")
                    sub = ast.parse(src)
                    h = _sha(ast.dump(sub))
                except (OSError, SyntaxError, UnicodeDecodeError):
                    problems.append(f"unreadable import {name!r}")
                    continue
                seen[key] = (str(f), h)
                walk(sub, f.parent, d - 1)

    walk(tree, path.parent, depth)
    digest = _sha(repr(sorted((k, v[1]) for k, v in seen.items())))
    return digest, not problems, "; ".join(sorted(set(problems)))


def load_target(symbol: str, *, roots=(), source_file=None) -> Target:
    module, qualname = symbol.split(":", 1)
    path = Path(source_file) if source_file else _find_file(module, [Path(r) for r in roots])
    if path is None:
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError) as e:
            raise LoadError(f"cannot import module {module!r}: {e}") from e
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            raise LoadError(f"cannot locate source for module {module!r}")
        path = Path(spec.origin)
    if not path.is_file():
        raise LoadError(f"source file {path} does not exist")
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise LoadError(f"{path}: syntax error: {e}") from e
    node = find_function(tree, qualname)
    if node is None:
        b = _Bindings()
        b.visit(tree)
        if b.counts.get(qualname.split(".")[0], 0) > 1:  # e.g. conditional defs: ambiguous, not "missing"
            raise BindingError(f"{path}: {qualname!r} is bound more than once at module level (not a plain top-level def)")
        raise LoadError(f"{path}: no function {qualname!r}")
    check_binding(tree, node, qualname)
    # Execute exactly the text that was parsed (no cached .pyc: a same-size edit within one mtime
    # second would otherwise run stale bytecode while the AST describes the new source).
    mod = types.ModuleType(f"_sf_verify_{next(_counter)}_{module.replace('.', '_')}")
    mod.__file__ = str(path)
    modcode = compile(text, str(path), "exec")
    try:
        exec(modcode, mod.__dict__)  # executes module top level (inherent to replay)
    except Exception as e:
        raise LoadError(f"{path}: importing failed: {type(e).__name__}: {e}") from e
    obj: Any = mod
    for part in qualname.split("."):
        obj = getattr(obj, part, None)
    if not callable(obj):
        raise LoadError(f"{path}: {qualname!r} is not callable after import")
    check_bound_object(modcode, obj, node, qualname, mod.__dict__)
    ih, cacheable, note = imports_fingerprint(tree, path, roots)
    return Target(symbol, str(path), text, tree, node, obj, impl_hash(node), dependency_hashes(tree, node),
                  mod.__dict__, _sha(ast.dump(tree)), ih, cacheable, note)
