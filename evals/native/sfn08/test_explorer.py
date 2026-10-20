"""K-04 (explorer viewer) and K-05 (builder CLI)."""
from __future__ import annotations

import html as htmllib
import importlib.util
import re
import shutil
import subprocess

import pytest

from .conftest import CLI, EDITORS, TEMPLATE, embedded_model, region, run_cli, tiny_model, write_model

# ------------------------------------------------------------------ K-04 static


def test_k04_template_inlines_function_verbatim():
    t = TEMPLATE.read_text()
    r = region(t)
    assert r is not None, "template.html needs exactly one editor-links:begin/end marker pair"
    assert "editorUrl" in r


def test_k04_template_reads_query_and_workspace():
    t = TEMPLATE.read_text()
    assert "workspace" in t
    assert re.search(r"""get\(\s*["']editor["']\s*\)""", t), "?editor= not read"
    assert re.search(r"""get\(\s*["']root["']\s*\)""", t), "?root= not read"
    assert t.count("editorUrl(") >= 2  # defined in the inlined region and used by the file list


def test_k04_template_copy_control_and_touch_target():
    t = TEMPLATE.read_text()
    assert "Copy path" in t
    assert re.search(r"min-height:\s*40px", t), "file links/buttons need a 40px touch target"


# ------------------------------------------------------------------ K-04 behavioural (headless Chrome)

def _browser():
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _build_html(tmp_path, workspace):
    spec = importlib.util.spec_from_file_location("nd_cli_sfn08", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = tiny_model({"workspace": workspace} if workspace is not None else None)
    m["nodes"]["a"]["files"] = [{"path": "src/qa.py", "lines": "120-168"},
                                {"path": "src/my file.py", "lines": "7"}, {"path": "README.md"}]
    out = tmp_path / "page.html"
    out.write_text(mod.build(m), encoding="utf-8")
    return out


def _dom(tmp_path, page, query):
    chrome = _browser()
    if chrome is None:
        pytest.fail("browser unavailable: no google-chrome/chromium found; K-04 behavioural check cannot run "
                    "(this is a FAILURE, not a skip)")
    # Chrome aborts under the runner's RLIMIT_AS cap, so escape it through a transient systemd user unit when present.
    wrap = ["systemd-run", "--user", "--pipe", "--wait", "--quiet"] if shutil.which("systemd-run") else []
    p = subprocess.run([*wrap, chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions",
                        f"--user-data-dir={tmp_path / 'chrome-profile'}", "--virtual-time-budget=6000",
                        "--dump-dom", f"file://{page}{query}#/a"], capture_output=True, text=True, timeout=18,
                       stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stderr[-400:]
    return htmllib.unescape(p.stdout)


def _panel(dom):
    # the dumped page also contains the template source, so take the rendered list (it has <li> right away)
    m = re.search(r'<ul class="files">\s*<li.*?</ul>', dom, re.S)
    assert m, "no file list rendered in the detail panel for node a"
    return m.group(0)


def _hrefs(panel):
    return re.findall(r'<a\b[^>]*\bhref="([^"]+)"', panel)


def test_k04_browser_workspace_links(tmp_path):
    page = _build_html(tmp_path, {"root": "/home/me/proj", "editor": "vscode"})
    panel = _panel(_dom(tmp_path, page, ""))
    hrefs = _hrefs(panel)
    assert "vscode://file/home/me/proj/src/qa.py:120" in hrefs, hrefs
    assert "vscode://file/home/me/proj/src/my%20file.py:7" in hrefs, hrefs
    assert "vscode://file/home/me/proj/README.md" in hrefs, hrefs
    assert panel.count("Copy path") >= 3 or panel.lower().count("copy path") >= 3


def test_k04_browser_query_overrides_workspace(tmp_path):
    page = _build_html(tmp_path, {"root": "/home/me/proj", "editor": "vscode"})
    hrefs = _hrefs(_panel(_dom(tmp_path, page, "?editor=zed&root=/other/place")))
    assert "zed://file/other/place/src/qa.py:120" in hrefs, hrefs
    assert not any(h.startswith("vscode://") for h in hrefs)


def test_k04_browser_invalid_query_root_ignored(tmp_path):
    page = _build_html(tmp_path, {"root": "/home/me/proj", "editor": "cursor"})
    hrefs = _hrefs(_panel(_dom(tmp_path, page, "?root=relative/dir")))
    assert "cursor://file/home/me/proj/src/qa.py:120" in hrefs, hrefs


def test_k04_browser_idea_query_only(tmp_path):
    page = _build_html(tmp_path, None)
    hrefs = _hrefs(_panel(_dom(tmp_path, page, "?editor=idea&root=/w/p")))
    assert "idea://open?file=%2Fw%2Fp%2Fsrc%2Fqa.py&line=120" in hrefs, hrefs


@pytest.mark.parametrize("workspace,query", [
    ({"root": "/home/me/proj", "editor": "none"}, ""),
    (None, ""),
    ({"editor": "vscode"}, ""),
    ({"root": "/home/me/proj", "editor": "vscode"}, "?editor=none"),
])
def test_k04_browser_no_editor_means_copy_and_hint_only(tmp_path, workspace, query):
    page = _build_html(tmp_path, workspace)
    panel = _panel(_dom(tmp_path, page, query))
    assert not re.search(r'href="(vscode|cursor|windsurf|zed|idea|subl|txmt)://', panel), panel
    assert "Copy path" in panel
    assert re.search(r"editor", re.sub(r"<[^>]+>", " ", panel).replace("Copy path", ""), re.I), \
        "a one-line hint on how to set the editor is required"


# ------------------------------------------------------------------ K-05 builder CLI

def _build(repo_tmp, *flags):
    m = write_model(repo_tmp)
    out = repo_tmp / "out.html"
    p = run_cli(CLI, "build", m, "-o", out, "--repo", repo_tmp, *flags)
    return p, out


def test_k05_build_stores_workspace(repo_tmp):
    p, out = _build(repo_tmp, "--workspace-root", "/home/me/proj", "--editor", "cursor")
    assert p.returncode == 0, p.stdout + p.stderr
    assert embedded_model(out.read_text())["workspace"] == {"root": "/home/me/proj", "editor": "cursor"}


@pytest.mark.parametrize("editor", EDITORS + ["none"])
def test_k05_check_accepts_listed_editors(repo_tmp, editor):
    m = write_model(repo_tmp, {"workspace": {"root": "/home/me/proj", "editor": editor}})
    p = run_cli(CLI, "check", m, "--repo", repo_tmp)
    assert p.returncode == 0, p.stdout + p.stderr


def test_k05_check_rejects_unknown_editor(repo_tmp):
    m = write_model(repo_tmp, {"workspace": {"root": "/home/me/proj", "editor": "emacs"}})
    p = run_cli(CLI, "check", m, "--repo", repo_tmp)
    assert p.returncode != 0 and "editor" in (p.stdout + p.stderr).lower()


@pytest.mark.parametrize("root", ["relative/dir", "~/proj", ""])
def test_k05_check_rejects_relative_root(repo_tmp, root):
    m = write_model(repo_tmp, {"workspace": {"root": root, "editor": "vscode"}})
    p = run_cli(CLI, "check", m, "--repo", repo_tmp)
    assert p.returncode != 0 and "root" in (p.stdout + p.stderr).lower()


def test_k05_build_rejects_relative_root_flag(repo_tmp):
    p, out = _build(repo_tmp, "--workspace-root", "relative/dir", "--editor", "vscode")
    err = p.stdout + p.stderr
    assert "unrecognized" not in err and "root" in err.lower(), err
    assert p.returncode != 0 and not out.exists()


def test_k05_build_rejects_unknown_editor_flag(repo_tmp):
    p, out = _build(repo_tmp, "--workspace-root", "/home/me/proj", "--editor", "emacs")
    err = p.stdout + p.stderr
    assert "unrecognized" not in err and "editor" in err.lower(), err
    assert p.returncode != 0 and not out.exists()


def test_k05_omission_regression(repo_tmp):
    p, out = _build(repo_tmp)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "workspace" not in embedded_model(out.read_text())
    p2 = run_cli(CLI, "check", write_model(repo_tmp), "--repo", repo_tmp)
    assert p2.returncode == 0, p2.stdout + p2.stderr
