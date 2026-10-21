"""Shared harness for SFN-08 acceptance tests (editor deep links). Everything runs in tmp dirs."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "mermaid-nesting-dolls"
JS = SKILL / "assets" / "editor-links.js"
TEMPLATE = SKILL / "assets" / "template.html"
CLI = SKILL / "scripts" / "nesting_dolls.py"
OPS_SHELL = REPO / "ops" / "shell" / "index.html"
EXPLORER_DIR = REPO / "docs" / "explorer"
NODE = "/home/linuxuser/.local/bin/node"
BEGIN = "/* editor-links:begin */"
END = "/* editor-links:end */"
EDITORS = ["vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate"]

# Evaluates editorUrl for a batch of argument lists read from stdin; {"__undef": true} means undefined.
_RUNNER = r"""
const fs = require('fs');
const lib = require(process.argv[1]);
const fix = (v) => (v && typeof v === 'object' && v.__undef) ? undefined : v;
const calls = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = calls.map((a) => {
  try { return {ok: true, v: lib.editorUrl.apply(null, a.map(fix))}; }
  catch (e) { return {ok: false, err: String(e)}; }
});
process.stdout.write(JSON.stringify(out));
"""

UNDEF = {"__undef": True}


def call_many(calls: list[list]) -> list:
    """Run editorUrl under Node for each argument list; assert it never throws; return the values."""
    assert JS.is_file(), f"{JS.relative_to(REPO)} does not exist"
    p = subprocess.run([NODE, "-e", _RUNNER, str(JS)], input=json.dumps(calls), capture_output=True,
                       text=True, timeout=15)
    assert p.returncode == 0, f"node failed: {p.stderr[:500]}"
    res = json.loads(p.stdout)
    for c, r in zip(calls, res):
        assert r["ok"], f"editorUrl{c!r} threw {r.get('err')}"
    return [r["v"] for r in res]


def call(*args):
    return call_many([list(args)])[0]


def region(text: str) -> str | None:
    """Text from the begin marker to the end marker inclusive, or None."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return None
    a, b = text.index(BEGIN), text.index(END) + len(END)
    return text[a:b] if a < b else None


def run_cli(script: Path, *args, timeout: int = 18):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True,
                          timeout=timeout)


def tiny_model(extra: dict | None = None) -> dict:
    m = {"meta": {"title": "T"}, "root": "r",
         "nodes": {"r": {"title": "Root", "summary": "Root node.", "diagram": "flowchart LR\n  a[\"A\"]",
                         "children": ["a"]},
                   "a": {"title": "A", "summary": "Leaf A.", "files": [
                       {"path": "src/qa.py", "lines": "1-2"}, {"path": "src/my file#1.py", "lines": "1"}]}}}
    if extra:
        m.update(extra)
    return m


@pytest.fixture
def repo_tmp(tmp_path):
    """A tiny repository with the files the tiny model cites."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "qa.py").write_text("x = 1\ny = 2\n")
    (tmp_path / "src" / "my file#1.py").write_text("z = 3\n")
    return tmp_path


def write_model(dirpath: Path, extra: dict | None = None) -> Path:
    p = dirpath / "m.json"
    p.write_text(json.dumps(tiny_model(extra)))
    return p


def embedded_model(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="nd-model">(.*?)</script>', html, re.S)
    assert m, "no embedded model in built HTML"
    return json.loads(m.group(1).replace("<\\/", "</").replace("<\\!--", "<!--"))
