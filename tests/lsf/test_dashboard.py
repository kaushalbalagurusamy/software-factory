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


def test_tabs_name_where_they_look():
    assert "docs/explorer" in HTML and "docs/eli12" in HTML


def test_budget_summary_lines_are_separate_blocks():
    assert '"wrows small"' in HTML and ".wrows{display:flex;flex-direction:column;gap:" in HTML
    assert 'class:"row small"' not in HTML  # the old inline spans ran together


def test_tabs_follow_the_hash():
    assert "function tabFromHash" in HTML and 'addEventListener("hashchange"' in HTML
    assert "S.tab=tabFromHash();" in HTML and 'history.pushState(null,"","#"+t[0])' in HTML
    # the token is read and stripped before the tab is chosen, so #token=... never names a tab
    assert HTML.index("history.replaceState(null") < HTML.index("S.tab=tabFromHash();")
    assert 'return "now"' in HTML


def test_path_chip_and_copy_button_share_a_row():
    assert ".ref{display:inline-flex;align-items:center;flex-wrap:wrap;gap:" in HTML and ".ref.plain" in HTML
    assert "margin-left:.4rem" not in HTML
