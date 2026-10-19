"""The dolls checker must number lines like Python's ast (only \\n, \\r\\n, \\r), not like str.splitlines."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills" / "mermaid-nesting-dolls" / "scripts" / "nesting_dolls.py"


def check(tmp_path, lines, contains):
    (tmp_path / "m.py").write_text("a = 1\n\x0c\ndef target():\n    return 2\n", encoding="utf-8")
    model = {"root": "r", "nodes": {"r": {"title": "R", "summary": "s", "files": [{"path": "m.py", "lines": lines, "contains": contains}]}}}
    (tmp_path / "model.json").write_text(json.dumps(model))
    return subprocess.run([sys.executable, str(SCRIPT), "check", str(tmp_path / "model.json"), "--repo", str(tmp_path)],
                          capture_output=True, text=True, timeout=30)


def test_form_feed_is_not_a_line_break(tmp_path):
    # ast numbers `def target():` as line 3 (the form feed sits inside line 2); splitlines would call it line 4
    assert check(tmp_path, "3-4", "def target").returncode == 0
    assert check(tmp_path, "4-4", "def target").returncode != 0
