import re

from conftest import SKILL

HTML = (SKILL / "assets" / "dashboard.html").read_text()
JS = (SKILL / "assets" / "editor-links.js").read_text()


def test_editor_links_inlined_byte_identical_between_markers():
    a, b = HTML.index("/* editor-links:begin */"), HTML.index("/* editor-links:end */") + len("/* editor-links:end */")
    assert HTML[a:b] == JS.strip("\n")


def test_editor_links_copy_matches_source_when_present():
    src = SKILL.parent / "mermaid-nesting-dolls" / "assets" / "editor-links.js"
    if src.exists():
        assert src.read_bytes() == (SKILL / "assets" / "editor-links.js").read_bytes()


def test_offline_and_themed_and_mobile():
    assert not re.search(r"""(?:src|href|url\()\s*=?\s*["']?(?:https?:)?//""", HTML)
    assert "http://" not in HTML and "https://" not in HTML
    assert "prefers-color-scheme" in HTML and 'name="viewport"' in HTML
    for tab in ("Now", "Telemetry", "Research", "Experiments", "ADRs", "PRD", "Architecture", "Docs", "Evals & bugs", "Git"):
        assert '"%s"' % tab in HTML
    assert "X-LSF-Token" in HTML and "/api/hitl/release" in HTML and "lsf hitl release" in HTML and "Approve" in HTML
    assert "editorUrl" in HTML and "not available: " in HTML


def test_no_innerhtml_of_data():
    assert "innerHTML" not in HTML
