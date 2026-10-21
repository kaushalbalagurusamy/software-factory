"""Q-06 no invention / no model, stdlib-only, py3.9 syntax, no factory import, Q-08 wiring text."""
from __future__ import annotations

import ast
import re
import sys

from .conftest import CLI, REPO, SKILL


def _src():
    return CLI.read_text(encoding="utf-8")


def test_Q06_skill_tells_author_to_fill_todos_in_plain_words():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "TODO" in text
    assert re.search(r"12-year-old|twelve", text, re.I)
    assert re.search(r"example (value|input)", text, re.I)
    assert re.search(r"code and tests|tests and code", text, re.I)


def test_Q06_script_has_no_network_or_model_use():
    src = _src()
    for bad in ("urllib", "socket", "requests", "http", "anthropic", "openai"):
        assert bad not in src, "script must not mention %r" % bad


def test_Q07_script_parses_as_python_39():
    ast.parse(_src(), feature_version=(3, 9))


def test_Q07_stdlib_only_imports():
    tree = ast.parse(_src())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    assert mods, "no imports found at all?"
    assert mods <= (set(sys.stdlib_module_names) | {"__future__"}), mods - set(sys.stdlib_module_names)


def test_Q07_no_factory_import_and_no_os_specific_calls():
    src = _src()
    assert not re.search(r"(?m)^\s*(from|import)\s+factory\b", src)
    for bad in ("msvcrt", "fcntl", "winreg", "os.startfile", "os.fork"):
        assert bad not in src, bad


def test_Q08_doc_sync_gains_eli12_step():
    text = (REPO / "skills" / "doc-sync" / "SKILL.md").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if "eli12.py check" in l]
    assert lines, "doc-sync must tell the author to run `eli12.py check`"
    assert any(re.search(r"stale", l, re.I) for l in lines), lines
    assert text.startswith("---\nname: doc-sync")   # rest of the file kept


def test_Q08_implementation_review_approval_condition_lists_eli12():
    text = (REPO / "skills" / "implementation-review" / "SKILL.md").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if "eli12.py check" in l]
    assert lines, "implementation-review approval condition must list `eli12.py check`"
    assert any(re.search(r"approv", l, re.I) and re.search(r"clean", l, re.I) for l in lines), lines
    assert "Approval requires `sf slice done` to pass again" in text   # existing condition untouched
