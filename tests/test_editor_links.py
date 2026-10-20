"""SFN-08 editor deep links: the pure function (K-01..K-03) under Node and the single-source rule (K-07)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "mermaid-nesting-dolls"
JS = SKILL / "assets" / "editor-links.js"
NODE = shutil.which("node") or "/home/linuxuser/.local/bin/node"
BEGIN, END = "/* editor-links:begin */", "/* editor-links:end */"

pytestmark = pytest.mark.skipif(not Path(NODE).exists() and not shutil.which("node"), reason="node not available")


def url(*args):
    code = "var f=require(%s).editorUrl;console.log(JSON.stringify(f.apply(null,%s)))" % (json.dumps(str(JS)), json.dumps(list(args)))
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_schemes_with_line():
    r, p = "/home/me/proj", "src/qa.py"
    assert url("vscode", r, p, 120) == "vscode://file/home/me/proj/src/qa.py:120"
    assert url("cursor", r, p, 1).startswith("cursor://file/")
    assert url("windsurf", r, p, 1).startswith("windsurf://file/")
    assert url("zed", r, p, "7").endswith(":7")
    assert url("idea", r, p, 5) == "idea://open?file=%2Fhome%2Fme%2Fproj%2Fsrc%2Fqa.py&line=5"
    assert url("sublime", r, p, 5) == "subl://open?url=file:///home/me/proj/src/qa.py&line=5"
    assert url("textmate", r, p, 5) == "txmt://open?url=file:///home/me/proj/src/qa.py&line=5"


def test_encoding_and_windows_root():
    assert url("vscode", "/a b", "d/x y#1.py", 2) == "vscode://file/a%20b/d/x%20y%231.py:2"
    assert url("vscode", "C:/Users/me", "a.py", 3) == "vscode://file/C:/Users/me/a.py:3"


@pytest.mark.parametrize("line", [None, 0, -1, 1.5, True, "x", "1.5", "-2", 10000001, "10000001"])
def test_bad_line_is_omitted(line):
    assert url("vscode", "/r", "a.py", line) == "vscode://file/r/a.py"
    assert url("idea", "/r", "a.py", line) == "idea://open?file=%2Fr%2Fa.py"
    assert url("sublime", "/r", "a.py", line) == "subl://open?url=file:///r/a.py"


def test_line_bounds():
    assert url("vscode", "/r", "a", 10000000).endswith(":10000000")
    assert url("vscode", "/r", "a", "0120").endswith(":120")


@pytest.mark.parametrize("ed", ["none", "emacs", "", None, "VSCODE", "__proto__"])
def test_unknown_editor_is_null(ed):
    assert url(ed, "/r", "a.py", 1) is None


@pytest.mark.parametrize("rel", ["/etc/passwd", "../x", "a/../b", "a\\b", "a\u0000b", "javascript:alert(1)", "data:x", "file:x", "C:/x", "x:y", "", None, 5])
def test_unsafe_relpath_is_null(rel):
    assert url("vscode", "/r", rel, 1) is None


@pytest.mark.parametrize("root", ["r", "", "C:", "C:proj", "./r", "file:///r", None, "/r\u0000"])
def test_bad_root_is_null(root):
    assert url("vscode", root, "a.py", 1) is None


def test_length_limits_apply_per_argument():
    assert url("vscode", "/" + "a" * 4095, "a") is not None
    assert url("vscode", "/" + "a" * 4096, "a") is None
    assert url("vscode", "/r", "a" * 4096) is not None
    assert url("vscode", "/r", "a" * 4097) is None


def test_never_javascript_data_or_file_scheme():
    for ed in ["vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate"]:
        u = url(ed, "/r", "a.py", 1)
        assert not re.match(r"(javascript|data|file):", u)


def test_es5_only():
    src = JS.read_text(encoding="utf-8")
    assert "=>" not in src and "`" not in src
    assert not re.search(r"\b(const|let)\b", src)


def inlined(path):
    t = path.read_text(encoding="utf-8")
    a, b = t.index(BEGIN), t.index(END) + len(END)
    return t[a:b]


def test_inlined_copies_are_byte_identical():
    src = inlined(JS)
    assert inlined(SKILL / "assets" / "template.html") == src
    assert inlined(ROOT / "ops" / "shell" / "index.html") == src


def test_backslash_drive_root_is_converted():
    assert url("vscode", "D:\\Users\\me\\proj", "a.py", 3) == "vscode://file/D:/Users/me/proj/a.py:3"
    assert url("vscode", "/a\\b", "x") is None and url("vscode", "\\srv\\x", "x") is None


def test_dotted_names_ok_and_odd_lines_omitted():
    assert url("zed", "/r", "a..b/c.py", 2) == "zed://file/r/a..b/c.py:2"
    assert url("vscode", "/r", "a", "abc") == "vscode://file/r/a"


@pytest.mark.parametrize("root,rel", [
    ("//evil/share", "a.py"), ("///x", "a.py"), ("/home/me//proj", "a.py"), ("/r//", "a.py"), ("/r/./x", "a.py"),
    ("C:/x//y", "a.py"), ("/r", "a//b.py"), ("/r", "./a.py"), ("/r", "a/./b.py"), ("/r", "a/"), ("/r", "."),
])
def test_unc_empty_and_dot_segments_are_null(root, rel):
    for ed in ["vscode", "idea", "sublime"]:
        assert url(ed, root, rel, 1) is None


def test_single_trailing_slash_on_root_is_stripped():
    assert url("vscode", "/home/me/", "a.py", 1) == "vscode://file/home/me/a.py:1"
    assert url("vscode", "C:/Users/me/", "a.py", 1) == "vscode://file/C:/Users/me/a.py:1"
    assert url("vscode", "/", "a.py", 1) == "vscode://file/a.py:1"
