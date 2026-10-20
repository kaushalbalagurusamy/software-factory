"""Q-04 index, Q-05 index.json, Q-07 performance and safety."""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from .conftest import (C_MISSING, CORE, UTIL, check, doc_path, eli, fill_all, findings, scaffold_all, sections, write)


def _purpose(root, mod, sentence):
    p = doc_path(root, mod)
    paras = re.split(r"(\n\s*\n)", p.read_text())
    # paras[0] is the title, paras[2] the purpose paragraph
    paras[2] = sentence
    p.write_text("".join(paras))


def _walk_strings(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_strings(v)
    elif isinstance(x, str):
        yield x


def test_Q04_index_lists_modules_purpose_and_symbol_count(clean):
    _purpose(clean, "pkg.core", "This file holds the main steps that run the job.")
    p = eli("index", "--root", str(clean), cwd=clean)
    assert p.returncode == 0, p.stderr
    text = (clean / "docs" / "eli12" / "INDEX.md").read_text()
    core = next(l for l in text.splitlines() if "pkg.core" in l)
    assert "This file holds the main steps that run the job." in text
    assert re.search(r"\b5\b", core), core            # run, outer, unresolved, cached, fetch
    util = next(l for l in text.splitlines() if "pkg.util" in l)
    assert re.search(r"\b4\b", util), util            # helper, ping, Box, Box.get
    assert text.index("pkg.core") < text.index("pkg.util")  # sorted


def test_Q04_index_is_deterministic_across_runs_and_trees(tmp_path):
    outs = []
    for name in ("a", "b"):
        root = tmp_path / name
        write(root, "pkg/util.py", UTIL)
        write(root, "pkg/core.py", CORE)
        scaffold_all(root)
        fill_all(root)
        assert eli("index", "--root", str(root), cwd=root).returncode == 0
        first = (root / "docs/eli12/INDEX.md").read_bytes(), (root / "docs/eli12/index.json").read_bytes()
        time.sleep(1.1)
        assert eli("index", "--root", str(root), cwd=root).returncode == 0
        assert first == ((root / "docs/eli12/INDEX.md").read_bytes(), (root / "docs/eli12/index.json").read_bytes())
        outs.append(first)
    assert outs[0] == outs[1], "index output must not embed absolute paths or timestamps"


def test_Q05_index_json_maps_module_to_doc(clean):
    assert eli("index", "--root", str(clean), cwd=clean).returncode == 0
    data = json.loads((clean / "docs/eli12/index.json").read_text())
    strings = set(_walk_strings(data))
    assert "docs/eli12/pkg.core.md" in strings and "docs/eli12/pkg.util.md" in strings
    assert strings & {"pkg/core.py", "pkg.core"} and strings & {"pkg/util.py", "pkg.util"}
    # mapping, not a flat list: the module key sits next to its doc path
    def pairs(d):
        if isinstance(d, dict):
            if any(isinstance(v, str) and v == "docs/eli12/pkg.core.md" for v in d.values()):
                yield d
            for v in d.values():
                yield from pairs(v)
        elif isinstance(d, list):
            for v in d:
                yield from pairs(v)
    ok = any(k in ("pkg/core.py", "pkg.core") for k, v in _kv(data) if v == "docs/eli12/pkg.core.md") or \
        any({"pkg/core.py", "pkg.core"} & set(_walk_strings(d)) for d in pairs(data))
    assert ok


def _kv(d):
    if isinstance(d, dict):
        for k, v in d.items():
            yield k, v
            yield from _kv(v)


def test_Q04_index_usage_error_exit_2(tmp_path):
    assert eli("index", "--root", str(tmp_path / "nope"), cwd=tmp_path).returncode == 2


# ---- Q-07 -----------------------------------------------------------------------------------------------------------

def test_Q07_symlink_escape_is_never_read(clean, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("def leaked_secret_fn(a: int) -> int:\n    return a\n")
    os.symlink(outside / "secret.py", clean / "pkg" / "escape.py")
    os.symlink(outside, clean / "linked")
    for args in (("check",), ("check", "--json"), ("scaffold", "pkg/escape.py"), ("scaffold", "linked/secret.py"),
                 ("index",)):
        p = eli(*args[:1], "--root", str(clean), *args[1:], cwd=clean)
        assert "leaked_secret_fn" not in p.stdout + p.stderr, args
    for f in clean.rglob("*"):
        if f.is_file() and not f.is_symlink():
            assert "leaked_secret_fn" not in f.read_text(errors="ignore"), f


def test_Q07_scaffold_outside_root_is_refused(clean, tmp_path):
    other = tmp_path / "other.py"
    other.write_text("def stray_fn(a: int) -> int:\n    return a\n")
    p = eli("scaffold", "--root", str(clean), str(other), cwd=clean)
    assert p.returncode != 0
    assert not any("stray_fn" in f.read_text(errors="ignore") for f in clean.rglob("*.md"))


def test_Q07_default_ignores_and_include_override(clean):
    for rel in ("evals/e.py", ".venv/v.py", "node_modules/n.py", ".git/g.py"):
        write(clean, rel, "def hidden_%s(a: int) -> int:\n    return a\n" % re.sub(r"\W", "_", rel[:-3]))
    p = check(clean)
    assert p.returncode == 0 and "hidden_" not in p.stdout, p.stdout
    p = check(clean, "--include", "evals")
    assert p.returncode == 1
    assert any(f["code"] == C_MISSING and "hidden_evals_e" in f["msg"] for f in findings(p)), p.stdout
    assert "hidden_node_modules" not in p.stdout       # only the named dir is re-included


def test_Q07_fifty_modules_fast(tmp_path):
    root = tmp_path / "big"
    files = []
    for i in range(50):
        nxt = (i + 1) % 50
        write(root, "pkg/m%02d.py" % i,
              "from pkg import m%02d\n\n\ndef f%d(a: int) -> int:\n    return m%02d.f%d(a)\n\n\n"
              "class C%d:\n    def go(self, b: str) -> str:\n        return b\n" % (nxt, i, nxt, nxt, i))
        files.append("pkg/m%02d.py" % i)
    t = time.time()
    p = eli("scaffold", "--root", str(root), *files, cwd=root, timeout=60)
    assert p.returncode == 0, p.stderr
    fill_all(root)
    c = check(root)
    assert c.returncode == 0, c.stdout[:2000]
    i = eli("index", "--root", str(root), cwd=root)
    assert i.returncode == 0
    assert time.time() - t < 15, "50 modules should take well under 15 s (2,000 within 30 s)"
    shutil.rmtree(root)
