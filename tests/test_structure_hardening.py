"""Regression tests for edge honesty, diff impact and line numbering in factory.structure."""
from __future__ import annotations

from pathlib import Path

from factory.structure.diff import diff_trees
from factory.structure.extract import ast_lines, extract
from factory.structure.model import build_model


def scan(tmp: Path, files: dict) -> dict:
    for rel, text in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return extract(tmp)


def edge(ex, caller, text):
    (e,) = [e for e in ex["edges"] if e["caller"] == caller and e["text"] == text]
    return e


def test_stdlib_decorators_are_transparent_only_when_bound_to_stdlib(tmp_path):
    ex = scan(tmp_path, {"m.py": (
        "import functools as ft\nfrom functools import cache\n\n\n"
        "@cache\ndef a():\n    return 1\n\n\n@ft.lru_cache(maxsize=2)\ndef b():\n    return 2\n\n\n"
        "def use():\n    return a() + b()\n")})
    assert edge(ex, "m:use", "a")["kind"] == "resolved" and edge(ex, "m:use", "b")["kind"] == "resolved"


def test_repo_defined_or_rebound_decorator_names_are_not_trusted(tmp_path):
    ex = scan(tmp_path, {"m.py": (
        "def property(fn):\n    return fn\n\n\n@property\ndef p():\n    return 1\n\n\n"
        "def lru_cache(fn):\n    return fn\n\n\n@lru_cache\ndef q():\n    return 1\n\n\n"
        "def use():\n    return p() + q()\n")})
    assert edge(ex, "m:use", "p")["reason_code"] == "decorator_wrapped"
    assert edge(ex, "m:use", "q")["reason_code"] == "decorator_wrapped"


def test_property_setter_pair_stays_transparent(tmp_path):
    ex = scan(tmp_path, {"m.py": (
        "class C:\n    @property\n    def v(self):\n        return 1\n\n    @v.setter\n    def v(self, x):\n        pass\n\n"
        "    def go(self):\n        return self.helper()\n\n    @staticmethod\n    def helper():\n        return 2\n")})
    assert edge(ex, "m:C.go", "self.helper")["kind"] == "resolved"


def test_star_import_before_binding_or_without_that_name_does_not_poison(tmp_path):
    ex = scan(tmp_path, {"pkg/__init__.py": "", "pkg/b.py": "def other():\n    return 1\n",
                         "pkg/ok.py": "def mine():\n    return 1\n\n\nfrom pkg.b import *\n\n\ndef use():\n    return mine()\n",
                         "pkg/early.py": "from pkg.b import *\n\n\ndef other():\n    return 2\n\n\ndef use():\n    return other()\n"})
    assert edge(ex, "pkg.ok:use", "mine")["kind"] == "resolved"  # b exports no `mine`
    assert edge(ex, "pkg.early:use", "other")["kind"] == "resolved"  # defined after the star import


def test_star_import_from_unscanned_module_makes_earlier_names_unresolved(tmp_path):
    ex = scan(tmp_path, {"m.py": "def f():\n    return 1\n\n\nfrom somewhere import *\n\n\ndef use():\n    return f()\n"})
    assert edge(ex, "m:use", "f")["reason_code"] == "star_import_rebinding"


def test_override_and_attribute_shadow_keep_candidates(tmp_path):
    ex = scan(tmp_path, {"m.py": (
        "class B:\n    def run(self):\n        return self.step()\n\n    def step(self):\n        return 1\n\n\n"
        "class S(B):\n    def step(self):\n        return 2\n\n\n"
        "class T(B):\n    def __init__(self):\n        self.step = print\n")})
    e = edge(ex, "m:B.run", "self.step")
    assert e["kind"] == "syntactic" and e["target"] is None
    assert set(e["candidates"]) == {"m:B.step", "m:S.step"}


def test_class_attribute_patch_and_no_false_positive(tmp_path):
    ex = scan(tmp_path, {"m.py": "class K:\n    def f(self):\n        return 1\n\n    def g(self):\n        return self.f()\n\n\n"
                                 "def fake():\n    return 2\n\n\nK.f = fake\n\n\nclass L:\n    def f(self):\n        return 1\n\n"
                                 "    def g(self):\n        return self.f()\n"})
    assert edge(ex, "m:K.g", "self.f")["kind"] == "syntactic"
    assert edge(ex, "m:L.g", "self.f")["kind"] == "resolved"


def test_module_patched_from_another_file(tmp_path):
    ex = scan(tmp_path, {"pkg/__init__.py": "", "pkg/c.py": "def helper():\n    return 1\n\n\ndef run():\n    return helper()\n",
                         "pkg/user.py": "from pkg import c\n\n\ndef go():\n    return c.helper()\n",
                         "pkg/p.py": "import pkg.c\n\n\npkg.c.helper = lambda: 2\n"})
    assert edge(ex, "pkg.c:run", "helper")["reason_code"] == "module_attr_rebound"
    assert edge(ex, "pkg.user:go", "c.helper")["kind"] == "unresolved"


BASE = {
    "pkg/__init__.py": "",
    "pkg/c.py": "LIMIT = 1\nOTHER = 2\n\n\ndef check(v):\n    return v < LIMIT\n\n\ndef make():\n    def inner():\n        return 1\n    return inner\n",
    "pkg/u.py": "from pkg import c\n\n\ndef use():\n    return c.make()()\n\n\ndef top():\n    return use()\n",
}


def _diff(tmp_path, change, depth=2):
    for name, files in (("base", BASE), ("head", {**BASE, **change})):
        for rel, text in files.items():
            p = tmp_path / name / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
    return diff_trees(tmp_path / "base", tmp_path / "head", depth=depth)


def test_changed_constant_lists_only_its_readers_with_kind(tmp_path):
    d = _diff(tmp_path, {"pkg/c.py": BASE["pkg/c.py"].replace("LIMIT = 1", "LIMIT = 2")})
    assert [s["id"] for s in d["changed_state"]] == ["pkg.c:LIMIT"]
    r = [c for c in d["affected_callers"] if c["via_changed"] == "pkg.c:LIMIT"]
    assert [(c["id"], c["kind"]) for c in r] == [("pkg.c:check", "read")]


def test_inner_function_change_lists_enclosing_and_its_callers(tmp_path):
    d = _diff(tmp_path, {"pkg/c.py": BASE["pkg/c.py"].replace("return 1\n    return inner", "return 9\n    return inner")}, depth=3)
    r = {c["id"]: c for c in d["affected_callers"] if c["via_changed"] == "pkg.c:make.<locals>.inner"}
    assert r["pkg.c:make"]["kind"] == "enclosing" and r["pkg.u:use"]["depth"] == 2 and r["pkg.u:top"]["depth"] == 3


def test_removed_constant_lists_base_readers(tmp_path):
    d = _diff(tmp_path, {"pkg/c.py": BASE["pkg/c.py"].replace("LIMIT = 1\n", "")})
    assert d["removed_state"] == ["pkg.c:LIMIT"]
    assert any(c["id"] == "pkg.c:check" and c["graph"] == "base" for c in d["affected_callers"])


def test_ast_lines_follow_python_numbering():
    assert ast_lines("a\x0cb\nc\r\nd\re\n") == ["a\x0cb", "c", "d", "e"]
    assert ast_lines("") == []


def test_model_cites_real_lines_in_files_with_form_feeds(tmp_path):
    ex = scan(tmp_path, {"f.py": "def first():\n    return 1\n\x0c\x0c\x0c\n\ndef second():\n    return first()\n"})
    m = build_model(ex, repo=tmp_path, generated="2026-01-01")
    ref = m["nodes"]["f/second"]["files"][0]
    assert ref["lines"] == "5-6" and ref["contains"] == "def second():"
    assert m["meta"]["structure"]["line_numbering_mismatch_files"] == ["f.py"]
