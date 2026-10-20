"""Unit tests for skills/eli12-docs/scripts/eli12.py."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "eli12-docs" / "scripts" / "eli12.py"
spec = importlib.util.spec_from_file_location("eli12_under_test", SCRIPT)
eli12 = importlib.util.module_from_spec(spec)
sys.modules["eli12_under_test"] = eli12
spec.loader.exec_module(eli12)

LIB = '''"""lib."""


def helper(a: int, b: str = "x") -> str:
    return b * a


class Box:
    def __init__(self, n: int):
        self.n = n

    def grow(self, k: int) -> None:
        self.n += k

    def _hidden(self):
        pass
'''
APP = '''from lib import helper, Box


def run() -> str:
    b = Box(1)
    b.grow(2)
    return helper(2)
'''


def make(tmp_path, files=None):
    for name, text in (files or {"lib.py": LIB, "app.py": APP}).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def run(tmp_path, *args):
    return eli12.main(list(args) + ["--root", str(tmp_path)]) if args[0] != "check" else \
        eli12.main(list(args) + ["--root", str(tmp_path)])


def fill(tmp_path, rel):
    """Replace every TODO with plain words so the doc passes."""
    p = tmp_path / rel
    t = p.read_text()
    t = t.replace("**What it does:** TODO", "**What it does:** It does a small job.")
    t = re.sub(r"(\(\w+\)|\(any\)|\([^)]*\)): TODO", r"\1: a value", t)
    t = t.replace(": TODO", ": a value").replace("**Gives back:** TODO", "**Gives back:** str: text")
    t = t.replace("\nTODO\n", "\nThis file holds small helpers.\n", 1)
    p.write_text(t)


def codes(capsys):
    out = capsys.readouterr().out.strip().splitlines()
    return [ln.split(": ", 2)[1] for ln in out if ln]


def test_scaffold_computes_lists_and_leaves_todo(tmp_path):
    make(tmp_path)
    assert run(tmp_path, "scaffold", "lib.py", "app.py") == 0
    lib = (tmp_path / "docs/eli12/lib.md").read_text()
    assert lib.startswith("# lib.py\n")
    assert "## helper" in lib and "## Box.grow" in lib and "_hidden" not in lib
    assert "- a (int): TODO" in lib
    assert "<!-- sig:" in lib
    helper = lib.split("## helper")[1].split("## ")[0]
    assert "app.run (app.py:4)" in helper
    app = (tmp_path / "docs/eli12/app.md").read_text()
    assert "lib.helper (lib.py:4)" in app and "lib.Box (lib.py:8)" in app
    assert "lib.Box.grow (lib.py:12) (maybe)" in app  # b.grow: receiver type unknown
    assert json.loads((tmp_path / "docs/eli12/index.json").read_text()) == {
        "app.py": "docs/eli12/app.md", "lib.py": "docs/eli12/lib.md"}


def test_check_flow(tmp_path, capsys):
    make(tmp_path)
    assert run(tmp_path, "check") == 1
    assert set(codes(capsys)) == {"missing-entry"}
    run(tmp_path, "scaffold", "lib.py", "app.py")
    capsys.readouterr()
    assert run(tmp_path, "check") == 1
    assert set(codes(capsys)) == {"todo"}
    for m in ("lib", "app"):
        fill(tmp_path, "docs/eli12/%s.md" % m)
    assert run(tmp_path, "check") == 0, capsys.readouterr().out


def test_stale_signature_and_dependencies(tmp_path, capsys):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py", "app.py")
    for m in ("lib", "app"):
        fill(tmp_path, "docs/eli12/%s.md" % m)
    (tmp_path / "lib.py").write_text(LIB.replace("a: int,", "a: float,"))
    capsys.readouterr()
    run(tmp_path, "check")
    assert "stale-signature" in codes(capsys)
    run(tmp_path, "scaffold", "lib.py")
    (tmp_path / "other.py").write_text("from lib import helper\n\n\ndef again():\n    return helper(1, 'y')\n")
    capsys.readouterr()
    run(tmp_path, "check")
    capsys.readouterr()
    run(tmp_path, "check")
    assert "stale-dependencies" in codes(capsys)


def test_line_shift_is_not_stale(tmp_path, capsys):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py", "app.py")
    for m in ("lib", "app"):
        fill(tmp_path, "docs/eli12/%s.md" % m)
    (tmp_path / "app.py").write_text("# note\n" + APP)
    capsys.readouterr()
    assert run(tmp_path, "check") == 0


def test_scaffold_keeps_human_text(tmp_path):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py")
    fill(tmp_path, "docs/eli12/lib.md")
    before = (tmp_path / "docs/eli12/lib.md").read_text()
    (tmp_path / "lib.py").write_text(LIB + "\n\ndef extra(x: int) -> int:\n    return x\n")
    run(tmp_path, "scaffold", "lib.py")
    after = (tmp_path / "docs/eli12/lib.md").read_text()
    assert "It does a small job." in after and after.count("It does a small job.") == before.count("It does a small job.")
    assert "## extra" in after
    assert after.count("a value") >= before.count("a value")


def test_orphan_and_unparseable(tmp_path, capsys):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py", "app.py")
    for m in ("lib", "app"):
        fill(tmp_path, "docs/eli12/%s.md" % m)
    (tmp_path / "lib.py").write_text("def other() -> None:\n    pass\n")
    (tmp_path / "bad.py").write_text("def (:\n")
    capsys.readouterr()
    assert run(tmp_path, "check") == 1
    cs = codes(capsys)
    assert "orphan-entry" in cs and "unparseable" in cs and "missing-entry" in cs


def test_format_and_length_rules(tmp_path, capsys):
    make(tmp_path, {"m.py": "def f(a: int) -> int:\n    return a\n"})
    run(tmp_path, "scaffold", "m.py")
    p = tmp_path / "docs/eli12/m.md"
    t = p.read_text()
    t = t.replace("\nTODO\n", "\nA tiny file.\n").replace(
        "**What it does:** TODO", "**What it does:** It does one thing. It also does another thing.")
    t = t.replace("- a (int): TODO", "- a is a number").replace("**Gives back:** int: TODO", "**Gives back:** int: x" + "y" * 170)
    p.write_text(t)
    capsys.readouterr()
    run(tmp_path, "check")
    cs = codes(capsys)
    assert {"too-long", "bad-param"} <= set(cs)
    t = t.replace("**Gives back:**", "**Used by:** nothing\n\n**Gives back:**", 1)
    p.write_text(t)
    run(tmp_path, "check")
    assert "format" in codes(capsys)


def test_jargon_and_glossary(tmp_path, capsys):
    make(tmp_path, {"m.py": "def f(a: int) -> int:\n    return a\n"})
    run(tmp_path, "scaffold", "m.py")
    fill(tmp_path, "docs/eli12/m.md")
    p = tmp_path / "docs/eli12/m.md"
    p.write_text(p.read_text().replace("It does a small job.", "It calls the webhook."))
    capsys.readouterr()
    run(tmp_path, "check")
    assert codes(capsys) == ["jargon"]
    (tmp_path / "docs/eli12/GLOSSARY.md").write_text("# Glossary\n\n- webhook: a web address that gets pinged.\n")
    assert run(tmp_path, "check") == 0
    (tmp_path / "docs/eli12/GLOSSARY.md").unlink()
    (tmp_path / "docs/eli12/jargon.txt").write_text("# mine\nnothingburger\n")
    assert run(tmp_path, "check") == 0


def test_json_output_and_exit_codes(tmp_path, capsys):
    make(tmp_path)
    assert run(tmp_path, "check", "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data and set(data[0]) == {"path", "line", "code", "message"} and data[0]["line"] >= 1
    assert eli12.main(["check", "--root", str(tmp_path / "nope")]) == 2
    assert eli12.main(["bogus"]) == 2
    assert eli12.main(["check", "--root", str(tmp_path), "--paths", "missing.py"]) == 2


def test_paths_scope(tmp_path, capsys):
    make(tmp_path)
    run(tmp_path, "check", "--paths", "lib.py")
    assert all(ln.startswith("lib.py") for ln in capsys.readouterr().out.splitlines())


def test_ignored_dirs_and_include(tmp_path, capsys):
    make(tmp_path, {"ok.py": "X = 1\n", ".venv/v.py": "def pub():\n    pass\n", "evals/e.py": "def pub():\n    pass\n"})
    assert run(tmp_path, "check") == 0
    assert eli12.main(["check", "--root", str(tmp_path), "--include", "evals"]) == 1


def test_symlink_escape(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("def leak():\n    pass\n")
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside / "secret.py", root / "link.py")
    assert run(root, "check") == 1
    out = capsys.readouterr().out
    assert "unparseable" in out and "leak" not in out


def test_index_deterministic(tmp_path):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py", "app.py")
    assert run(tmp_path, "index") == 0
    a = (tmp_path / "docs/eli12/INDEX.md").read_text()
    run(tmp_path, "index")
    assert a == (tmp_path / "docs/eli12/INDEX.md").read_text()
    assert "lib.py" in a and "| 3 |" in a


def test_package_init_and_dotted_names(tmp_path):
    make(tmp_path, {"pkg/__init__.py": "def top():\n    pass\n", "pkg/sub/m.py": "def f():\n    pass\n"})
    run(tmp_path, "scaffold", "pkg/__init__.py", "pkg/sub/m.py")
    assert (tmp_path / "docs/eli12/pkg.md").exists() and (tmp_path / "docs/eli12/pkg.sub.m.md").exists()


def test_changed_mode(tmp_path, capsys):
    make(tmp_path)
    run(tmp_path, "scaffold", "lib.py", "app.py")
    for m in ("lib", "app"):
        fill(tmp_path, "docs/eli12/%s.md" % m)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git"] + cmd, cwd=tmp_path, env=env, check=True)
    (tmp_path / "other.py").write_text("def new_one():\n    pass\n")
    capsys.readouterr()
    rc = eli12.main(["check", "--root", str(tmp_path), "--changed", "HEAD"])
    out = capsys.readouterr().out
    assert rc == 1 and "other.py" in out and "lib.py" not in out
    assert eli12.main(["check", "--root", str(tmp_path), "--changed", "no-such-ref"]) == 2


def test_two_thousand_modules_fast(tmp_path):
    for i in range(2000):
        (tmp_path / ("m%d.py" % i)).write_text("def f%d(a: int) -> int:\n    return a\n" % i)
    t = time.time()
    eli12.main(["check", "--root", str(tmp_path)])
    assert time.time() - t < 30
