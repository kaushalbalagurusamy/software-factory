"""Builder flags, workspace validation and `check --assets` (SFN-08 K-04/K-05/K-07)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TOOL = SKILL / "scripts" / "nesting_dolls.py"
MODEL = {"meta": {"title": "t"}, "root": "r", "nodes": {"r": {"title": "R", "summary": "s", "files": [{"path": "a.py", "lines": "1"}]}}}


def run(*a, cwd=None):
    return subprocess.run([sys.executable, str(TOOL), *a], capture_output=True, text=True, cwd=cwd)


def setup(tmp_path, ws=None):
    (tmp_path / "a.py").write_text("x\n")
    m = dict(MODEL, **({"workspace": ws} if ws is not None else {}))
    (tmp_path / "m.json").write_text(json.dumps(m))
    return tmp_path / "m.json"


def test_build_stores_workspace(tmp_path):
    m = setup(tmp_path)
    r = run("build", str(m), "-o", str(tmp_path / "o.html"), "--repo", str(tmp_path), "--workspace-root", "/abs/p", "--editor", "cursor")
    assert r.returncode == 0, r.stdout
    html = (tmp_path / "o.html").read_text()
    assert '"workspace": {"root": "/abs/p", "editor": "cursor"}' in html


def test_build_without_flags_has_no_workspace(tmp_path):
    m = setup(tmp_path)
    assert run("build", str(m), "-o", str(tmp_path / "o.html"), "--repo", str(tmp_path)).returncode == 0
    assert '"workspace"' not in (tmp_path / "o.html").read_text()


def test_check_rejects_bad_workspace(tmp_path):
    for ws in ({"root": "rel/p"}, {"root": "C:"}, {"editor": "emacs"}, {"root": "/ok", "editor": ""}, "x"):
        m = setup(tmp_path, ws)
        r = run("check", str(m), "--repo", str(tmp_path))
        assert r.returncode == 1 and "workspace" in r.stdout, ws


def test_check_accepts_good_workspace(tmp_path):
    for ws in ({"root": "/a", "editor": "none"}, {"root": "C:/Users/me", "editor": "zed"}):
        assert run("check", str(setup(tmp_path, ws)), "--repo", str(tmp_path)).returncode == 0


def test_flag_validation(tmp_path):
    m = setup(tmp_path)
    assert run("check", str(m), "--repo", str(tmp_path), "--editor", "emacs").returncode == 1
    assert run("check", str(m), "--repo", str(tmp_path), "--workspace-root", "rel").returncode == 1


def fake_repo(tmp_path, shell_text):
    (tmp_path / "ops" / "shell").mkdir(parents=True)
    (tmp_path / "ops" / "shell" / "index.html").write_text(shell_text)
    return tmp_path


def test_assets_check_passes_on_identical_and_fails_on_drift(tmp_path):
    src = (SKILL / "assets" / "editor-links.js").read_text()
    repo = fake_repo(tmp_path, "<script>\n" + src + "</script>")
    assert run("check", "--assets", "--repo", str(repo)).returncode == 0
    (repo / "ops" / "shell" / "index.html").write_text("<script>\n" + src.replace("MAX_LINE = 10000000", "MAX_LINE = 99") + "</script>")
    r = run("check", "--assets", "--repo", str(repo))
    assert r.returncode == 1 and "editor-links" in r.stdout


def test_assets_check_fails_when_shell_missing_or_unmarked(tmp_path):
    r = run("check", "--assets", "--repo", str(tmp_path))
    assert r.returncode == 1 and "editor-links" in r.stdout
    repo = fake_repo(tmp_path, "<script>no markers</script>")
    assert run("check", "--assets", "--repo", str(repo)).returncode == 1


def test_editor_list_matches_js():
    import re
    js = (SKILL / "assets" / "editor-links.js").read_text()
    in_js = re.search(r"var EDITORS = \[(.*?)\]", js).group(1).replace('"', "").replace(" ", "").split(",")
    in_py = re.search(r"EDITORS = \((.*?)\)", TOOL.read_text()).group(1).replace('"', "").replace(" ", "").split(",")
    assert in_js == in_py
