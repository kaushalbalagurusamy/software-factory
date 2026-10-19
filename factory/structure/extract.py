"""Structural extraction for Python projects using only the stdlib `ast` module.

What it records, per repository tree:
  * modules, classes, functions/methods with source spans and stable symbol ids `<module.path>:<Qualname>`
  * imports, call sites, and for every call edge an honest `kind`:
      resolved    target found through the project's own import map / local scope / class members
      syntactic   matched by text only (for example a method on an object of unknown type); `candidates`
                  lists repo methods with that name, it is NOT a claim that any of them is called
      unresolved  dynamic or ambiguous (getattr, calls through variables, subscripts, lambdas, star imports,
                  conditional imports, decorator-wrapped targets, eval/exec, call of a call result); the
                  edge carries `reason_code` and `reason`
  * mutable state: module-level variables, global/nonlocal, `self.x = ...`, class attributes, mutation of
    module-level containers
  * `limits`: what this extraction could NOT establish. It is never a complete call graph.

There is no type inference, no LSP and no execution. Calls to builtins and to modules outside the repository
are counted in `limits.external_calls_not_recorded` and are not edges.
"""
from __future__ import annotations

import ast
import builtins
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SCHEMA = "factory.structure/1"
SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "build", "dist", "venv", "env"}
MUTATORS = {
    "append", "extend", "add", "update", "pop", "popitem", "clear", "remove", "discard", "insert",
    "setdefault", "sort", "reverse", "appendleft", "popleft", "extendleft",
}
DYNAMIC_BUILTINS = {
    "getattr": ("dynamic_attribute", "attribute looked up by a runtime string via getattr"),
    "setattr": ("dynamic_attribute", "attribute set by a runtime string via setattr"),
    "delattr": ("dynamic_attribute", "attribute deleted by a runtime string via delattr"),
    "eval": ("dynamic_code", "code evaluated from a runtime string via eval"),
    "exec": ("dynamic_code", "code executed from a runtime string via exec"),
    "compile": ("dynamic_code", "code compiled from a runtime string"),
    "__import__": ("dynamic_import", "module imported by a runtime name via __import__"),
}
DYNAMIC_EXTERNAL = {
    "importlib.import_module": ("dynamic_import", "module imported by a runtime name via importlib"),
    "importlib.__import__": ("dynamic_import", "module imported by a runtime name via importlib"),
}
# Decorators that do not change which function a call reaches. A decorator is trusted only when its name is
# bound to the builtin or to an import of the stdlib object listed here; a repo-defined name never qualifies.
TRANSPARENT_BUILTINS = {"staticmethod", "classmethod", "property"}
TRANSPARENT_QUALIFIED = {
    "functools.cache", "functools.lru_cache", "functools.cached_property", "functools.total_ordering",
    "abc.abstractmethod", "typing.final", "typing.override", "typing.overload", "typing_extensions.final",
    "typing_extensions.override", "typing_extensions.overload", "dataclasses.dataclass",
}
PROPERTY_ACCESSORS = {"setter", "getter", "deleter"}
# Used only to find the `self` parameter, never to trust a decorator.
TRANSPARENT_DECORATORS = {
    "staticmethod", "classmethod", "property", "abstractmethod", "final", "override", "overload", "dataclass",
    "setter", "getter", "deleter", "cached_property", "lru_cache", "cache", "total_ordering",
}
MAX_CANDIDATES = 25
MUTABLE_CONTAINER_CALLS = {"list", "dict", "set", "defaultdict", "OrderedDict", "deque", "Counter", "bytearray"}
NOTES = [
    "Python only; stdlib ast; no type inference, no LSP, no execution.",
    "resolved edges follow names through imports, local scope and class members; self-dispatch resolves to the "
    "declaring class and a subclass may override.",
    "syntactic edges are name matches only; candidates are not claims.",
    "calls to builtins and to modules outside the scanned tree are counted, not recorded as edges.",
    "module names are derived from paths relative to the scanned root (no source-root or sys.path logic).",
]


class StructureError(ValueError):
    """Bad input (unknown path, bad git revision)."""


# ---- sources --------------------------------------------------------------------------------------------------


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIRS


def _excluded(rel: str, patterns) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


class DirSource:
    def __init__(self, root: str | Path, exclude=()):
        self.root = Path(root)
        if not self.root.is_dir():
            raise StructureError(f"not a directory: {root}")
        self.exclude = tuple(exclude)
        self.label = str(self.root)

    def files(self) -> list[str]:
        out = []
        for dirpath, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
            for n in names:
                if n.endswith(".py"):
                    rel = (Path(dirpath) / n).relative_to(self.root).as_posix()
                    if not _excluded(rel, self.exclude):
                        out.append(rel)
        return sorted(out)

    def read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()


class GitSource:
    """Read-only view of a git revision (`git ls-tree` and `git show`; nothing is checked out)."""

    def __init__(self, repo: str | Path, rev: str, exclude=()):
        self.repo, self.rev, self.exclude = Path(repo), rev, tuple(exclude)
        self.label = f"git:{rev}"
        self._run(["git", "-C", str(self.repo), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"])

    @staticmethod
    def _run(cmd: list[str]) -> bytes:
        try:
            p = subprocess.run(cmd, capture_output=True)
        except OSError as e:
            raise StructureError(f"cannot run git: {e}") from e
        if p.returncode != 0:
            raise StructureError(f"{' '.join(cmd[3:])} failed: {p.stderr.decode(errors='replace').strip() or 'unknown revision'}")
        return p.stdout

    def files(self) -> list[str]:
        raw = self._run(["git", "-C", str(self.repo), "ls-tree", "-r", "--name-only", "-z", self.rev])
        out = []
        for rel in raw.decode("utf-8", errors="surrogateescape").split("\0"):
            if rel.endswith(".py") and not any(_skip_dir(p) for p in PurePosixPath(rel).parts[:-1]) and not _excluded(rel, self.exclude):
                out.append(rel)
        return sorted(out)

    def read(self, rel: str) -> bytes:
        return self._run(["git", "-C", str(self.repo), "show", f"{self.rev}:{rel}"])


def make_source(spec, repo=None, exclude=()):
    """A path, a `git:<rev>` string (needs `repo`) or an existing source object."""
    if hasattr(spec, "files") and hasattr(spec, "read"):
        return spec
    if isinstance(spec, str) and spec.startswith("git:"):
        if repo is None:
            raise StructureError("git:<rev> needs a repository path (repo=...)")
        return GitSource(repo, spec[4:], exclude)
    return DirSource(spec, exclude)


# ---- data ------------------------------------------------------------------------------------------------------


@dataclass
class Binding:
    kind: str  # def | class | module | from | var
    target: str | None = None  # symbol id (def/class), module name (module), absolute module (from)
    attr: str | None = None
    conditional: bool = False
    line: int = 0


@dataclass
class Scope:
    params: set = field(default_factory=set)
    vars: set = field(default_factory=set)
    defs: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)
    globals_decl: set = field(default_factory=set)
    nonlocals: set = field(default_factory=set)


@dataclass
class Mod:
    name: str
    path: str
    is_pkg: bool
    tree: ast.Module | None = None
    error: dict | None = None
    nlines: int = 0
    bindings: dict = field(default_factory=dict)
    star: list = field(default_factory=list)
    imports: list = field(default_factory=list)


def module_name(rel: str) -> tuple[str, bool]:
    parts = list(PurePosixPath(rel).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        return (".".join(parts) or "__init__"), True
    return ".".join(parts), False


def _def_nodes(node):
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def _dump(node, root) -> str:
    """Normalised dump: no positions, nested definitions replaced by a placeholder."""
    if isinstance(node, ast.AST):
        if node is not root and _def_nodes(node):
            return f"<def {type(node).__name__} {node.name}>"
        return f"{type(node).__name__}(" + ",".join(f"{n}={_dump(v, root)}" for n, v in ast.iter_fields(node)) + ")"
    if isinstance(node, list):
        return "[" + ",".join(_dump(v, root) for v in node) + "]"
    return repr(node)


def ast_hash(node) -> str | None:
    try:
        return hashlib.sha256(_dump(node, node).encode("utf-8", "surrogatepass")).hexdigest()
    except RecursionError:
        return None


def walk_scope(body):
    """Yield nodes of one scope. Nested defs/classes are yielded but not entered; their decorators, defaults
    and bases (evaluated in this scope) are. Lambdas and comprehensions are entered."""
    stack = list(reversed(body))
    while stack:
        n = stack.pop()
        yield n
        if _def_nodes(n):
            kids = list(n.decorator_list)
            if isinstance(n, ast.ClassDef):
                kids += n.bases + [k.value for k in n.keywords]
            else:
                kids += n.args.defaults + [d for d in n.args.kw_defaults if d is not None]
            stack.extend(reversed(kids))
        else:
            stack.extend(reversed(list(ast.iter_child_nodes(n))))


def _unparse(n) -> str:
    try:
        return ast.unparse(n)
    except (ValueError, RecursionError):
        return type(n).__name__


def _doc_line(node) -> str:
    try:
        doc = ast.get_docstring(node)
    except TypeError:
        return ""
    return (doc or "").strip().split("\n")[0][:200]


def _deco_name(d) -> str:
    if isinstance(d, ast.Call):
        d = d.func
    return _unparse(d)


def ast_lines(text: str) -> list[str]:
    """Lines numbered exactly as ast numbers them: only \\n, \\r\\n and \\r end a line (not \\f, \\v, \\x1c-\\x1e, \\x85, U+2028/9)."""
    parts = re.split(r"\r\n|\r|\n", text)
    return parts[:-1] if parts and parts[-1] == "" else parts


# ---- extractor -------------------------------------------------------------------------------------------------


class Extractor:
    def __init__(self, source, only_label=None):
        self.source = source
        self.mods: dict[str, Mod] = {}
        self.symbols: dict[str, dict] = {}
        self.node_sym: dict[int, str] = {}  # id(ast node) -> symbol id
        self.sym_node: dict[str, ast.AST] = {}
        self.members: dict[str, dict] = {}  # class id -> {name: [symids]}
        self.class_vars: dict[str, set] = {}
        self.scopes: dict[str, Scope] = {}
        self.state: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.writes: list[dict] = []
        self.reads: dict[str, dict] = {}
        self.imports_out: dict[str, list] = {}
        self.methods_by_name: dict[str, list] = {}
        self.external_calls = 0
        self.hash_failures: list[str] = []
        self.prefixes: set[str] = set()
        self._seen_edges: set = set()
        self._state_parts: dict[str, list] = {}
        self.sub_index: dict[str, set] = {}  # class id -> direct repo subclasses
        self.attr_defs: dict[str, set] = {}  # class id -> names assigned as instance/class attributes anywhere in the repo
        self.patched: set = set()  # (module, attr) rebound by `mod.attr = ...` somewhere in the repo

    # -- pass 1: parse + symbols

    def run(self) -> dict:
        files = self.source.files()
        failures = []
        for rel in files:
            name, is_pkg = module_name(rel)
            mod = Mod(name, rel, is_pkg)
            try:
                raw = self.source.read(rel)
                mod.tree = ast.parse(raw, filename=rel)
                mod.nlines = len(ast_lines(raw.decode("utf-8", errors="replace")))
            except SyntaxError as e:
                mod.error = {"path": rel, "error": f"{type(e).__name__}: {e.msg}", "line": e.lineno or 0}
            except (ValueError, RecursionError, MemoryError, UnicodeDecodeError) as e:
                mod.error = {"path": rel, "error": f"{type(e).__name__}: {e}", "line": 0}
            except (OSError, subprocess.SubprocessError, StructureError) as e:
                mod.error = {"path": rel, "error": f"unreadable: {e}", "line": 0}
            if mod.error:
                failures.append(mod.error)
            if name in self.mods:  # a/b.py vs a/b/__init__.py
                other = self.mods[name]
                failures.append({"path": rel, "error": f"module name {name!r} also provided by {other.path}; the second is not analysed", "line": 0})
                continue
            self.mods[name] = mod
            parts = name.split(".")
            for i in range(1, len(parts)):
                self.prefixes.add(".".join(parts[:i]))
        for mod in self.mods.values():
            if mod.tree is not None:
                self._collect_symbols(mod)
        for mod in self.mods.values():
            if mod.tree is not None:
                self._collect_env(mod)
        for sid, sym in self.symbols.items():
            if sym["kind"] == "method":
                self.methods_by_name.setdefault(sym["name"], []).append(sid)
        self._prepass()
        for mod in self.mods.values():
            if mod.tree is not None:
                self._analyse_module(mod)
        return self._result(files, failures)

    def _add_symbol(self, mod: Mod, node, kind, qual, parent, start, end, decorators=(), bases=()) -> str:
        sid = f"{mod.name}:{qual}"
        n = 2
        while sid in self.symbols:  # conditional redefinition: stable ordinal suffix
            sid = f"{mod.name}:{qual}#{n}"
            n += 1
        self.symbols[sid] = {
            "id": sid, "kind": kind, "name": qual.split(".")[-1] if kind != "module" else mod.name.split(".")[-1],
            "qualname": qual, "module": mod.name, "path": mod.path, "start": start, "end": end, "parent": parent,
            "decorators": list(decorators), "bases": list(bases),
            "async": isinstance(node, ast.AsyncFunctionDef), "ast_hash": ast_hash(node), "doc": _doc_line(node),
        }
        if self.symbols[sid]["ast_hash"] is None:
            self.hash_failures.append(sid)
        self.node_sym[id(node)] = sid
        self.sym_node[sid] = node
        return sid

    def _collect_symbols(self, mod: Mod) -> None:
        msid = self._add_symbol(mod, mod.tree, "module", "<module>", None, 1, max(mod.nlines, 1))
        self.symbols[msid]["name"] = mod.name.split(".")[-1]

        def visit(body, parent_sid, parent_qual, parent_kind):
            for n in walk_defs(body):
                if isinstance(n, ast.ClassDef):
                    kind = "class"
                elif parent_kind == "class":
                    kind = "method"
                else:
                    kind = "function"
                prefix = "" if parent_kind == "module" else (parent_qual + (".<locals>." if parent_kind in ("function", "method") else "."))
                qual = prefix + n.name
                start = min([n.lineno] + [d.lineno for d in n.decorator_list])
                sid = self._add_symbol(mod, n, kind, qual, parent_sid, start, n.end_lineno or n.lineno,
                                       [_unparse(d) for d in n.decorator_list],
                                       [_unparse(b) for b in n.bases] if isinstance(n, ast.ClassDef) else ())
                if isinstance(n, ast.ClassDef):
                    self.members[sid] = {}
                visit(n.body, sid, qual, kind)

        def walk_defs(body):
            """Defs directly in this scope (descending through if/try/with/for/while, not into other defs)."""
            for st in walk_scope(body):
                if _def_nodes(st):
                    yield st

        visit(mod.tree.body, msid, "", "module")
        # class member tables
        for sid, sym in list(self.symbols.items()):
            if sym["module"] == mod.name and sym["kind"] in ("method", "class") and sym["parent"] in self.members:
                self.members[sym["parent"]].setdefault(sym["name"], []).append(sid)

    # -- pass 2: module environments

    def _abs_from(self, mod: Mod, level: int, module: str | None) -> str | None:
        if level == 0:
            return module or ""
        pkg = mod.name.split(".") if mod.is_pkg else mod.name.split(".")[:-1]
        if mod.name == "__init__":
            pkg = []
        up = level - 1
        if up > len(pkg):
            return None
        base = pkg[: len(pkg) - up]
        return ".".join(base + ([module] if module else []))

    def _bind(self, table: dict, name: str, b: Binding) -> None:
        table.setdefault(name, []).append(b)

    def _collect_env(self, mod: Mod) -> None:
        def stmt_bodies(st):
            if isinstance(st, ast.If):
                return [(st.body, True), (st.orelse, True)]
            if isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
                return [(st.body, True), *[(h.body, True) for h in st.handlers], (st.orelse, True), (st.finalbody, False)]
            if isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                return [(st.body, True), (st.orelse, True)]
            if isinstance(st, (ast.With, ast.AsyncWith)):
                return [(st.body, False)]
            if isinstance(st, ast.Match):
                return [(c.body, True) for c in st.cases]
            return []

        def targets(t):
            if isinstance(t, ast.Name):
                yield t
            elif isinstance(t, (ast.Tuple, ast.List)):
                for e in t.elts:
                    yield from targets(e)
            elif isinstance(t, ast.Starred):
                yield from targets(t.value)

        def is_mutable(v) -> bool:
            if isinstance(v, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
                return True
            return isinstance(v, ast.Call) and _unparse(v.func).split(".")[-1] in MUTABLE_CONTAINER_CALLS

        def note_state(name_node, value, line, kind="module_var", stmt=None):
            sid = f"{mod.name}:{name_node.id}"
            rec = self.state.setdefault(sid, {
                "id": sid, "kind": kind, "module": mod.name, "name": name_node.id, "path": mod.path, "start": line,
                "end": getattr(name_node, "end_lineno", line) or line, "mutable_container": False, "assignments": 0,
            })
            rec["assignments"] += 1
            if stmt is not None:
                self._state_parts.setdefault(sid, []).append(_dump(stmt, stmt))
            if value is not None and is_mutable(value):
                rec["mutable_container"] = True

        def visit(body, cond):
            for st in body:
                if _def_nodes(st):
                    kind = "class" if isinstance(st, ast.ClassDef) else "def"
                    self._bind(mod.bindings, st.name, Binding(kind, self.node_sym[id(st)], conditional=cond, line=st.lineno))
                elif isinstance(st, ast.Import):
                    for a in st.names:
                        if a.asname:
                            self._bind(mod.bindings, a.asname, Binding("module", a.name, conditional=cond, line=st.lineno))
                        else:
                            top = a.name.split(".")[0]
                            self._bind(mod.bindings, top, Binding("module", top, conditional=cond, line=st.lineno))
                        mod.imports.append({"kind": "import", "module": a.name, "name": None, "alias": a.asname, "conditional": cond, "line": st.lineno,
                                            "resolved_module": a.name if self._is_repo_mod(a.name) else None})
                elif isinstance(st, ast.ImportFrom):
                    absmod = self._abs_from(mod, st.level, st.module)
                    for a in st.names:
                        if a.name == "*":
                            mod.star.append({"module": absmod, "line": st.lineno})
                            mod.imports.append({"kind": "star_import", "module": absmod, "name": "*", "alias": None, "conditional": cond, "line": st.lineno,
                                                "resolved_module": absmod if absmod and self._is_repo_mod(absmod) else None})
                            continue
                        self._bind(mod.bindings, a.asname or a.name, Binding("from", absmod, a.name, cond, st.lineno))
                        mod.imports.append({"kind": "from", "module": absmod, "name": a.name, "alias": a.asname, "conditional": cond, "line": st.lineno,
                                            "resolved_module": absmod if absmod and self._is_repo_mod(absmod) else None})
                elif isinstance(st, ast.Assign):
                    for t in st.targets:
                        for nm in targets(t):
                            self._bind(mod.bindings, nm.id, Binding("var", mod.name, conditional=cond, line=st.lineno))
                            note_state(nm, st.value, st.lineno, stmt=st)
                elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
                    for nm in targets(st.target):
                        self._bind(mod.bindings, nm.id, Binding("var", mod.name, conditional=cond, line=st.lineno))
                        note_state(nm, getattr(st, "value", None), st.lineno, stmt=st)
                elif isinstance(st, (ast.For, ast.AsyncFor)):
                    for nm in targets(st.target):
                        self._bind(mod.bindings, nm.id, Binding("var", mod.name, conditional=True, line=st.lineno))
                        note_state(nm, None, st.lineno)
                elif isinstance(st, (ast.With, ast.AsyncWith)):
                    for it in st.items:
                        if it.optional_vars is not None:
                            for nm in targets(it.optional_vars):
                                self._bind(mod.bindings, nm.id, Binding("var", mod.name, conditional=cond, line=st.lineno))
                                note_state(nm, None, st.lineno)
                for body2, c2 in stmt_bodies(st):
                    visit(body2, cond or c2)

        visit(mod.tree.body, False)
        # class-level variables
        for sid, sym in self.symbols.items():
            if sym["module"] == mod.name and sym["kind"] == "class":
                names = set()
                for n in walk_scope(self.sym_node[sid].body):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        names.add(n.id)
                self.class_vars[sid] = names
        self.imports_out[mod.name] = mod.imports

    def _is_repo_mod(self, name: str) -> bool:
        return name in self.mods or name in self.prefixes

    # -- scopes for symbols

    def _scope_of(self, sid: str) -> Scope:
        if sid in self.scopes:
            return self.scopes[sid]
        sc = Scope()
        node = self.sym_node[sid]
        mod = self.mods[self.symbols[sid]["module"]]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            for arg in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []):
                sc.params.add(arg.arg)
        body = node.body
        for n in walk_scope(body):
            if isinstance(n, ast.Global):
                sc.globals_decl.update(n.names)
            elif isinstance(n, ast.Nonlocal):
                sc.nonlocals.update(n.names)
            elif _def_nodes(n):
                sc.defs.setdefault(n.name, []).append(self.node_sym[id(n)])
            elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                sc.vars.add(n.id)
            elif isinstance(n, ast.arg):
                sc.vars.add(n.arg)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                sc.vars.add(n.name)
            elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
                sc.vars.add(n.name)
            elif isinstance(n, ast.MatchMapping) and n.rest:
                sc.vars.add(n.rest)
            elif isinstance(n, ast.Import):
                for al in n.names:
                    if al.asname:
                        self._bind(sc.imports, al.asname, Binding("module", al.name, line=n.lineno))
                    else:
                        top = al.name.split(".")[0]
                        self._bind(sc.imports, top, Binding("module", top, line=n.lineno))
            elif isinstance(n, ast.ImportFrom):
                absmod = self._abs_from(mod, n.level, n.module)
                for al in n.names:
                    if al.name != "*":
                        self._bind(sc.imports, al.asname or al.name, Binding("from", absmod, al.name, False, n.lineno))
        sc.vars -= sc.globals_decl | sc.nonlocals
        self.scopes[sid] = sc
        return sc

    def _chain(self, sid: str) -> list[Scope]:
        """Function/class scopes visible from `sid`, outermost first (intermediate class scopes are skipped)."""
        chain = []
        cur = sid
        first = True
        while cur and self.symbols[cur]["kind"] != "module":
            kind = self.symbols[cur]["kind"]
            if first or kind in ("function", "method"):
                chain.append(self._scope_of(cur))
            first = False
            cur = self.symbols[cur]["parent"]
        return list(reversed(chain))

    # -- resolution

    def _binding_target(self, b: Binding, name: str, seen: frozenset, local: bool = False):
        if b.kind in ("def", "class"):
            return ("sym", b.target)
        if b.kind == "var":
            sid = f"{b.target}:{name}"
            return ("var", "module-level variable", sid if sid in self.state else None)
        if b.kind == "module":
            if self._is_repo_mod(b.target):
                return ("module", b.target)
            return ("external", b.target)
        # from-import
        absmod, attr = b.target, b.attr
        if absmod is None:
            return ("unres", "bad_relative_import", f"relative import of {attr!r} goes above the scanned root")
        sub = f"{absmod}.{attr}" if absmod else attr
        if sub in self.mods or sub in self.prefixes:
            if sub in self.mods and self.mods[sub].tree is None:
                return ("unres", "unparsed_module", f"module {sub!r} failed to parse")
            return ("module", sub)
        if absmod in self.mods:
            m = self.mods[absmod]
            if m.tree is None:
                return ("unres", "unparsed_module", f"module {absmod!r} failed to parse ({m.error['error']})")
            if (absmod, attr) in seen:
                return ("unres", "import_cycle", f"import cycle while resolving {attr!r} in {absmod!r}")
            return self._module_attr(absmod, attr, seen | {(absmod, attr)})
        if absmod in self.prefixes:
            return ("unres", "module_attr_missing", f"{attr!r} is not a module or symbol under namespace {absmod!r}")
        return ("external", f"{absmod}.{attr}")

    def _star_could_shadow(self, mod: Mod, bs: list[Binding], name: str) -> bool:
        """A `from x import *` after an earlier binding of `name` may rebind it."""
        for st in mod.star:
            if any(b.line < st["line"] for b in bs):
                tgt = self.mods.get(st["module"] or "")
                if tgt is None or tgt.tree is None or tgt.star:
                    return True  # exported names of an unscanned/unparsed/star-chained module are unknown
                if name in tgt.bindings and not name.startswith("_"):
                    return True
        return False

    def _resolve_bindings(self, bs: list[Binding], name: str, seen: frozenset, mod: Mod | None = None):
        if mod is not None:
            r = self._resolve_bindings(bs, name, seen)
            cands = sorted({r[1]} if r[0] == "sym" else (set(r[3]) if r[0] == "unres" and len(r) > 3 else set()))
            if (mod.name, name) in self.patched:
                return ("unres", "module_attr_rebound", f"{mod.name}.{name} is rebound by an attribute assignment elsewhere in the repo", cands)
            if self._star_could_shadow(mod, bs, name):
                return ("unres", "star_import_rebinding", f"{name!r} is bound before a star import in {mod.name!r} that may rebind it", cands)
            return r
        if len(bs) == 1 and not (bs[0].conditional and bs[0].kind in ("module", "from")):
            return self._binding_target(bs[0], name, seen)
        targets = [self._binding_target(b, name, seen) for b in bs]
        if all(t[0] == "external" for t in targets):
            return targets[0]
        code = "conditional_import" if any(b.conditional and b.kind in ("module", "from") for b in bs) else "multiple_bindings"
        cands = sorted({t[1] for t in targets if t[0] == "sym"})
        return ("unres", code, f"name {name!r} has {len(bs)} binding(s) (conditional or repeated); the callee cannot be fixed statically", cands)

    def _module_attr(self, modname: str, attr: str, seen: frozenset):
        m = self.mods[modname]
        bs = m.bindings.get(attr)
        if bs:
            return self._resolve_bindings(bs, attr, seen, m)
        if m.star:
            return ("unres", "star_import", f"{attr!r} may come from a star import in {modname!r}")
        return ("unres", "module_attr_missing", f"{attr!r} is not defined at module level in {modname!r}")

    def _lookup_name(self, name: str, ctx: dict):
        for sc in reversed(ctx["chain"]):
            if name in sc.globals_decl:
                break
            if name in sc.defs:
                ids = sc.defs[name]
                return ("sym", ids[0]) if len(ids) == 1 else ("unres", "multiple_bindings", f"name {name!r} defined {len(ids)} times in one scope")
            if name in sc.imports:
                return self._resolve_bindings(sc.imports[name], name, frozenset())
            if name in sc.params:
                return ("var", "parameter", None)
            if name in sc.vars:
                return ("var", "local variable", None)
            if name in sc.nonlocals:
                return ("var", "enclosing-scope variable", None)
        mod = ctx["mod"]
        bs = mod.bindings.get(name)
        if bs:
            return self._resolve_bindings(bs, name, frozenset(), mod)
        if hasattr(builtins, name):  # a star import could shadow a builtin; that is not modelled
            return ("builtin", name)
        if mod.star:
            return ("unres", "star_import", f"{name!r} may come from star import(s) of {', '.join(str(s['module']) for s in mod.star)}")
        return ("unres", "undefined_name", f"{name!r} is not bound in any visible scope")

    def _member(self, class_id: str, name: str, skip_self: bool = False, _seen=None):
        """Members called `name` in the class or its repo-resolvable bases: (ids, saw_unknown_base)."""
        _seen = _seen or set()
        if class_id in _seen:
            return [], True
        _seen.add(class_id)
        unknown = False
        if not skip_self and name in self.members.get(class_id, {}):
            return list(self.members[class_id][name]), False
        node = self.sym_node[class_id]
        mod = self.mods[self.symbols[class_id]["module"]]
        ctx = {"mod": mod, "chain": self._chain(self.symbols[class_id]["parent"])}
        for b in node.bases:
            r = self._resolve_expr(b, ctx)
            if r and r[0] == "sym" and self.symbols[r[1]]["kind"] == "class":
                ids, unk = self._member(r[1], name, False, _seen)
                if ids:
                    return ids, False
                unknown = unknown or unk
            else:
                unknown = True
        return [], unknown

    def _resolve_expr(self, node, ctx):
        """Resolve a Name / Attribute chain expression to ('sym'|'module'|...) or None."""
        if isinstance(node, ast.Name):
            return self._lookup_name(node.id, ctx)
        if isinstance(node, ast.Attribute):
            base = self._resolve_expr(node.value, ctx)
            if base is None:
                return None
            return self._step(base, node.attr, ctx)
        return None

    def _step(self, base, attr: str, ctx):
        k = base[0]
        if k == "module":
            name = base[1]
            sub = f"{name}.{attr}"
            if sub in self.mods or sub in self.prefixes:
                if sub in self.mods and self.mods[sub].tree is None:
                    return ("unres", "unparsed_module", f"module {sub!r} failed to parse")
                return ("module", sub)
            if name in self.mods:
                if self.mods[name].tree is None:
                    return ("unres", "unparsed_module", f"module {name!r} failed to parse")
                return self._module_attr(name, attr, frozenset())
            return ("unres", "module_attr_missing", f"{attr!r} is not a module or symbol under namespace {name!r}")
        if k == "sym" and self.symbols[base[1]]["kind"] == "class":
            ids, _ = self._member(base[1], attr)
            if len(ids) == 1 and self._attr_shadowed(base[1], attr):
                return ("attr", f"{self.symbols[base[1]]['name']}.{attr}")
            if len(ids) == 1:
                return ("sym", ids[0])
            if len(ids) > 1:
                return ("unres", "multiple_bindings", f"{attr!r} is defined {len(ids)} times on the class")
            return ("attr", f"{self.symbols[base[1]]['name']}.{attr}")
        if k == "external":
            return ("external", f"{base[1]}.{attr}")
        if k == "builtin":
            return ("external", f"builtins.{base[1]}.{attr}")
        if k == "unres":
            return base
        if k == "var":
            return ("attr", attr, base)
        return ("attr", attr)

    # -- pass 3: per-symbol analysis

    def _analyse_module(self, mod: Mod) -> None:
        for sid, sym in self.symbols.items():
            if sym["module"] == mod.name:
                self._analyse_symbol(mod, sid)

    def _self_info(self, sid: str):
        """(self_name, class_id) for methods and functions nested inside them."""
        sym = self.symbols[sid]
        node = self.sym_node[sid]
        if sym["kind"] == "method":
            deco = {_deco_name(d).split(".")[-1] for d in node.decorator_list}
            args = node.args.posonlyargs + node.args.args
            if "staticmethod" in deco or not args:
                return None, sym["parent"]
            return args[0].arg, sym["parent"]
        if sym["kind"] == "function" and sym["parent"] and self.symbols[sym["parent"]]["kind"] in ("method", "function"):
            s, c = self._self_info(sym["parent"])
            if s and s not in {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}:
                return s, c
        return None, None

    def _ctx_for(self, mod: Mod, sid: str) -> dict:
        sym = self.symbols[sid]
        chain = self._chain(sid) if sym["kind"] != "module" else []
        self_name, class_id = self._self_info(sid) if sym["kind"] in ("method", "function") else (None, None)
        return {"mod": mod, "chain": chain, "sid": sid, "self": self_name, "class": class_id}

    def _prepass(self) -> None:
        """Whole-repo facts needed before any edge is classified: subclasses, attribute rebinding, patched modules."""
        for cid, sym in self.symbols.items():
            if sym["kind"] != "class":
                continue
            mod = self.mods[sym["module"]]
            pctx = {"mod": mod, "chain": self._chain(sym["parent"])}
            for b in self.sym_node[cid].bases:
                r = self._resolve_expr(b, pctx)
                if r and r[0] == "sym" and self.symbols[r[1]]["kind"] == "class":
                    self.sub_index.setdefault(r[1], set()).add(cid)
            self.attr_defs.setdefault(cid, set()).update(self.class_vars.get(cid, ()))
        for sid, sym in self.symbols.items():
            mod = self.mods[sym["module"]]
            ctx = self._ctx_for(mod, sid)
            for n in walk_scope(self.sym_node[sid].body):
                if not (isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del))):
                    continue
                if isinstance(n.value, ast.Name) and ctx["self"] and n.value.id == ctx["self"] and ctx["class"]:
                    self.attr_defs.setdefault(ctx["class"], set()).add(n.attr)
                    continue
                r = self._resolve_expr(n.value, ctx)
                if r and r[0] == "module":
                    self.patched.add((r[1], n.attr))
                elif r and r[0] == "sym" and self.symbols[r[1]]["kind"] == "class":
                    self.attr_defs.setdefault(r[1], set()).add(n.attr)

    def _ancestors(self, cid: str) -> set:
        out, stack = set(), [cid]
        node_ctx = lambda c: {"mod": self.mods[self.symbols[c]["module"]], "chain": self._chain(self.symbols[c]["parent"])}
        while stack:
            c = stack.pop()
            for b in self.sym_node[c].bases:
                r = self._resolve_expr(b, node_ctx(c))
                if r and r[0] == "sym" and self.symbols[r[1]]["kind"] == "class" and r[1] not in out:
                    out.add(r[1])
                    stack.append(r[1])
        return out

    def _descendants(self, cid: str) -> set:
        out, stack = set(), [cid]
        while stack:
            for c in self.sub_index.get(stack.pop(), ()):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out

    def _attr_shadowed(self, cid: str, attr: str) -> bool:
        return any(attr in self.attr_defs.get(c, ()) for c in {cid} | self._ancestors(cid))

    def _analyse_symbol(self, mod: Mod, sid: str) -> None:
        sym = self.symbols[sid]
        node = self.sym_node[sid]
        ctx = self._ctx_for(mod, sid)
        chain = ctx["chain"]
        scope = chain[-1] if chain else Scope()
        in_module = sym["kind"] == "module"
        body = node.body

        def module_var(name: str, c=ctx):
            """State id when `name` is a module-level variable of this module visible from here."""
            if in_module:
                return f"{mod.name}:{name}" if f"{mod.name}:{name}" in self.state else None
            for sc in reversed(c["chain"]):
                if name in sc.globals_decl:
                    break
                if name in sc.params or name in sc.vars or name in sc.defs or name in sc.imports or name in sc.nonlocals:
                    return None
            r = self._lookup_name(name, c)
            return r[2] if r[0] == "var" and len(r) > 2 else None

        def state_of(expr) -> str | None:
            """State id of a module-level variable named by `expr` (Name or alias.NAME), else None."""
            if isinstance(expr, ast.Name):
                return module_var(expr.id)
            if isinstance(expr, ast.Attribute):
                r = self._resolve_expr(expr, ctx)
                if r and r[0] == "var" and len(r) > 2:
                    return r[2]
            return None

        def add_write(kind, target, n):
            self.writes.append({"symbol": sid, "kind": kind, "target": target, "path": mod.path,
                                "start": n.lineno, "end": getattr(n, "end_lineno", n.lineno) or n.lineno})

        read_ids: dict[str, int] = {}
        for n in walk_scope(body):
            if isinstance(n, ast.Call):
                self._call(n.func, n, ctx, sid, mod)
                if isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS:
                    st = state_of(n.func.value)
                    if st:
                        add_write("container_mutation", st, n)
            elif _def_nodes(n):
                for d in n.decorator_list:
                    if not isinstance(d, ast.Call):
                        self._call(d, d, ctx, sid, mod, prefix="@")
            elif isinstance(n, ast.Global):
                for nm in n.names:
                    add_write("global_decl", f"{mod.name}:{nm}", n)
            elif isinstance(n, ast.Nonlocal):
                parent = sym["parent"]
                for nm in n.names:
                    add_write("nonlocal_decl", f"{parent}${nm}", n)
            elif isinstance(n, ast.Name):
                if isinstance(n.ctx, (ast.Store, ast.Del)):
                    if n.id in scope.globals_decl and not in_module:
                        add_write("global_write", f"{mod.name}:{n.id}", n)
                    elif n.id in scope.nonlocals and not in_module:
                        add_write("nonlocal_write", f"{sym['parent']}${n.id}", n)
                elif not in_module:
                    st = module_var(n.id)
                    if st:
                        read_ids.setdefault(st, n.lineno)
            elif isinstance(n, ast.Attribute):
                if isinstance(n.ctx, (ast.Store, ast.Del)) and isinstance(n.value, ast.Name) and ctx["self"] and n.value.id == ctx["self"] and ctx["class"]:
                    add_write("attr_write", f"{ctx['class']}#{n.attr}", n)
                elif isinstance(n.ctx, ast.Load) and not in_module:
                    r = self._resolve_expr(n, ctx)
                    if r and r[0] == "var" and len(r) > 2 and r[2]:
                        read_ids.setdefault(r[2], n.lineno)
            elif isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)):
                st = state_of(n.value)
                if st:
                    add_write("container_mutation", st, n)
        if sym["kind"] == "class":
            for nm in sorted(self.class_vars.get(sid, ())):
                line = next((x.lineno for x in walk_scope(body) if isinstance(x, ast.Name) and x.id == nm and isinstance(x.ctx, ast.Store)), sym["start"])
                self.writes.append({"symbol": sid, "kind": "class_attr", "target": f"{sid}#{nm}", "path": mod.path, "start": line, "end": line})
        if read_ids:
            self.reads[sid] = read_ids

    def _record(self, ctx, sid, mod, node, text, kind, target=None, candidates=(), code=None, reason=None):
        key = (sid, text, node.lineno, getattr(node, "col_offset", 0), kind)
        if key in self._seen_edges:
            return
        self._seen_edges.add(key)
        cands = sorted(set(candidates))
        trunc = len(cands) > MAX_CANDIDATES
        self.edges.append({
            "caller": sid, "text": text, "kind": kind, "target": target, "candidates": cands[:MAX_CANDIDATES],
            "candidates_truncated": trunc, "reason_code": code, "reason": reason,
            "path": mod.path, "start": node.lineno, "end": getattr(node, "end_lineno", node.lineno) or node.lineno,
        })

    def _decorator_transparent(self, d, parent: str, mod: Mod) -> bool:
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute) and f.attr in PROPERTY_ACCESSORS and isinstance(f.value, ast.Name) \
                and self.symbols[parent]["kind"] == "class":
            return any(isinstance(x, ast.Name) and x.id == "property" and self._lookup_name("property", {"mod": mod, "chain": []})[0] == "builtin"
                       for m in self.members[parent].get(f.value.id, ()) for x in self.sym_node[m].decorator_list)
        ctx = {"mod": mod, "chain": self._chain(parent) if self.symbols[parent]["kind"] != "module" else []}
        r = self._resolve_expr(f, ctx)
        if r is None:
            return False
        return (r[0] == "builtin" and r[1] in TRANSPARENT_BUILTINS) or (r[0] == "external" and r[1] in TRANSPARENT_QUALIFIED)

    def _wrapped(self, target_id: str):
        """Reason string when calls to this symbol may not reach it because of a decorator, else None."""
        sym = self.symbols[target_id]
        node = self.sym_node[target_id]
        mod = self.mods[sym["module"]]
        bad = [_unparse(d) for d in node.decorator_list if not self._decorator_transparent(d, sym["parent"], mod)]
        return f"decorated with {', '.join('@' + b for b in bad)}, which may wrap or replace it" if bad else None

    def _call(self, f, node, ctx, sid, mod, prefix=""):
        text = prefix + _unparse(f)
        if isinstance(f, (ast.Name, ast.Attribute)):
            root = f
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(f, ast.Attribute) and isinstance(root, ast.Call) and isinstance(root.func, ast.Name) and root.func.id == "super":
                return self._super_call(f, node, ctx, sid, mod, text)
            if isinstance(f, ast.Attribute) and isinstance(root, ast.Name) and ctx["self"] and root.id == ctx["self"] and ctx["class"] \
                    and isinstance(f.value, ast.Name):
                ids, unknown = self._member(ctx["class"], f.attr)
                return self._finish_member(ids, f.attr, node, ctx, sid, mod, text, recv=ctx["class"])
            r = self._resolve_expr(f, ctx)
            if r is None:  # attribute of a non-name expression
                if isinstance(root, (ast.Constant, ast.JoinedStr, ast.List, ast.Dict, ast.Set, ast.Tuple, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                    self.external_calls += 1
                    return
                return self._syntactic(f.attr, node, ctx, sid, mod, text)
            return self._finish(r, f, node, ctx, sid, mod, text)
        if isinstance(f, ast.Call):
            inner = f.func
            if isinstance(inner, ast.Name) and inner.id == "getattr":
                return self._record(ctx, sid, mod, node, text, "unresolved", code="getattr_result", reason="call of the result of getattr: callee chosen at runtime")
            return self._record(ctx, sid, mod, node, text, "unresolved", code="call_of_call", reason="call of a call result: callee is a runtime value")
        if isinstance(f, ast.Subscript):
            return self._record(ctx, sid, mod, node, text, "unresolved", code="subscript_call", reason="call of an item looked up at runtime")
        if isinstance(f, ast.Lambda):
            return self._record(ctx, sid, mod, node, text, "unresolved", code="lambda_call", reason="call of a lambda expression")
        return self._record(ctx, sid, mod, node, text, "unresolved", code="computed_callee", reason=f"callee is a computed {type(f).__name__} expression")

    def _syntactic(self, attr, node, ctx, sid, mod, text):
        cands = self.methods_by_name.get(attr, [])
        self._record(ctx, sid, mod, node, text, "syntactic", candidates=cands,
                     reason=f"method {attr!r} on an object of unknown type; matched by name only")

    def _finish_member(self, ids, attr, node, ctx, sid, mod, text, recv=None):
        if len(ids) == 1 and recv:
            subs = self._descendants(recv)
            over = sorted({m for c in subs for m in self.members.get(c, {}).get(attr, ())})
            shadow = self._attr_shadowed(recv, attr) or any(attr in self.attr_defs.get(c, ()) for c in subs)
            if over or shadow:
                why = (f"overridden in subclass(es) {', '.join(self.symbols[m]['parent'] for m in over)}" if over else
                       f"{attr!r} is also assigned as an instance/class attribute, which hides the method")
                return self._record(ctx, sid, mod, node, text, "syntactic", candidates=ids + over,
                                    reason=f"{text}: {why}; the receiver's runtime class decides the callee")
        if len(ids) == 1:
            return self._emit_symbol(ids[0], node, ctx, sid, mod, text)
        if len(ids) > 1:
            return self._record(ctx, sid, mod, node, text, "unresolved", candidates=ids, code="multiple_bindings",
                                reason=f"{attr!r} is defined {len(ids)} times on the class")
        return self._syntactic(attr, node, ctx, sid, mod, text)

    def _super_call(self, f, node, ctx, sid, mod, text):
        if not ctx["class"]:
            return self._syntactic(f.attr, node, ctx, sid, mod, text)
        ids, _ = self._member(ctx["class"], f.attr, skip_self=True)
        return self._finish_member(ids, f.attr, node, ctx, sid, mod, text)

    def _emit_symbol(self, tid, node, ctx, sid, mod, text):
        wrapped = self._wrapped(tid)
        if wrapped:
            return self._record(ctx, sid, mod, node, text, "unresolved", candidates=[tid], code="decorator_wrapped", reason=wrapped)
        self._record(ctx, sid, mod, node, text, "resolved", target=tid)

    def _finish(self, r, f, node, ctx, sid, mod, text):
        k = r[0]
        if k == "sym":
            return self._emit_symbol(r[1], node, ctx, sid, mod, text)
        if k == "var":
            if isinstance(f, ast.Name):
                return self._record(ctx, sid, mod, node, text, "unresolved", code="call_through_variable",
                                    reason=f"call through {r[1]} {f.id!r}: callee is a runtime value")
            return self._syntactic(f.attr, node, ctx, sid, mod, text)
        if k == "attr":  # attribute that is not a known member (instance attribute, dynamic member, ...)
            if len(r) > 2 and r[2][0] == "var" and r[2][2] in self.state and self.state[r[2][2]]["mutable_container"] and r[1] in MUTATORS:
                self.external_calls += 1  # list/dict/set method on a module-level container
                return
            return self._syntactic(f.attr, node, ctx, sid, mod, text)
        if k == "builtin":
            if r[1] in DYNAMIC_BUILTINS:
                code, why = DYNAMIC_BUILTINS[r[1]]
                return self._record(ctx, sid, mod, node, text, "unresolved", code=code, reason=why)
            self.external_calls += 1
            return
        if k == "external":
            if r[1] in DYNAMIC_EXTERNAL:
                code, why = DYNAMIC_EXTERNAL[r[1]]
                return self._record(ctx, sid, mod, node, text, "unresolved", code=code, reason=why)
            self.external_calls += 1
            return
        if k == "module":
            return self._record(ctx, sid, mod, node, text, "unresolved", code="call_of_module", reason=f"module {r[1]!r} is called")
        if k == "unres":
            return self._record(ctx, sid, mod, node, text, "unresolved", candidates=r[3] if len(r) > 3 else (), code=r[1], reason=r[2])
        self._record(ctx, sid, mod, node, text, "unresolved", code="computed_callee", reason="unclassified callee")

    # -- output

    def _result(self, files: list[str], failures: list[dict]) -> dict:
        for sid, parts in self._state_parts.items():
            self.state[sid]["value_hash"] = hashlib.sha256("\n".join(parts).encode("utf-8", "surrogatepass")).hexdigest()
        edges = sorted(self.edges, key=lambda e: (e["path"], e["start"], e["caller"], e["text"], e["kind"]))
        by_reason: dict[str, int] = {}
        for e in edges:
            if e["kind"] == "unresolved":
                by_reason[e["reason_code"]] = by_reason.get(e["reason_code"], 0) + 1
        counts = {k: sum(1 for s in self.symbols.values() if s["kind"] == k) for k in ("module", "class", "function", "method")}
        counts["symbols"] = len(self.symbols)
        limits = {
            "files_total": len(files),
            "files_parsed": sum(1 for m in self.mods.values() if m.tree is not None),
            "parse_failures": sorted(failures, key=lambda f: f["path"]),
            "resolved_edges": sum(1 for e in edges if e["kind"] == "resolved"),
            "syntactic_edges": sum(1 for e in edges if e["kind"] == "syntactic"),
            "unresolved_edges": sum(1 for e in edges if e["kind"] == "unresolved"),
            "unresolved_by_reason": dict(sorted(by_reason.items())),
            "external_calls_not_recorded": self.external_calls,
            "hash_failures": sorted(self.hash_failures),
            "complete_call_graph": False,
            "notes": NOTES,
        }
        return {
            "schema": SCHEMA,
            "root": self.source.label,
            "tool": {"name": "factory.structure", "method": "python ast (stdlib)", "python": sys.version.split()[0]},
            "files": {m.path: {"module": m.name, "status": "failed" if m.error else "parsed", "lines": m.nlines} for m in self.mods.values()},
            "modules": {m.name: {"path": m.path, "is_package": m.is_pkg, "status": "failed" if m.error else "parsed",
                                 "imports": m.imports} for m in sorted(self.mods.values(), key=lambda m: m.name)},
            "symbols": dict(sorted(self.symbols.items())),
            "edges": edges,
            "state": dict(sorted(self.state.items())),
            "writes": sorted(self.writes, key=lambda w: (w["path"], w["start"], w["symbol"], w["kind"], w["target"])),
            "reads": {k: sorted(v) for k, v in sorted(self.reads.items())},
            "read_lines": {k: dict(sorted(v.items())) for k, v in sorted(self.reads.items())},
            "counts": counts,
            "limits": limits,
        }


def extract(source, exclude=(), repo=None) -> dict:
    """Extract structure from a directory path, a `git:<rev>` spec (with repo=) or a source object."""
    return Extractor(make_source(source, repo, exclude)).run()
