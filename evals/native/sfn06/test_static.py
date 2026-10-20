"""Static checks: L-01 layout, L-10 dashboard, L-13 self-check, L-14 SKILL.md, L-15 safety, L-16 no breakage."""
from __future__ import annotations

import ast
import re
import subprocess
import sys

import pytest

from .conftest import LSF, PHASES, REPO, SKILL

DASH = SKILL / "assets" / "dashboard.html"
EDLINKS = SKILL / "assets" / "editor-links.js"
BEGIN, END = "/* editor-links:begin */", "/* editor-links:end */"


def need(p):
    if not p.is_file():
        pytest.fail(f"{p} does not exist yet (SFN-06 not implemented)", pytrace=False)
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- L-01
def test_L01_layout_files_exist():
    for rel in ("SKILL.md", "scripts/lsf.py", "scripts/eli12.py", "assets/dashboard.html", "assets/editor-links.js",
                "install.sh"):
        assert (SKILL / rel).is_file(), rel


def test_L01_skill_frontmatter():
    text = need(SKILL / "SKILL.md")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "frontmatter missing"
    fm = m.group(1)
    assert re.search(r"(?m)^name:\s*lsf\s*$", fm)
    assert re.search(r"(?m)^disable-model-invocation:\s*true\s*$", fm)
    assert re.search(r"(?m)^description:\s*\S", fm)


@pytest.mark.parametrize("copy,source", [
    ("assets/editor-links.js", "skills/mermaid-nesting-dolls/assets/editor-links.js"),
    ("scripts/eli12.py", "skills/eli12-docs/scripts/eli12.py"),
])
def test_L01_copies_are_byte_identical_to_sources_when_they_exist(copy, source):
    mine = SKILL / copy
    assert mine.is_file(), copy
    src = REPO / source
    if not src.is_file():
        pytest.skip(f"{source} has not landed yet (SFN-07/08); the contract says the byte check applies when it exists")
    assert mine.read_bytes() == src.read_bytes()


def test_L01_editor_links_carries_markers_and_the_function():
    text = need(EDLINKS)
    assert text.count(BEGIN) == 1 and text.count(END) == 1 and text.index(BEGIN) < text.index(END)
    assert "editorUrl" in text


def test_L01_dashboard_inlines_editor_links_between_markers():
    js, html = need(EDLINKS), need(DASH)
    want = js[js.index(BEGIN):js.index(END) + len(END)]
    assert html.count(BEGIN) == 1 and html.count(END) == 1
    got = html[html.index(BEGIN):html.index(END) + len(END)]
    assert got == want


# ---------------------------------------------------------------- L-10 (static)
TABS = ["Now", "Telemetry", "Research", "Experiments", "ADRs", "PRD", "Architecture", "Docs", "Evals & bugs", "Git"]


def test_L10_all_tab_names_present():
    html = need(DASH)
    visible = html.replace("&amp;", "&")
    for t in TABS:
        assert re.search(r">\s*" + re.escape(t) + r"\s*<|['\"]" + re.escape(t) + r"['\"]", visible), t


def test_L10_no_network_resources():
    html = need(DASH)
    assert not re.search(r"""(?i)\b(src|href|action|poster|data|srcset|formaction)\s*=\s*["']?\s*(https?:)?//""", html)
    assert not re.search(r"""(?i)url\(\s*["']?\s*(https?:)?//""", html)
    assert not re.search(r"(?i)@import", html)
    assert not re.search(r"(?i)<link[^>]+rel=[\"']?(stylesheet|preload|prefetch|preconnect|modulepreload)", html)
    assert not re.search(r"(?i)<script[^>]+\bsrc\s*=", html)
    assert not re.search(r"(?i)<(img|iframe|embed|object|video|audio|source)\b[^>]*\bsrc\s*=\s*[\"']?https?:", html)
    assert not re.search(r"""(?i)(fetch|XMLHttpRequest|WebSocket|EventSource|import)\s*\(?\s*["']https?:""", html)
    assert "navigator.sendBeacon" not in html
    for m in re.finditer(r"https?://[^\s\"'<>)]+", html):
        host = re.match(r"https?://([^/:#?]+)", m.group(0)).group(1)
        assert host in ("127.0.0.1", "localhost", "PORT") or "PORT" in m.group(0) or host.startswith("127."), m.group(0)


def test_L10_dark_and_light_tokens_via_prefers_color_scheme():
    html = need(DASH)
    assert "prefers-color-scheme" in html
    assert re.search(r":root\s*\{[^}]*--[a-z-]+\s*:", html)
    assert re.search(r"prefers-color-scheme:\s*dark", html) or re.search(r"prefers-color-scheme:\s*light", html)
    assert re.search(r"(?i)<meta[^>]+name=[\"']color-scheme[\"']|color-scheme\s*:", html)


def test_L10_usable_at_390px():
    html = need(DASH)
    assert re.search(r"(?i)<meta[^>]+name=[\"']viewport[\"'][^>]*width=device-width", html)
    assert re.search(r"@media[^{]*max-width:\s*(4\d\d|5\d\d|6\d\d|7\d\d)px", html)
    assert re.search(r"min-height:\s*(4\d|[5-9]\d)px", html), "touch targets of at least 40 px"
    assert "overflow-x" in html


def test_L10_empty_tabs_say_not_available_with_a_reason():
    html = need(DASH)
    assert "not available:" in html
    assert "reason" in html


def test_L10_available_is_never_shown_for_zero_items():
    html = need(DASH)
    # Visible wording: "available" may appear only as "not available", or as a property name; never as a state label
    stripped = re.sub(r"not available", "", html, flags=re.I)
    stripped = re.sub(r"(?i)\bunavailable\b", "", stripped)
    for m in re.finditer(r"""["'`>]([^"'`<>\n]*)\bavailable\b([^"'`<>\n]*)["'`<]""", stripped):
        assert not (m.group(1).strip() or m.group(2).strip()), f"visible 'available' label found: {m.group(0)!r}"
    # items-count guard exists wherever availability is decided
    assert re.search(r"\.items\s*(&&|\.length)|items\.length|\.length\s*[>=!]", html)


def test_L10_release_button_uses_token_header_and_falls_back_to_command():
    html = need(DASH)
    assert "Approve" in html
    assert "/api/hitl/release" in html and "X-LSF-Token" in html
    assert "lsf hitl release" in html
    assert re.search(r"location\.hash|#token=", html)
    for r in ("/api/state", "/api/file", "/api/at"):
        assert r in html


def test_L10_uses_editor_links_everywhere_files_are_named():
    html = need(DASH)
    assert html.count("editorUrl(") >= 2
    assert "Copy path" in html
    assert "workspace_root" in html and "editor" in html
    assert "docs/explorer" in html and "docs/eli12" in html


# ---------------------------------------------------------------- L-13 self-check / L-15
def lsf_source():
    return need(LSF)


def test_L13_lsf_is_python39_syntax():
    ast.parse(lsf_source(), feature_version=(3, 9))


def test_L13_no_python310_runtime_features():
    src = lsf_source()
    tree = ast.parse(src, feature_version=(3, 9))
    has_future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and
                     any(a.name == "annotations" for a in n.names) for n in tree.body)
    ann = []
    for n in ast.walk(tree):
        if isinstance(n, ast.arg) and n.annotation:
            ann.append(n.annotation)
        elif isinstance(n, ast.AnnAssign):
            ann.append(n.annotation)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns:
            ann.append(n.returns)
    piped = [a for a in ann if any(isinstance(x, ast.BinOp) and isinstance(x.op, ast.BitOr) for x in ast.walk(a))]
    assert not piped or has_future, "X | Y annotations need `from __future__ import annotations` on 3.9"
    for bad in ("tomllib", "zip(strict", "strict=True", "pairwise(", "bit_count", "removeprefix_", "ExceptionGroup",
                "datetime.UTC", "from datetime import UTC", "anext(", "aiter(", "slots=True", "kw_only"):
        assert bad not in src, bad
    assert not [n for n in ast.walk(tree) if type(n).__name__ in ("Match", "TryStar")]


def imported_modules(tree):
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    return mods


def test_L13_only_standard_library_imports():
    mods = imported_modules(ast.parse(lsf_source()))
    assert mods, "lsf.py must import something"
    std = getattr(sys, "stdlib_module_names", None)  # 3.10+; on 3.9 fall back to where the module lives
    if std is None:
        import importlib.util
        import sysconfig
        libdir = sysconfig.get_paths()["stdlib"]

        def is_std(m):
            spec = importlib.util.find_spec(m)
            return spec is not None and (spec.origin in ("built-in", "frozen") or
                                         (spec.origin or "").startswith(libdir) and "site-packages" not in spec.origin)
        std = {m for m in mods if is_std(m)}
    assert mods <= set(std), sorted(mods - set(std))
    assert "tomllib" not in mods  # 3.11+


def test_L15_no_posix_only_or_linux_only_facilities():
    src = lsf_source()
    mods = imported_modules(ast.parse(src))
    for bad in ("fcntl", "resource", "pwd", "grp", "termios", "pty", "msvcrt", "winreg", "syslog"):
        assert bad not in mods, bad
    for bad in ("flock", "prlimit", "/proc", "epoll", "inotify", "memfd", "os.sched_", "getxattr", "/sys/", "os.fork("):
        assert bad not in src, bad


def test_L15_no_network_clients():
    mods = imported_modules(ast.parse(lsf_source()))
    for bad in ("urllib", "requests", "ftplib", "smtplib", "imaplib", "poplib", "telnetlib", "xmlrpc",
                "ssl", "aiohttp", "httpx", "urllib3"):
        assert bad not in mods, bad
    src = lsf_source()
    assert "http.client" not in src and "urllib.request" not in src and "create_connection" not in src


def test_L15_server_uses_loopback_only():
    src = lsf_source()
    assert "127.0.0.1" in src
    assert "0.0.0.0" not in src and not re.search(r"""bind\(\s*\(\s*["']{2}""", src)


# ---------------------------------------------------------------- L-14
def skill_text():
    return need(SKILL / "SKILL.md")


def test_L14_flow_in_owner_order_with_alias_map_and_split():
    t = skill_text()
    pos = [t.index(p) for p in PHASES]
    assert pos == sorted(pos), "phase ids appear in the owner's order"
    low = t.lower()
    assert "alias" in low and ("/sf" in t or "sf stage" in low)
    assert "60%" in t and "20%" in t


def test_L14_rules_for_agents():
    t = skill_text()
    low = t.lower()
    assert "lsf hitl status" in t and "exit 3" in low
    assert re.search(r"(?i)never[^.\n]*releas|do not[^.\n]*releas|must not[^.\n]*releas|forbid[^.\n]*releas", t)
    assert "checkpoint" in low and "chat" in low
    assert "lsf phase start" in t and "lsf phase end" in t
    assert "ELI12" in t
    assert re.search(r"(?i)nesting dolls|mermaid-nesting-dolls|\bdolls\b", t)
    assert "ponytail" in low
    for path in ("docs/prds", "docs/adr", "experiments/", "research/", "docs/eli12", "docs/explorer", "docs/bugs"):
        assert path in t, path


def test_L14_models_are_a_profile_choice_with_no_hard_coded_names():
    t = skill_text()
    assert "models" in t and "profile.json" in t
    for name in ("opus", "sonnet", "haiku", "fable", "gpt-", "gemini", "claude-3", "claude-4", "claude-opus"):
        assert name not in t.lower(), name


def test_L14_skill_is_compact_enough_to_read():
    assert len(skill_text().splitlines()) <= 400


# ---------------------------------------------------------------- L-16
def test_L16_skills_sync_check_still_passes_and_knows_lsf():
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent-home", "PYTHONDONTWRITEBYTECODE": "1"}
    need(SKILL / "SKILL.md")
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "skills_sync.py"), "check"], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    s = subprocess.run([sys.executable, str(REPO / "scripts" / "skills_sync.py"), "status"], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=60)
    assert "lsf" in s.stdout + s.stderr


def test_L16_lsf_skill_dir_has_no_bytecode_or_secrets():
    assert (SKILL / "SKILL.md").is_file()
    assert not list(SKILL.rglob("__pycache__")) and not list(SKILL.rglob("*.pyc"))
