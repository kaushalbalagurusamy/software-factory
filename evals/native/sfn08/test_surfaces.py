"""K-06 (ops shell), K-07 (single source), K-08 (demo model docs)."""
from __future__ import annotations

import re
import shutil

import pytest

from .conftest import (EXPLORER_DIR, JS, OPS_SHELL, SKILL, TEMPLATE, embedded_model, region, run_cli,
                       write_model)

# Amended when SFN-03 added the human-stops tab (clarification C-51.1): SFN-08 must still not change the tab list itself.
TABS_BLOCK = '''var TABS=[
 ["overview","Overview","mix"],["hitl","Human stops","mix"],["ops","Ops","rt"],["architecture","Architecture","hist"],["research","Research","hist"],
 ["experiments","Experiments","hist"],["adrs","ADRs","hist"],["prd","PRD journeys","hist"],["langfuse","Langfuse","rt"],
 ["evals","Evals & bugs","hist"],["journey","Dev journey","hist"],["git","Git history","hist"]];'''


# ------------------------------------------------------------------ K-06


def test_k06_ops_shell_inlines_function_and_reads_config():
    t = OPS_SHELL.read_text()
    assert region(t) is not None, "ops/shell/index.html needs exactly one editor-links marker pair"
    assert t.count("editorUrl(") >= 2, "the inlined function must also be used to render file links"
    assert "workspace_root" in t and re.search(r"""\beditor\b""", t)
    assert re.search(r"""get\(\s*["']editor["']\s*\)""", t) and re.search(r"""get\(\s*["']root["']\s*\)""", t), \
        "?editor= and ?root= overrides are not read"
    assert re.search(r"copy", t, re.I)


def test_k06_ops_shell_tabs_unchanged():
    assert TABS_BLOCK in OPS_SHELL.read_text(), "TABS list belongs to SFN-03 and must not change"


def test_k06_ops_shell_file_columns_still_present():
    t = OPS_SHELL.read_text()
    for col in ('["path","File"]', '["path","Source"]'):
        assert col in t


# ------------------------------------------------------------------ K-07


def test_k07_single_source_byte_identical():
    assert JS.is_file(), "editor-links.js missing"
    src = region(JS.read_text())
    assert src is not None, "editor-links.js needs exactly one begin/end marker pair"
    assert "function editorUrl" in src
    for name, p in (("template", TEMPLATE), ("ops shell", OPS_SHELL)):
        got = region(p.read_text())
        assert got is not None, f"{name} has no marker pair"
        assert got.encode() == src.encode(), f"{name} copy differs from editor-links.js"


@pytest.fixture
def mirror(tmp_path):
    """A copy of skill + ops shell the CLI can be pointed at (vendor library symlinked to save space)."""
    root = tmp_path / "repo"
    dst = root / "skills" / "mermaid-nesting-dolls"
    shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("vendor", "__pycache__", "tests"))
    (dst / "assets" / "vendor").symlink_to(SKILL / "assets" / "vendor")
    (root / "ops" / "shell").mkdir(parents=True)
    shutil.copy(OPS_SHELL, root / "ops" / "shell" / "index.html")
    (root / "src").mkdir()
    (root / "src" / "qa.py").write_text("x = 1\ny = 2\n")
    (root / "src" / "my file#1.py").write_text("z = 3\n")
    model = write_model(root)
    return root, dst, model


def _check(mirror):
    root, dst, model = mirror
    return run_cli(dst / "scripts" / "nesting_dolls.py", "check", model, "--repo", root, "--assets")


def test_k07_check_assets_passes_when_in_sync(mirror):
    p = _check(mirror)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("target", ["template", "ops", "source"])
def test_k07_check_assets_reports_mismatch(mirror, target):
    root, dst, _ = mirror
    f = {"template": dst / "assets" / "template.html", "ops": root / "ops" / "shell" / "index.html",
         "source": dst / "assets" / "editor-links.js"}[target]
    assert f.is_file(), f"{f} missing"
    text = f.read_text()
    assert region(text) is not None, f"{target}: no marker pair, cannot mutate"
    f.write_text(text.replace("/* editor-links:end */", "/* tampered */\n/* editor-links:end */"))
    p = _check(mirror)
    out = p.stdout + p.stderr
    assert p.returncode != 0, out
    assert "editor-links" in out.lower() or "editor links" in out.lower(), out


def test_k07_check_without_assets_flag_ignores_drift(mirror):
    root, dst, model = mirror
    f = dst / "assets" / "template.html"
    f.write_text(f.read_text() + "\n<!-- edited -->")
    p = run_cli(dst / "scripts" / "nesting_dolls.py", "check", model, "--repo", root)
    assert p.returncode == 0, p.stdout + p.stderr


# ------------------------------------------------------------------ K-08


def test_k08_readme_states_how_to_set_editor():
    t = (EXPLORER_DIR / "README.md").read_text()
    assert re.search(r"--editor", t) and re.search(r"--workspace-root", t) and re.search(r"\?editor=", t), \
        "README must name --editor, --workspace-root and the ?editor= query parameter"
    assert re.search(r"vscode", t) and re.search(r"none", t)


def test_k08_demo_model_rebuilt_portable():
    html = (EXPLORER_DIR / "software-factory.html").read_text()
    assert region(html) is not None, "explorer HTML was not rebuilt with the editor-links region"
    assert region(html).encode() == region(JS.read_text()).encode()
    ws = embedded_model(html).get("workspace") or {}
    assert not ws.get("root"), "demo model must be portable (no workspace root baked in)"
    model_json = (EXPLORER_DIR / "software-factory.model.json").read_text()
    assert '"workspace"' not in model_json or '"root"' not in model_json.split('"workspace"')[1][:200]
