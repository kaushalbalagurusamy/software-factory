"""(8) id/hash stability, (9) explorer model grounding, (10) structural diff impact."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.structure.diff import diff_trees
from factory.structure.model import build_model
from shelp import scan, write_tree

REPO = Path(__file__).resolve().parents[3]
DOLLS = REPO / "skills" / "mermaid-nesting-dolls" / "scripts" / "nesting_dolls.py"

BASE_SRC = (
    "LIMIT = 10\n\n\n"
    "def helper(a, b):\n    return a + b\n\n\n"
    "class Box:\n    def put(self, v):\n        return helper(v, 1)\n\n    def get(self):\n        return self.put(0)\n"
)


def _syms(tmp_path, name, src):
    return scan(tmp_path / name, {"m.py": src})["symbols"]


# ---------------------------------------------------------------------------- (8) stability
def test_ids_and_hashes_survive_formatting(tmp_path):
    reformatted = (
        "# a new header comment\n\n\n\nLIMIT = (10)\n\n\n\n\n"
        "def helper(a,\n           b):  # trailing comment\n    return (a +\n            b)\n\n\n"
        "class Box:\n\n    def put(self, v):\n        # comment\n        return helper(v,\n                      1,)\n\n\n"
        "    def get(self):\n        return self.put(0)\n"
    )
    a, b = _syms(tmp_path, "a", BASE_SRC), _syms(tmp_path, "b", reformatted)
    assert set(a) == set(b)
    for sid in a:
        assert a[sid]["ast_hash"] == b[sid]["ast_hash"], sid
    assert a["m:helper"]["start"] != b["m:helper"]["start"]  # lines moved, ids did not


@pytest.mark.parametrize("old,new,changed", [
    ("return a + b", "return a - b", "m:helper"),
    ("return helper(v, 1)", "return helper(v, 2)", "m:Box.put"),
    ("LIMIT = 10", "LIMIT = 11", "m:<module>"),
])
def test_body_change_changes_only_that_hash(tmp_path, old, new, changed):
    a, b = _syms(tmp_path, "a", BASE_SRC), _syms(tmp_path, "b", BASE_SRC.replace(old, new))
    diff = {sid for sid in a if a[sid]["ast_hash"] != b[sid]["ast_hash"]}
    assert diff == {changed}, diff


# ---------------------------------------------------------------------------- (9) model
MODEL_FIX = {
    "pkg/__init__.py": "",
    "pkg/core.py": "import functools\n\n\ndef helper():\n    return 1\n\n\n@functools.lru_cache\ndef cached():\n    return helper()\n\n\n"
                   "class Svc:\n    def a(self):\n        return self.b()\n\n    def b(self):\n        return getattr(self, 'a')()\n",
    "pkg/ff.py": "def first():\n    return 1\n\x0c\n\ndef second():\n    return first()\n\x0c\n\ndef third():\n    return second()\n",
}


def _model(tmp_path, files):
    root = write_tree(tmp_path / "repo", files)
    from factory.structure.extract import extract
    ex = extract(str(root))
    model = build_model(ex, repo=str(root), generated="2026-10-19")
    out = tmp_path / "model.json"
    out.write_text(json.dumps(model), encoding="utf-8")
    return root, ex, model, out


def test_model_passes_the_nesting_dolls_check(tmp_path):
    root, ex, model, out = _model(tmp_path, {k: v for k, v in MODEL_FIX.items() if k != "pkg/ff.py"})
    p = subprocess.run([sys.executable, str(DOLLS), "check", str(out), "--repo", str(root)], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and " 0 errors" in p.stdout, p.stdout + p.stderr
    assert model["meta"]["structure"]["complete_call_graph"] is False
    assert any(n.get("kind") == "unresolved" for n in model["nodes"].values())


@pytest.mark.parametrize("with_formfeed", [False, True])
def test_symbol_citations_are_the_symbols_own_span(tmp_path, with_formfeed):
    """Each symbol node must cite its own AST span (Python line numbering), and that span must hold its def line."""
    files = MODEL_FIX if with_formfeed else {k: v for k, v in MODEL_FIX.items() if k != "pkg/ff.py"}
    root, ex, model, _ = _model(tmp_path, files)
    by_title = {}
    for s in ex["symbols"].values():
        if s["kind"] in ("function", "class", "method"):
            by_title[(s["path"], s["qualname"] if s["kind"] == "method" else s["name"])] = s
    checked = 0
    for nid, n in model["nodes"].items():
        if n.get("kind") not in ("function", "class", "method"):
            continue
        (ref,) = n["files"]
        s = by_title[(ref["path"], n["title"])]
        lines = (root / ref["path"]).read_text(encoding="utf-8").split("\n")  # Python's own line numbering
        want = f"{s['start']}-{s['end']}" if s["end"] > s["start"] else str(s["start"])
        assert ref["lines"] == want, (nid, ref, want)
        kw = "class " if s["kind"] == "class" else "def "
        assert any(l.strip().startswith(kw + s["name"]) for l in lines[s["start"] - 1:s["end"]]), (nid, ref)
        assert ref.get("contains") and ref["contains"] in "\n".join(lines[s["start"] - 1:s["end"]]), (nid, ref)
        checked += 1
    assert checked >= 5


# ---------------------------------------------------------------------------- (10) diff
DIFF_BASE = {
    "pkg/__init__.py": "",
    "pkg/c.py": "LIMIT = 10\n\n\ndef helper():\n    return 1\n\n\ndef run():\n    return helper()\n\n\ndef check(v):\n    return v < LIMIT\n\n\n"
                "def make():\n    def inner():\n        return 1\n    return inner\n",
    "pkg/a.py": "from pkg import c as calias\n\n\ndef top():\n    return calias.helper()\n\n\ndef outer():\n    return top()\n\n\n"
                "def use_make():\n    return calias.make()()\n\n\n"
                "class K:\n    def helper(self):\n        return 0\n\n\ndef by_name(o):\n    return o.helper()\n",
    "pkg/broken.py": "def keep():\n    return 1\n\n\ndef gone_later():\n    return 2\n",
}


def _diff(tmp_path, head_changes):
    base = write_tree(tmp_path / "base", DIFF_BASE)
    head = write_tree(tmp_path / "head", {**DIFF_BASE, **head_changes})
    return diff_trees(str(base), str(head))


def _callers(d, via):
    return {c["id"]: c for c in d["affected_callers"] if c["via_changed"] == via}


def test_diff_lists_true_callers_with_edge_kinds(tmp_path):
    d = _diff(tmp_path, {"pkg/c.py": DIFF_BASE["pkg/c.py"].replace("def helper():\n    return 1", "def helper():\n    return 2"),
                         "pkg/a.py": DIFF_BASE["pkg/a.py"].replace("return 0", "return 5")})
    assert {c["id"] for c in d["changed"]} == {"pkg.c:helper", "pkg.a:K.helper"}
    c = _callers(d, "pkg.c:helper")
    assert c["pkg.c:run"]["edge_kind"] == "resolved" and c["pkg.a:top"]["edge_kind"] == "resolved"
    assert c["pkg.a:outer"]["depth"] == 2
    k = _callers(d, "pkg.a:K.helper")
    assert k["pkg.a:by_name"]["edge_kind"] == "syntactic"
    assert d["limits"]["complete_call_graph"] is False
    assert d["status"] == "complete_for_parsed_files"


def test_unparsable_head_file_is_unknown_not_removed(tmp_path):
    d = _diff(tmp_path, {"pkg/broken.py": "def keep(:\n    return 1\n"})
    assert d["removed"] == [] and d["status"] == "incomplete"
    assert {"pkg.broken:keep", "pkg.broken:gone_later"} <= set(d["unknown_due_to_parse_failure"])


def test_unparsable_base_file_is_unknown_not_added(tmp_path):
    base = write_tree(tmp_path / "base", {**DIFF_BASE, "pkg/broken.py": "def keep(:\n"})
    head = write_tree(tmp_path / "head", DIFF_BASE)
    d = diff_trees(str(base), str(head))
    assert d["added"] == [] and d["status"] == "incomplete"


def test_strict_cli_exits_3_on_parse_failure(tmp_path):
    base = write_tree(tmp_path / "base", DIFF_BASE)
    head = write_tree(tmp_path / "head", {**DIFF_BASE, "pkg/broken.py": "def keep(:\n"})
    p = subprocess.run([sys.executable, "-m", "factory.structure", "diff", str(base), str(head), "--strict"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 3, p.stderr


def test_deleted_file_symbols_are_removed_with_base_callers(tmp_path):
    base = write_tree(tmp_path / "base", DIFF_BASE)
    head_files = {k: v for k, v in DIFF_BASE.items() if k != "pkg/broken.py"}
    head_files["pkg/a.py"] = DIFF_BASE["pkg/a.py"] + "\n\ndef uses_keep():\n    from pkg.broken import keep\n    return keep()\n"
    base2 = write_tree(tmp_path / "base2", {**DIFF_BASE, "pkg/a.py": head_files["pkg/a.py"]})
    head = write_tree(tmp_path / "head", head_files)
    d = diff_trees(str(base2), str(head))
    assert "pkg.broken:keep" in d["removed"]
    assert "pkg.a:uses_keep" in _callers(d, "pkg.broken:keep")


def test_module_constant_change_lists_its_readers(tmp_path):
    """LIMIT feeds check(); changing it changes check's behaviour, so check must be in the impact listing."""
    d = _diff(tmp_path, {"pkg/c.py": DIFF_BASE["pkg/c.py"].replace("LIMIT = 10", "LIMIT = 20")})
    assert "pkg.c:<module>" in {c["id"] for c in d["changed"]}
    listed = {c["id"] for c in d["changed"]} | {c["id"] for c in d["affected_callers"]}
    assert "pkg.c:check" in listed, d["affected_callers"]


def test_closure_change_lists_callers_of_the_enclosing_function(tmp_path):
    """make() returns inner; changing inner's body changes what callers of make() get."""
    d = _diff(tmp_path, {"pkg/c.py": DIFF_BASE["pkg/c.py"].replace("    def inner():\n        return 1", "    def inner():\n        return 2")})
    assert "pkg.c:make.<locals>.inner" in {c["id"] for c in d["changed"]}
    listed = {c["id"] for c in d["changed"]} | {c["id"] for c in d["affected_callers"]}
    assert "pkg.a:use_make" in listed, (d["changed"], d["affected_callers"])
