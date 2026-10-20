"""K-01..K-03: the pure editorUrl function, executed under Node."""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import EDITORS, JS, NODE, UNDEF, call, call_many

ROOT = "/home/me/proj"


def enc(seg: str) -> str:  # same unreserved set as encodeURIComponent
    return quote(seg, safe="-_.!~*'()")


def abs_enc(root: str, rel: str) -> str:
    return "/".join(enc(s) for s in (root + "/" + rel).split("/"))


def expected(editor: str, root: str, rel: str, line: int | None) -> str:
    a = abs_enc(root, rel)
    ln = f":{line}" if line else ""
    q = f"&line={line}" if line else ""
    return {
        "vscode": f"vscode://file{a}{ln}", "cursor": f"cursor://file{a}{ln}",
        "windsurf": f"windsurf://file{a}{ln}", "zed": f"zed://file{a}{ln}",
        "idea": f"idea://open?file={quote(root + '/' + rel, safe='-_.!~*()' + chr(39))}{q}",
        "sublime": f"subl://open?url=file://{a}{q}",
        "textmate": f"txmt://open?url=file://{a}{q}",
    }[editor]


def test_k01_file_exports_function_es5_umd():
    assert JS.is_file(), "skills/mermaid-nesting-dolls/assets/editor-links.js is missing"
    src = JS.read_text()
    assert "SFEditorLinks" in src and "module.exports" in src
    assert not re.search(r"=>|\bconst\b|\blet\b|`|\bclass\b|\bimport\b|\brequire\(", src), \
        "must be plain ES5 with no dependencies"
    assert NODE


def test_k01_returns_string_or_null():
    out = call_many([["vscode", ROOT, "a.py", 1], ["none", ROOT, "a.py", 1]])
    assert isinstance(out[0], str) and out[1] is None


@pytest.mark.parametrize("editor", EDITORS)
def test_k02_scheme_with_line(editor):
    assert call(editor, ROOT, "src/qa.py", 120) == expected(editor, ROOT, "src/qa.py", 120)


@pytest.mark.parametrize("editor", EDITORS)
def test_k02_scheme_without_line(editor):
    got = call(editor, ROOT, "src/qa.py", UNDEF)
    assert got.startswith(expected(editor, ROOT, "src/qa.py", None).split("&")[0]), got
    assert "line" not in got.split("?")[-1] and not re.search(r":\d+$", got), got
    assert "&line=" not in got


@pytest.mark.parametrize("editor", EDITORS)
def test_k02_percent_encoding(editor):
    rel = "src/my dir/a b#c%d'e\"f\u00e9\u4e2d.py"
    root = "/home/me/my proj#1"
    got = call(editor, root, rel, 7)
    assert got == expected(editor, root, rel, 7)
    # raw specials never leak into the URL after the scheme
    tail = got.split("://", 1)[1]
    assert " " not in tail and '"' not in got and "\u00e9" not in got
    assert "%25d" in got or "%2525d" in got  # the literal % is itself encoded


@pytest.mark.parametrize("line,suffix", [
    (UNDEF, None), (None, None), (0, None), (-1, None), (-5, None), (1.5, None), (2.0 + 0.5, None),
    ("abc", None), ("", None), ("1.5", None), ("-3", None), ("0", None),
    (1, 1), (120, 120), ("120", 120), ("7", 7), (10000000, 10000000), ("10000000", 10000000),
    (10000001, None), ("10000001", None), (True, None),
])
def test_k02_line_rules(line, suffix):
    got = call("vscode", ROOT, "a.py", line)
    assert got == f"vscode://file{ROOT}/a.py" + (f":{suffix}" if suffix else ""), got
    got = call("idea", ROOT, "a.py", line)
    assert ("&line=%d" % suffix in got) if suffix else ("line" not in got), got


def test_k02_nan_and_infinity_omit_line():
    # JSON cannot carry NaN/Infinity, so drive these through string forms the caller might pass
    assert call("zed", ROOT, "a.py", "NaN") == f"zed://file{ROOT}/a.py"
    assert call("zed", ROOT, "a.py", "Infinity") == f"zed://file{ROOT}/a.py"


@pytest.mark.parametrize("editor", ["none", "emacs", "", "VIM", "javascript", "file", "data", None, 5, UNDEF])
def test_k02_none_and_unknown_editor(editor):
    assert call(editor, ROOT, "a.py", 3) is None


BAD_REL = ["/etc/passwd", "/a.py", "../x.py", "a/../b.py", "a/..", "..", "a\x00b.py", "a\\b.py", "..\\x",
           "javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "http://evil.example/x", "x:y.py",
           "c:foo.py", "C:/Windows/x", "vscode://file/etc/x"]


@pytest.mark.parametrize("rel", BAD_REL)
@pytest.mark.parametrize("editor", ["vscode", "idea"])
def test_k03_rejects_unsafe_relpath(editor, rel):
    assert call(editor, ROOT, rel, 3) is None


def test_k03_rejects_nonstring_relpath_without_throwing():
    assert call_many([["vscode", ROOT, None, 1], ["vscode", ROOT, UNDEF, 1], ["vscode", ROOT, 5, 1],
                      ["vscode", None, "a.py", 1], ["vscode", UNDEF, "a.py", 1]]) == [None] * 5


@pytest.mark.parametrize("root", ["relative/dir", "./x", "~/proj", "", "proj", "\\\\server\\share", "C:", "C:proj",
                                  "javascript:alert(1)", "file:///home/me", "http://x/y", "\\home\\me"])
def test_k03_rejects_bad_root(root):
    assert call("vscode", root, "a.py", 3) is None


@pytest.mark.parametrize("root", ["C:/Users/me/proj", "D:\\Users\\me\\proj", "c:/work"])
def test_k03_accepts_windows_drive_root(root):
    got = call("vscode", root, "a.py", 3)
    assert got is not None and got.startswith("vscode://file/") and got.endswith("a.py:3"), got


def test_k03_rejects_windows_drive_root_that_is_not_a_drive_path():
    assert call("vscode", "1:/x", "a.py", 3) is None
    assert call("vscode", "CC:/x", "a.py", 3) is None


def test_k03_length_limits():
    ok_rel = "a" * 4096
    assert call("vscode", ROOT, ok_rel, 1) is not None
    assert call("vscode", ROOT, "a" * 4097, 1) is None
    assert call("vscode", ROOT, "d/" * 2048 + "x", 1) is None  # 4097 chars
    assert call("vscode", "/" + "r" * 4095, "a.py", 1) is not None
    assert call("vscode", "/" + "r" * 4096, "a.py", 1) is None


def test_k03_safe_inputs_still_work_when_dots_appear_inside_names():
    assert call("vscode", ROOT, "a..b/c.py", 2) == f"vscode://file{ROOT}/a..b/c.py:2"
    assert call("vscode", ROOT, ".hidden/.x", 2) == f"vscode://file{ROOT}/.hidden/.x:2"


def test_k03_never_dangerous_scheme_fuzz():
    editors = EDITORS + ["none", "javascript", "data", "file", "x", "JAVASCRIPT"]
    roots = [ROOT, "/", "javascript:alert(1)", "data:,x", "file:///x", "C:/x", "//host/share", "/a b"]
    rels = ["a.py", "javascript:1", "data:,x", "file:x", "//x", "a/b", ":x", " javascript:1", "\tdata:x", "%6aavascript:1"]
    calls = [[e, r, p, 3] for e in editors for r in roots for p in rels]
    for c, out in zip(calls, call_many(calls)):
        if out is None:
            continue
        low = out.lower().lstrip()
        assert not low.startswith(("javascript:", "data:", "file:")), (c, out)
        assert re.match(r"^(vscode|cursor|windsurf|zed|idea|subl|txmt)://", out), (c, out)
