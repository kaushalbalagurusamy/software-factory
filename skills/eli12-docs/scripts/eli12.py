#!/usr/bin/env python3
"""eli12: keep plain-English ("explain it like I'm 12") docs for every Python module honest.

Three commands: scaffold (write a skeleton with the who-uses-who lines computed from the code),
check (find missing, stale, too-dense or jargon-filled entries), index (list every doc page).
Standard library only, Python 3.9+, no network, no model calls.
"""
import argparse
import ast
import builtins
import hashlib
import json
import os
import re
import subprocess
import sys

DOCDIR = "docs/eli12"
SKIP_DOCS = ("INDEX.md", "GLOSSARY.md")
DEFAULT_IGNORE = {".venv", "venv", "node_modules", ".git", "evals", "__pycache__", ".tox", "site-packages"}
LABELS = ["What it does", "Expects", "Gives back", "Used by", "Depends on", "Watch out"]
REQUIRED = LABELS[:5]
LABEL_RE = re.compile(r"^\*\*(%s):\*\*(.*)$" % "|".join(LABELS))
SIG_RE = re.compile(r"<!--\s*sig:([0-9a-f]{8})\s*-->")
PARAM_RE = re.compile(r"^`?[*\w]+`? \(.+\): \S")
LINENO_RE = re.compile(r"\(([^()]*?):\d+\)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- source model

class Sym:
    def __init__(self, mod, qual, path, node, cls=None, is_static=False):
        self.mod, self.qual, self.path, self.node = mod, qual, path, node
        self.line = node.lineno
        self.cls = cls
        self.is_static = is_static
        self.is_class = isinstance(node, ast.ClassDef)
        self.public = not any(p.startswith("_") for p in qual.split("."))

    @property
    def key(self):
        return (self.mod, self.qual)

    def shown(self):
        return "%s.%s (%s:%d)" % (self.mod, self.qual, self.path, self.line)


class Module:
    def __init__(self, path, name, is_pkg):
        self.path, self.name, self.is_pkg = path, name, is_pkg
        self.tree = None
        self.error = None
        self.syms = []


def _ignored(root, extra_include):
    return DEFAULT_IGNORE - set(extra_include or ())


def discover(root, include=None):
    """Return sorted relative posix paths of .py files under root, skipping ignored dirs."""
    ign = _ignored(root, include)
    out = []
    for dp, dns, fns in os.walk(root, followlinks=False):
        dns[:] = sorted(d for d in dns if d not in ign and not os.path.islink(os.path.join(dp, d)))
        for fn in fns:
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/"))
    return sorted(out)


def inside(root, p):
    r = os.path.realpath(root)
    q = os.path.realpath(p)
    return q == r or q.startswith(r + os.sep)


def modname(rel):
    parts = rel[:-3].split("/")
    is_pkg = parts[-1] == "__init__"
    if is_pkg and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts), is_pkg


def load_module(root, rel):
    name, is_pkg = modname(rel)
    m = Module(rel, name, is_pkg)
    full = os.path.join(root, rel)
    try:
        if not inside(root, full):
            raise ValueError("file resolves outside the root")
        with open(full, "rb") as f:
            src = f.read().decode("utf-8")
        m.tree = ast.parse(src, filename=rel)
    except SyntaxError as e:
        m.error = "syntax error: %s" % e.msg
        m.err_line = e.lineno or 1
    except (OSError, UnicodeDecodeError, ValueError, RecursionError, MemoryError) as e:
        m.error = "cannot read: %s" % (e,)
    if m.tree is not None:
        for node in m.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m.syms.append(Sym(name, node.name, rel, node))
            elif isinstance(node, ast.ClassDef):
                m.syms.append(Sym(name, node.name, rel, node))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        st = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in sub.decorator_list)
                        m.syms.append(Sym(name, node.name + "." + sub.name, rel, sub, cls=node.name, is_static=st))
    return m


def public_syms(m):
    out = []
    for s in m.syms:
        if not s.public:
            continue
        if s.cls and s.node.name.startswith("_"):
            continue
        out.append(s)
    return out


def sig_hash(s, mods_syms):
    n = s.node
    if s.is_class:
        init = mods_syms.get((s.mod, s.qual + ".__init__"))
        text = "class|%s|%s" % (s.qual, ast.unparse(init.node.args) if init else "")
    else:
        text = "def|%s|%s|%s" % (s.qual, ast.unparse(n.args), ast.unparse(n.returns) if n.returns else "")
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def params_of(s, symmap):
    """List of (name, type) for the signature a caller sees."""
    node = s.node
    if s.is_class:
        init = symmap.get((s.mod, s.qual + ".__init__"))
        if not init:
            return []
        node, skip = init.node, True
    else:
        skip = bool(s.cls) and not s.is_static
    a = node.args
    out = []
    pos = list(a.posonlyargs) + list(a.args)
    for i, p in enumerate(pos):
        if i == 0 and skip:
            continue
        out.append((p.arg, ast.unparse(p.annotation) if p.annotation else "TODO"))
    if a.vararg:
        out.append(("*" + a.vararg.arg, ast.unparse(a.vararg.annotation) if a.vararg.annotation else "TODO"))
    for p in a.kwonlyargs:
        out.append((p.arg, ast.unparse(p.annotation) if p.annotation else "TODO"))
    if a.kwarg:
        out.append(("**" + a.kwarg.arg, ast.unparse(a.kwarg.annotation) if a.kwarg.annotation else "TODO"))
    return out


# ---------------------------------------------------------------- dependency graph

class Project:
    def __init__(self, root, include=None):
        self.root = root
        self.mods = {}
        for rel in discover(root, include):
            m = load_module(root, rel)
            self.mods[rel] = m
        self.symmap = {}
        self.byname = {}
        for m in self.mods.values():
            for s in m.syms:
                self.symmap[s.key] = s
        self.names = {m.name: m for m in self.mods.values() if m.tree is not None}
        self.suffix = {}
        for n in self.names:
            parts = n.split(".")
            for i in range(len(parts)):
                self.suffix.setdefault(".".join(parts[i:]), set()).add(n)
        self.methods = {}
        for s in self.symmap.values():
            if s.cls:
                self.methods.setdefault(s.qual.split(".")[-1], []).append(s)
        self._tables = {}
        self.certain, self.maybe, self.unres = {}, {}, {}
        self._edges()

    def resolve_mod(self, name):
        if name in self.names:
            return name
        c = self.suffix.get(name, ())
        return next(iter(c)) if len(c) == 1 else None

    def table(self, m):
        if m.name in self._tables:
            return self._tables[m.name]
        t = {}
        pkg = m.name.split(".") if m.is_pkg else m.name.split(".")[:-1]
        for n in ast.walk(m.tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.asname:
                        r = self.resolve_mod(a.name)
                        t[a.asname] = ("mod", r) if r else ("ext",)
                    else:
                        first = a.name.split(".")[0]
                        r = self.resolve_mod(first)
                        t[first] = ("mod", r) if r else ("ext",)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg[: len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                    full = ".".join(base + ([n.module] if n.module else []))
                else:
                    full = n.module or ""
                tgt = self.resolve_mod(full) if full else None
                for a in n.names:
                    k = a.asname or a.name
                    if tgt and (tgt, a.name) in self.symmap:
                        t[k] = ("sym", tgt, a.name)
                    elif tgt and self.resolve_mod(tgt + "." + a.name):
                        t[k] = ("mod", self.resolve_mod(tgt + "." + a.name))
                    elif tgt:
                        t[k] = ("unk",)
                    else:
                        sub = self.resolve_mod(full + "." + a.name) if full else None
                        t[k] = ("mod", sub) if sub else ("ext",)
        for s in m.syms:
            if not s.cls:
                t[s.qual] = ("sym", m.name, s.qual)
        self._tables[m.name] = t
        return t

    def _resolve(self, e, m, cls, locs, selfname):
        if isinstance(e, ast.Name):
            if cls and e.id == selfname:
                return ("self", cls)
            if e.id in locs:
                return None
            r = self.table(m).get(e.id)
            return None if r == ("unk",) else r
        if isinstance(e, ast.Attribute):
            b = self._resolve(e.value, m, cls, locs, selfname)
            if not b:
                return None
            if b[0] == "mod":
                if (b[1], e.attr) in self.symmap:
                    return ("sym", b[1], e.attr)
                sub = self.resolve_mod(b[1] + "." + e.attr)
                return ("mod", sub) if sub else None
            if b[0] == "sym" and (b[1], b[2] + "." + e.attr) in self.symmap:
                return ("sym", b[1], b[2] + "." + e.attr)
            if b[0] == "self" and (m.name, b[1] + "." + e.attr) in self.symmap:
                return ("sym", m.name, b[1] + "." + e.attr)
        return None

    def _refs(self, node, m, cls, selfname):
        locs = set()
        for n in ast.walk(node):
            if isinstance(n, ast.arg):
                locs.add(n.arg)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                locs.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not node:
                locs.add(n.name)
        cert, may, unres = {}, {}, {}

        def put(d, k, n):
            d[k] = min(d.get(k, n.lineno), n.lineno)
        called = {id(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                r = self._resolve(n, m, cls, locs, selfname)
                if r and r[0] == "sym":
                    put(cert, (r[1], r[2]), n)
                elif (r is None or r == ("unk",)) and id(n) in called and n.id not in locs \
                        and not hasattr(builtins, n.id) and not (cls and n.id == selfname):
                    put(unres, n.id, n)  # called, but nothing in the project (or imports) explains it
            elif isinstance(n, ast.Attribute):
                r = self._resolve(n, m, cls, locs, selfname)
                if r and r[0] == "sym":
                    put(cert, (r[1], r[2]), n)
                    continue
                b = self._resolve(n.value, m, cls, locs, selfname)
                if id(n) in called and (b is None or (b[0] == "self" and r is None)):
                    for s in self.methods.get(n.attr, ()):
                        put(may, s.key, n)
        return cert, may, unres

    def _edges(self):
        for m in self.mods.values():
            if m.tree is None:
                continue
            for s in m.syms:
                selfname = None
                if s.cls and not s.is_static:
                    pos = list(s.node.args.posonlyargs) + list(s.node.args.args)
                    selfname = pos[0].arg if pos else None
                cert, may, unres = self._refs(s.node, m, s.cls, selfname)
                self._store(s.key, cert, may, unres)
            top = ast.Module(body=[n for n in m.tree.body if not isinstance(
                n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])
            cert, may, unres = self._refs(top, m, None, None)
            self._store((m.name, "<module>"), cert, may, unres, line_path=m.path)

    def _store(self, src, cert, may, unres, line_path=None):
        def inside_src(t):
            return t[0] == src[0] and (t[1] == src[1] or t[1].startswith(src[1] + "."))
        cert = {t: n for t, n in cert.items() if not inside_src(t)}
        may = {t: n for t, n in may.items() if not inside_src(t) and t not in cert}
        self.certain[src] = cert
        self.maybe[src] = may
        self.unres[src] = unres
        if line_path:
            self.symmap[src] = _ModSym(src, line_path)

    def lists(self, s):
        """(used_by, depends_on): Used by cites call sites, Depends on cites definitions."""
        def shown(key, path, line, tag=""):
            return "%s.%s (%s:%d)%s" % (key[0], key[1], path, line, tag)
        dep = [shown(t, self.symmap[t].path, self.symmap[t].line) for t in self.certain.get(s.key, {}) if t in self.symmap]
        dep += [shown(t, self.symmap[t].path, self.symmap[t].line, " (maybe)")
                for t in self.maybe.get(s.key, {}) if t in self.symmap]
        dep += ["%s (%s:%d) (maybe)" % (k, s.path, n) for k, n in self.unres.get(s.key, {}).items()]
        used = []
        for src, targets in self.certain.items():
            if s.key in targets and src in self.symmap:
                used.append(shown(src, self.symmap[src].path, targets[s.key]))
        for src, targets in self.maybe.items():
            if s.key in targets and src in self.symmap:
                used.append(shown(src, self.symmap[src].path, targets[s.key], " (maybe)"))
        return sorted(used), sorted(dep)


class _ModSym:
    def __init__(self, key, path):
        self.key, self.path = key, path

    def shown(self):
        return "%s.<module> (%s:1)" % (self.key[0], self.path)


# ---------------------------------------------------------------- doc parsing / rendering

class Entry:
    def __init__(self, name, line):
        self.name, self.line = name, line
        self.sig = None
        self.sig_line = line
        self.labels = []  # [label, lineno, [raw lines]]
        self.stray = []   # (lineno, text)
        self.lines = []   # (lineno, text) every body line


class Doc:
    def __init__(self):
        self.header = None
        self.purpose = None      # (lineno, text)
        self.entries = []
        self.lines = []


def parse_doc(text):
    d = Doc()
    d.lines = text.split("\n")
    L = d.lines
    i = 0
    if L and L[0].startswith("# "):
        d.header = L[0][2:].strip()
    i = 1
    while i < len(L) and not L[i].strip():
        i += 1
    if i < len(L) and not L[i].startswith("## "):
        start = i
        while i < len(L) and L[i].strip() and not L[i].startswith("## "):
            i += 1
        d.purpose = (start + 1, " ".join(x.strip() for x in L[start:i]))
    cur = None
    for n in range(i, len(L)):
        line = L[n]
        if line.startswith("## "):
            cur = Entry(line[3:].strip(), n + 1)
            d.entries.append(cur)
            continue
        if cur is None:
            continue
        cur.lines.append((n + 1, line))
        if not line.strip():
            continue
        sm = SIG_RE.search(line)
        if sm and cur.sig is None:
            cur.sig, cur.sig_line = sm.group(1), n + 1
            continue
        lm = LABEL_RE.match(line)
        if lm:
            cur.labels.append([lm.group(1), n + 1, [lm.group(2).strip()]])
        elif cur.labels:
            cur.labels[-1][2].append(line)
        else:
            cur.stray.append((n + 1, line))
    return d


def items_of(raw):
    """Bullet/inline items of a labelled value (continuation lines starting with space are dropped)."""
    out = []
    first = raw[0].strip()
    if first:
        out.append(first)
    for ln in raw[1:]:
        if ln[:1] in (" ", "\t"):
            continue
        s = ln.strip()
        if s[:2] in ("- ", "* "):
            s = s[2:].strip()
        if s:
            out.append(s)
    return out


def norm_item(s):
    return LINENO_RE.sub(r"(\1)", s).strip()


def render_labelled(label, raw):
    first = raw[0]
    head = "**%s:**%s" % (label, (" " + first) if first else "")
    return "\n".join([head] + raw[1:])


def render_list(label, items):
    if not items:
        return "**%s:** nothing" % label
    return "\n".join(["**%s:**" % label] + ["- " + x for x in items])


def scaffold_entry(proj, s, old):
    used, dep = proj.lists(s)
    ps = params_of(s, proj.symmap)
    human = {}
    if old:
        for lab, _, raw in old.labels:
            human[lab] = raw
    blocks = ["## " + s.qual, "<!-- sig:%s -->" % sig_hash(s, proj.symmap), ""]
    if "What it does" in human:
        blocks.append(render_labelled("What it does", human["What it does"]))
    else:
        blocks.append("**What it does:** TODO")
    blocks.append("")
    if "Expects" in human:
        blocks.append(render_labelled("Expects", human["Expects"]))
    elif ps:
        blocks.append("\n".join(["**Expects:**"] + ["- %s (%s): TODO" % p for p in ps]))
    else:
        blocks.append("**Expects:** nothing")
    blocks.append("")
    if "Gives back" in human:
        blocks.append(render_labelled("Gives back", human["Gives back"]))
    elif s.is_class:
        blocks.append("**Gives back:** %s: TODO" % s.qual)
    elif s.node.returns is not None and ast.unparse(s.node.returns) == "None":
        blocks.append("**Gives back:** nothing")
    elif s.node.returns is not None:
        blocks.append("**Gives back:** %s: TODO" % ast.unparse(s.node.returns))
    else:
        blocks.append("**Gives back:** TODO: TODO")
    blocks += ["", render_list("Used by", used), "", render_list("Depends on", dep), ""]
    if "Watch out" in human:
        blocks += [render_labelled("Watch out", human["Watch out"]), ""]
    return blocks


def doc_rel(m):
    return "%s/%s.md" % (DOCDIR, m.name)


def scaffold_module(proj, m):
    """Return (doc relpath, new text) for module m."""
    rel = doc_rel(m)
    full = os.path.join(proj.root, rel)
    old = None
    if os.path.exists(full):
        if not inside(proj.root, full):
            raise UsageError("%s resolves outside the root" % rel)
        with open(full, encoding="utf-8") as f:
            old = parse_doc(f.read())
    olde = {e.name: e for e in old.entries} if old else {}
    out = ["# " + m.path, ""]
    out.append(old.purpose[1] if old and old.purpose else "TODO")
    out.append("")
    seen = set()
    for s in public_syms(m):
        seen.add(s.qual)
        out += scaffold_entry(proj, s, olde.get(s.qual))
    for e in (old.entries if old else []):
        if e.name not in seen:  # keep orphans visible so check reports them
            out += ["## " + e.name] + [t for _, t in e.lines]
    return rel, "\n".join(out).rstrip("\n") + "\n"


def write_text(root, rel, text):
    """Write root/rel without ever following a symlink (any component) or leaving the root."""
    full = os.path.join(root, rel)
    d = os.path.dirname(full)
    cur = os.path.abspath(root)
    for part in os.path.relpath(full, cur).split(os.sep):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise UsageError("refusing to write through a symlink: %s" % rel)
    if not inside(root, d):
        raise UsageError("%s resolves outside the root" % rel)
    os.makedirs(d, exist_ok=True)
    tmp = "%s.tmp%d" % (full, os.getpid())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if os.path.islink(full):
            raise UsageError("refusing to write through a symlink: %s" % rel)
        os.replace(tmp, full)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def doc_files(root):
    d = os.path.join(root, DOCDIR)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".md") and f not in SKIP_DOCS)


def read_doc(root, fn):
    p = os.path.join(root, DOCDIR, fn)
    if not inside(root, p):
        raise ValueError("resolves outside the root")
    with open(p, "rb") as f:
        return f.read().decode("utf-8")


def build_index(root):
    rows, mapping, problems = [], {}, []
    for fn in doc_files(root):
        try:
            d = parse_doc(read_doc(root, fn))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            problems.append("%s/%s: unreadable: %s" % (DOCDIR, fn, e))
            continue
        if not d.header:
            problems.append("%s/%s: first line is not '# <module path>'" % (DOCDIR, fn))
            continue
        mapping[d.header] = "%s/%s" % (DOCDIR, fn)
        rows.append((d.header, d.purpose[1] if d.purpose else "TODO", len(d.entries)))
    rows.sort()
    md = ["# ELI12 documentation index", "", "| Module | What it is for | Documented symbols |", "| --- | --- | --- |"]
    for h, p, c in rows:
        md.append("| [%s](%s) | %s | %d |" % (h, mapping[h].split("/")[-1], p.replace("|", "\\|"), c))
    js = json.dumps(mapping, indent=2, sort_keys=True) + "\n"
    return "\n".join(md) + "\n", js, problems


def write_index(root, md=True):
    mdt, js, problems = build_index(root)
    if md:
        write_text(root, DOCDIR + "/INDEX.md", mdt)
    write_text(root, DOCDIR + "/index.json", js)
    return problems


# ---------------------------------------------------------------- check

def jargon_terms(root):
    p = os.path.join(root, DOCDIR, "jargon.txt")
    if not os.path.isfile(p):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "jargon.txt")
    if p.startswith(os.path.join(root, DOCDIR)) and not inside(root, p):
        raise UsageError("jargon list resolves outside the root")
    try:
        with open(p, encoding="utf-8") as f:
            return [x.strip() for x in f.read().splitlines() if x.strip() and not x.lstrip().startswith("#")]
    except (OSError, UnicodeDecodeError) as e:
        raise UsageError("cannot read jargon list %s: %s" % (p, e))


def glossary_terms(root):
    p = os.path.join(root, DOCDIR, "GLOSSARY.md")
    if not os.path.exists(p):
        return set()
    try:
        text = read_doc(root, "GLOSSARY.md")
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise UsageError("cannot read GLOSSARY.md: %s" % (e,))
    return [re.sub(r"^[#>*\-\s`_]+", "", ln).lower() for ln in text.splitlines()]


def defined(term, gloss):
    t = term.lower()
    rx = re.compile(r"^" + re.escape(t) + r"(?![\w-])")
    return any(rx.match(g) for g in gloss)


def norm_set(items):
    return {norm_item(x) for x in items if norm_item(x).lower() != "nothing"}


def check_doc(proj, m, jargon, gloss, add):
    rel = doc_rel(m)
    pubs = {s.qual: s for s in public_syms(m)}
    full = os.path.join(proj.root, rel)
    if not os.path.exists(full):
        for s in pubs.values():
            add(m.path, s.line, "missing-entry", "no doc entry for %s (expected in %s)" % (s.qual, rel))
        return
    try:
        doc = parse_doc(read_doc(proj.root, "%s.md" % m.name))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        add(rel, 1, "unparseable", "cannot read doc: %s" % (e,))
        return
    if doc.header != m.path:
        add(rel, 1, "format", "first line must be '# %s'" % m.path)
    if not doc.purpose:
        add(rel, 2, "format", "missing one-sentence purpose paragraph after the title")
    starts = [(e.line, e.name) for e in doc.entries]

    def owner(n):
        o = [nm for ln0, nm in starts if ln0 <= n]
        return (o[-1] + ": ") if o else ""
    for n, ln in enumerate(doc.lines, 1):
        if len(ln) > 160:
            add(rel, n, "too-long", "%sline is %d characters (limit 160)" % (owner(n), len(ln)))
        if "TODO" in ln:
            add(rel, n, "todo", "%sunfilled TODO" % owner(n))
    prose = []
    if doc.purpose:
        prose.append((doc.purpose[0], doc.purpose[1]))
    seen = set()
    for e in doc.entries:
        if e.name in seen:
            add(rel, e.line, "format", "duplicate entry %s" % e.name)
            continue
        seen.add(e.name)
        s = pubs.get(e.name)
        if s is None:
            add(rel, e.line, "orphan-entry", "%s no longer exists in %s" % (e.name, m.path))
        check_entry(proj, rel, e, s, add)
        for lab, ln, raw in e.labels:
            if lab in ("Used by", "Depends on"):
                continue
            for k, t in enumerate(["%s" % raw[0]] + raw[1:]):
                prose.append((ln + k, t))
    for q, s in pubs.items():
        if q not in seen:
            add(m.path, s.line, "missing-entry", "no doc entry for %s (expected in %s)" % (q, rel))
    reported = set()
    for ln, t in prose:
        t = CODE_SPAN_RE.sub(" ", t)
        for term in jargon:
            if term.lower() in reported:
                continue
            if re.search(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", t, re.I) and not defined(term, gloss):
                reported.add(term.lower())
                add(rel, ln, "jargon", "'%s' needs an entry in %s/GLOSSARY.md" % (term, DOCDIR))


def check_entry(proj, rel, e, s, add0):
    def add(path, line, code, msg):
        add0(path, line, code, msg if e.name in msg else "%s: %s" % (e.name, msg))

    for ln, t in e.stray:
        add(rel, ln, "format", "text before the first labelled line: %s" % t.strip()[:40])
    if e.sig is None:
        add(rel, e.line, "format", "missing '<!-- sig:xxxxxxxx -->' line")
    elif s is not None and e.sig != sig_hash(s, proj.symmap):
        add(rel, e.sig_line, "stale-signature", "stale: signature changed for %s" % e.name)
    names = [l[0] for l in e.labels]
    order = [n for n in LABELS if n in names]
    for r in REQUIRED:
        if r not in names:
            add(rel, e.line, "format", "%s: missing '**%s:**' line" % (e.name, r))
    if names != order or len(set(names)) != len(names):
        add(rel, e.line, "format", "%s: labelled lines must appear once each, in the order %s" % (e.name, ", ".join(LABELS)))
    lab = {l[0]: l for l in e.labels}
    if "What it does" in lab:
        _, ln, raw = lab["What it does"]
        text = " ".join(x.strip() for x in raw if x.strip())
        if not text:
            add(rel, ln, "format", "'What it does' is empty")
        elif len(text.split()) > 25 or re.search(r"[.!?](?=\s+[A-Z0-9\"'`(])", text):
            add(rel, ln, "too-long", "'What it does' must be one sentence of at most 25 words (%d words)" % len(text.split()))
    if "Expects" in lab:
        _, ln, raw = lab["Expects"]
        its = items_of(raw)
        if not its:
            add(rel, ln, "format", "'Expects' is empty; write the parameters or 'nothing'")
        elif not (len(its) == 1 and its[0].lower() in ("nothing", "todo")):
            for it in its:
                if not PARAM_RE.match(it) and it != "TODO":
                    add(rel, ln, "bad-param", "write '%s' as 'name (type): meaning'" % it[:50])
    if "Expects" in lab and s is not None:
        _, ln, raw = lab["Expects"]
        its = items_of(raw)
        want = params_of(s, proj.symmap)
        if its and all(PARAM_RE.match(i) or i.lower() in ("nothing", "todo") for i in its):
            got = []
            for i in its:
                mm = re.match(r"^`?([*\w]+)`? \((.+?)\): ", i)
                if mm:
                    got.append((mm.group(1), mm.group(2).strip()))
            bad = None
            if [n for n, _ in got] != [n for n, _ in want]:
                bad = "expected parameters (%s), the page lists (%s)" % (
                    ", ".join(n for n, _ in want) or "none", ", ".join(n for n, _ in got) or "nothing")
            else:
                for (n, t), (_, wt) in zip(got, want):
                    if wt != "TODO" and t != "TODO" and re.sub(r"\s+", "", t) != re.sub(r"\s+", "", wt):
                        bad = "parameter %s is %s in the code but %s on the page" % (n, wt, t)
                        break
            if bad:
                add(rel, ln, "format", "%s: Expects does not match the signature: %s" % (e.name, bad))
    if "Gives back" in lab and s is not None and not s.is_class:
        _, ln, raw = lab["Gives back"]
        t = " ".join(x.strip() for x in raw if x.strip())
        r = s.node.returns
        if r is not None and t != "TODO" and not t.startswith("TODO:"):
            ret = ast.unparse(r)
            dt = "nothing" if t.lower() == "nothing" else t.split(": ", 1)[0].strip()
            ok = (dt == "nothing" and ret == "None") or re.sub(r"\s+", "", dt) == re.sub(r"\s+", "", ret)
            if not ok and not (ret == "None" and dt == "None"):
                add(rel, ln, "format", "%s: Gives back does not match the signature: the code returns %s, the page says %s" % (e.name, ret, dt))
    if "Gives back" in lab:
        _, ln, raw = lab["Gives back"]
        t = " ".join(x.strip() for x in raw if x.strip())
        if not (t.lower() == "nothing" or t == "TODO" or re.match(r"^[^:]+: \S", t)):
            add(rel, ln, "format", "'Gives back' must be 'nothing' or 'type: meaning'")
    if s is not None:
        used, dep = proj.lists(s)
        for label, want in (("Used by", used), ("Depends on", dep)):
            if label in lab and norm_set(items_of(lab[label][2])) != norm_set(want):
                add(rel, lab[label][1], "stale-dependencies", "stale: dependencies changed (%s differs from the code)" % label)


def resolve_paths(root, paths):
    out = set()
    for p in paths:
        cand = p if os.path.isabs(p) else os.path.join(root, p)
        if not os.path.exists(cand) and os.path.exists(p):
            cand = p
        if not os.path.exists(cand):
            raise UsageError("path not found: %s" % p)
        if not inside(root, cand):
            raise UsageError("path is outside the root: %s" % p)
        rel = os.path.relpath(os.path.abspath(cand), os.path.abspath(root)).replace(os.sep, "/")
        out.add(rel)
    return out


def changed_files(root, ref):
    try:
        a = subprocess.run(["git", "diff", "--name-only", "--relative", ref, "--"], cwd=root,
                           capture_output=True, text=True, check=True).stdout
        b = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root,
                           capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise UsageError("git failed for --changed %s: %s" % (ref, getattr(e, "stderr", e) or e))
    return {x for x in (a + b).splitlines() if x}


def run_check(root, paths=None, changed=None, include=None):
    findings = []

    def add(path, line, code, msg):
        findings.append({"path": path, "line": max(1, int(line)), "code": code, "message": msg})

    jargon = jargon_terms(root)
    gloss = glossary_terms(root)
    proj = Project(root, include)
    scope = None
    full = True
    if paths:
        full = False
        sel = resolve_paths(root, paths)
        scope = {r for r in proj.mods if any(r == p or r.startswith(p.rstrip("/") + "/") or p == "." for p in sel)}
    if changed:
        full = False
        ch = changed_files(root, changed)
        mods = {r for r in proj.mods if r in ch}
        cnames = {proj.mods[r].name for r in mods}
        scope = (scope or set()) | mods
        for src, ts in list(proj.certain.items()) + list(proj.maybe.items()):
            if src[0] in proj.names and any(t[0] in cnames for t in ts):
                scope.add(proj.names[src[0]].path)
        for fn in doc_files(root):
            try:
                d = parse_doc(read_doc(root, fn))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            if d.header not in proj.mods:
                continue
            for e in d.entries:
                for lab in e.labels:
                    if lab[0] in ("Used by", "Depends on") and any(
                            ln.lstrip("- ").startswith(c + ".") for ln in lab[2] for c in cnames):
                        scope.add(d.header)
    for rel in sorted(proj.mods):
        if scope is not None and rel not in scope:
            continue
        m = proj.mods[rel]
        if m.error:
            add(m.path, getattr(m, "err_line", 1), "unparseable", m.error)
            continue
        check_doc(proj, m, jargon, gloss, add)
    if full:
        known = {doc_rel(m).split("/")[-1] for m in proj.mods.values() if m.tree is not None}
        bad = {m.name + ".md" for m in proj.mods.values() if m.tree is None}
        for fn in doc_files(root):
            if fn not in known and fn not in bad:
                add("%s/%s" % (DOCDIR, fn), 1, "orphan-entry", "doc page has no matching Python module")
    findings.sort(key=lambda f: (f["path"], f["line"], f["code"], f["message"]))
    return findings


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="eli12", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scaffold", "check", "index"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--include", action="append", default=[], metavar="DIRNAME",
                       help="scan a directory that is ignored by default (.venv, node_modules, .git, evals)")
        if name == "scaffold":
            p.add_argument("files", nargs="+", metavar="FILE")
        if name == "check":
            p.add_argument("--paths", nargs="+", default=None)
            p.add_argument("--changed", metavar="GITREF")
            p.add_argument("--json", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = os.path.abspath(a.root)
    try:
        if not os.path.isdir(root):
            raise UsageError("root is not a directory: %s" % a.root)
        if a.cmd == "check":
            fs = run_check(root, a.paths, a.changed, a.include)
            if a.json:
                print(json.dumps(fs, indent=2))
            else:
                for f in fs:
                    print("%(path)s:%(line)d: %(code)s: %(message)s" % f)
            return 1 if fs else 0
        if a.cmd == "index":
            for pr in write_index(root):
                print(pr, file=sys.stderr)
            return 0
        sel = resolve_paths(root, a.files)
        proj = Project(root, a.include)
        bad = 0
        for rel in sorted(sel):
            m = proj.mods.get(rel)
            if m is None:
                raise UsageError("not a Python file under the root (or ignored): %s" % rel)
            if m.error:
                print("%s:%d: unparseable: %s" % (m.path, getattr(m, "err_line", 1), m.error))
                bad = 1
                continue
            r, text = scaffold_module(proj, m)
            write_text(root, r, text)
            print("wrote " + r)
        write_index(root, md=False)
        return bad
    except UsageError as e:
        print("eli12: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
