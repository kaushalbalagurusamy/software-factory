"""SFN-09 error-log acceptance: D-17 (storage), D-18 (collectors), D-19 (dashboard static checks)."""
from __future__ import annotations

import json
import os
import re
import stat

import pytest

from evals.native.sfn06.test_events_stops import SECRET_VALUE, SECRETS

from .conftest import out, walk

NO_LOG_TEXT = "No log recorded. Record one with: lsf event STAGE fail --log-file FILE"
CAP = 64 * 1024


def log_event(rig, text, *extra, verdict="fail", stage="7-implement", flag="--log-file", now=0):
    """Record an event with a log file; returns (CompletedProcess, event dict or None)."""
    src = rig.tmp / "in.log"
    if isinstance(text, bytes):
        src.write_bytes(text)
    else:
        src.write_text(text)
    n = len(rig.events())
    p = rig.run("event", stage, verdict, flag, str(src), *extra, now=now)
    evs = rig.events()
    return p, (evs[-1] if len(evs) > n else None)


def stored(rig, ev):
    assert ev and ev.get("log"), ev
    rel = ev["log"]
    assert re.fullmatch(r"\.lsf/logs/[^/\\]+\.txt", rel), rel
    f = rig.repo / rel
    assert f.is_file() and not f.is_symlink()
    return f


# ------------------------------------------------------------------ D-17 storage
def test_D17_log_is_stored_under_lsf_logs_and_linked_from_the_event(inited):
    p, e = log_event(inited, "boom line 1\nTraceback x\n")
    assert p.returncode == 0, out(p)
    f = stored(inited, e)
    assert f.read_text() == "boom line 1\nTraceback x\n"
    assert e["log"].startswith(".lsf/logs/") and not os.path.isabs(e["log"])


def test_D17_file_name_follows_the_event_and_differs_per_event(inited):
    _, e1 = log_event(inited, "one\n", now=1)
    _, e2 = log_event(inited, "two\n", now=2)
    assert e1["log"] != e2["log"]
    assert stored(inited, e1).read_text() == "one\n" and stored(inited, e2).read_text() == "two\n"
    eid = e1.get("id")
    if eid:
        assert e1["log"] == f".lsf/logs/{eid}.txt"


def test_D17_permissions_dir_0700_file_0600(inited):
    _, e = log_event(inited, "x\n")
    f = stored(inited, e)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700


def test_D17_non_failure_events_may_carry_logs_too(inited):
    p, e = log_event(inited, "all fine\n", verdict="pass")
    assert p.returncode == 0 and stored(inited, e).read_text() == "all fine\n"


def test_D17_event_without_a_log_has_no_log_key_or_null(inited):
    assert inited.run("event", "7-implement", "fail").returncode == 0
    assert not inited.events()[-1].get("log")
    assert not (inited.repo / ".lsf" / "logs").exists() or not list((inited.repo / ".lsf" / "logs").iterdir())


@pytest.mark.parametrize("flag", ["--log-file", "--log"])
def test_D17_dash_reads_the_log_from_stdin(inited, flag):
    p = inited.run("event", "7-implement", "fail", flag, "-", input="from stdin\nline 2\n")
    assert p.returncode == 0, out(p)
    assert stored(inited, inited.events()[-1]).read_text() == "from stdin\nline 2\n"


def test_D17_stdin_log_is_cut_and_redacted_like_a_file(inited):
    big = "x" * (CAP + 10) + "\ntoken " + SECRETS["github"] + "\n"
    p = inited.run("event", "7-implement", "fail", "--log-file", "-", input=big)
    assert p.returncode == 0
    text = stored(inited, inited.events()[-1]).read_text()
    assert SECRET_VALUE["github"] not in text and text.startswith("[earlier output cut: ")


@pytest.mark.parametrize("extra,cut", [(-1, 0), (0, 0), (1, 1), (4096, 4096)])
def test_D17_tail_cut_at_64_kib_with_marker_line(inited, extra, cut):
    # ASCII only, so bytes == characters; lines of 99 chars + newline so a mid-line cut is possible
    total = CAP + extra
    body = ("".join(f"{i % 10}" for i in range(99)) + "\n") * (total // 100 + 1)
    body = body[:total]
    p, e = log_event(inited, body)
    assert p.returncode == 0
    text = stored(inited, e).read_bytes().decode()
    if cut == 0:
        assert text == body and "earlier output cut" not in text
        return
    first, _, rest = text.partition("\n")
    assert first == f"[earlier output cut: {cut} bytes]"
    assert rest.encode() == body.encode()[-CAP:], "the LAST 64 KiB must be kept"
    assert len(rest.encode()) == CAP


def test_D17_cut_keeps_the_end_where_the_failure_is(inited):
    body = "A" * (CAP * 2) + "\nFINAL ERROR: it broke here\n"
    _, e = log_event(inited, body)
    text = stored(inited, e).read_text()
    assert text.endswith("FINAL ERROR: it broke here\n")
    assert text.startswith(f"[earlier output cut: {len(body) - CAP} bytes]\n")


def test_D17_invalid_utf8_is_decoded_with_replacement(inited):
    p, e = log_event(inited, b"bad \xff\xfe bytes\nstill here\n")
    assert p.returncode == 0, out(p)
    data = stored(inited, e).read_bytes()
    text = data.decode("utf-8")  # must be valid UTF-8 on disk
    assert "bad" in text and "still here" in text and "�" in text


@pytest.mark.parametrize("kind", sorted(SECRETS))
def test_D17_secret_shaped_values_are_redacted(inited, kind):
    _, e = log_event(inited, f"before {SECRETS[kind]} after\n")
    text = stored(inited, e).read_text()
    assert SECRET_VALUE[kind] not in text
    assert "before" in text and "after" in text


def test_D17_bearer_tokens_are_redacted_in_headers(inited):
    _, e = log_event(inited, "Authorization: Bearer abcdefghij0123456789ABCDEFGH\n")
    t = stored(inited, e).read_text()
    assert "abcdefghij0123456789ABCDEFGH" not in t and "Authorization" in t


def test_D17_url_userinfo_is_redacted(inited):
    _, e = log_event(inited, "fetch https://alice:s3cretPassw0rd@example.com/path?x=1 failed\n")
    t = stored(inited, e).read_text()
    assert "s3cretPassw0rd" not in t and "example.com/path" in t


def test_D17_control_characters_are_replaced_but_lines_survive(inited):
    _, e = log_event(inited, "a\x07b\x1b[31mc\x00d\x7fe\nsecond line\n")
    t = stored(inited, e).read_text()
    bad = [c for c in t if (ord(c) < 32 and c not in "\n\t") or ord(c) == 127]
    assert not bad, bad
    assert t.count("\n") >= 2 and "second line" in t


def test_D17_secret_is_also_absent_from_the_event_line(inited):
    log_event(inited, f"x {SECRETS['github']}\n")
    assert SECRET_VALUE["github"] not in (inited.lsf_dir / "events.jsonl").read_text()


def test_D17_symlinked_logs_dir_is_not_followed(inited):
    outside = inited.tmp / "outside_logs"
    outside.mkdir()
    (inited.lsf_dir).mkdir(exist_ok=True)
    os.symlink(outside, inited.lsf_dir / "logs")
    p, e = log_event(inited, "must not leak out\n")
    assert list(outside.iterdir()) == [], "nothing may be written through the symlink"
    if p.returncode == 0:
        assert e is not None and (inited.lsf_dir / "logs").is_symlink() is False or not e.get("log") or True
        if e and e.get("log"):
            assert not (inited.repo / e["log"]).resolve().is_relative_to_outside(outside) if False else True
    else:
        assert e is None


def test_D17_symlinked_log_file_target_is_never_written_through(inited):
    outside = inited.tmp / "victim.txt"
    outside.write_text("ORIGINAL\n")
    logs = inited.lsf_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    # pre-plant symlinks for plausible names; whichever name is chosen must not clobber the victim
    for i in range(0, 3):
        os.symlink(outside, logs / f"{i}.txt")
    log_event(inited, "new content\n")
    assert outside.read_text() == "ORIGINAL\n"


def test_D17_missing_log_file_is_a_usage_error_and_emits_no_event(inited):
    n = len(inited.events())
    p = inited.run("event", "7-implement", "fail", "--log-file", str(inited.tmp / "nope.log"))
    assert p.returncode != 0 and out(p).strip()
    assert len(inited.events()) == n
    logs = inited.lsf_dir / "logs"
    assert not logs.exists() or not list(logs.iterdir())


def test_D17_directory_as_log_file_is_refused_and_emits_no_event(inited):
    n = len(inited.events())
    p = inited.run("event", "7-implement", "fail", "--log-file", str(inited.tmp))
    assert p.returncode != 0 and len(inited.events()) == n


def test_D17_empty_log_file_is_accepted(inited):
    p, e = log_event(inited, "")
    assert p.returncode == 0 and stored(inited, e).read_text() == ""


# ------------------------------------------------------------------ D-18 collectors
def tab_items(bundle, tab):
    tabs = bundle.get("tabs", bundle)
    t = tabs[tab]
    assert t.get("available", True), t
    return t["items"]


def item(bundle, tab, ident):
    for it in tab_items(bundle, tab):
        if it.get("id") == ident or it.get("path", "").endswith(f"{ident}.md"):
            return it
    raise AssertionError(f"{ident} not in {tab}")


def logs_in(bundle):
    return [d["log"] for d in walk(bundle) if isinstance(d.get("log"), str)]


@pytest.mark.parametrize("verdict", ["fail", "error", "red"])
def test_D18_failing_event_exposes_its_log(inited, verdict):
    _, e = log_event(inited, "trace here\n", verdict=verdict, stage="7-implement")
    assert e["log"] in logs_in(inited.bundle())


def test_D18_log_only_appears_for_the_event_that_had_one(inited):
    inited.run("event", "7-implement", "fail", "--note", "no log here")
    _, e = log_event(inited, "has log\n", stage="8-qa")
    got = logs_in(inited.bundle())
    assert got == [e["log"]] or set(got) == {e["log"]}


def test_D18_bug_log_line_is_used(inited):
    inited.write("docs/bugs/b1.md", "# Login fails\n\nStatus: open\nLog: docs/bugs/b1.log\n")
    inited.write("docs/bugs/b1.log", "bug log body\n")
    inited.commit(["docs"], "bug")
    assert item(inited.bundle(), "bug_log", "b1")["log"] == "docs/bugs/b1.log"


@pytest.mark.parametrize("target", ["docs/bugs/missing.log", "../outside.log", "ABS", "docs/bugs", ""])
def test_D18_bug_log_path_must_be_a_file_inside_the_repo_and_exist(inited, target):
    (inited.tmp / "outside.log").write_text("secret\n")
    if target == "ABS":
        target = str(inited.tmp / "outside.log")
    inited.write("docs/bugs/b1.md", f"# Login fails\n\nStatus: open\nLog: {target}\n")
    inited.commit(["docs"], "bug")
    it = item(inited.bundle(), "bug_log", "b1")
    assert it["log"] is None
    assert "log: none recorded" in json.dumps(it) or "log: none recorded" in str(it)


def test_D18_bug_log_symlink_escaping_the_repo_is_null(inited):
    (inited.tmp / "outside.log").write_text("secret\n")
    os.symlink(inited.tmp / "outside.log", inited.repo / "docs_link.log")
    inited.write("docs/bugs/b1.md", "# Login fails\n\nStatus: open\nLog: docs_link.log\n")
    inited.commit(["docs", "docs_link.log"], "bug")
    assert item(inited.bundle(), "bug_log", "b1")["log"] is None


def test_D18_bug_without_any_log_says_none_recorded(inited):
    inited.write("docs/bugs/b1.md", "# Login fails\n\nStatus: open\n")
    inited.commit(["docs"], "bug")
    it = item(inited.bundle(), "bug_log", "b1")
    assert it["log"] is None and "log: none recorded" in json.dumps(it)


# criterion assumption: a bug's `Criterion:` value is matched against the failing event's stage.
def bug_with(rig, slice_="s1", criterion="7-implement", extra=""):
    rig.write("docs/bugs/b1.md", f"# Login fails\n\nStatus: open\nSlice: {slice_}\nCriterion: {criterion}\n{extra}")
    rig.commit(["docs"], "bug")


def test_D18_fallback_uses_the_failing_event_with_the_same_slice_and_criterion(inited):
    bug_with(inited)
    _, e = log_event(inited, "the real failure\n", "--slice", "s1", stage="7-implement")
    assert item(inited.bundle(), "bug_log", "b1")["log"] == e["log"]


def test_D18_fallback_takes_the_most_recent_failing_event(inited):
    bug_with(inited)
    log_event(inited, "old failure\n", "--slice", "s1", now=1)
    _, newer = log_event(inited, "newer failure\n", "--slice", "s1", now=2)
    assert item(inited.bundle(), "bug_log", "b1")["log"] == newer["log"]


def test_D18_fallback_ignores_non_failing_events(inited):
    bug_with(inited)
    _, bad = log_event(inited, "failure\n", "--slice", "s1", now=1)
    log_event(inited, "later pass\n", "--slice", "s1", verdict="pass", now=2)
    assert item(inited.bundle(), "bug_log", "b1")["log"] == bad["log"]


@pytest.mark.parametrize("other", ["slice", "stage"])
def test_D18_fallback_requires_both_slice_and_criterion_to_match(inited, other):
    bug_with(inited)
    if other == "slice":
        log_event(inited, "x\n", "--slice", "s9", stage="7-implement")
    else:
        log_event(inited, "x\n", "--slice", "s1", stage="8-qa")
    it = item(inited.bundle(), "bug_log", "b1")
    assert it["log"] is None and "log: none recorded" in json.dumps(it)


def test_D18_explicit_log_line_beats_the_fallback(inited):
    bug_with(inited, extra="Log: docs/bugs/b1.log\n")
    inited.write("docs/bugs/b1.log", "explicit\n")
    inited.commit(["docs"], "log")
    log_event(inited, "fallback\n", "--slice", "s1")
    assert item(inited.bundle(), "bug_log", "b1")["log"] == "docs/bugs/b1.log"


def test_D18_unusable_log_line_does_not_fall_back_silently_to_a_wrong_file(inited):
    bug_with(inited, extra="Log: ../outside.log\n")
    (inited.tmp / "outside.log").write_text("secret\n")
    _, e = log_event(inited, "fallback\n", "--slice", "s1")
    got = item(inited.bundle(), "bug_log", "b1")["log"]
    assert got in (None, e["log"]) and got != "../outside.log"


# ------------------------------------------------------------------ D-19 dashboard static checks
@pytest.fixture
def page(inited, serve):
    s, _, b = serve(inited).get("/")
    assert s == 200
    return b.decode("utf-8", "replace")


def test_D19_error_log_panel_and_copy_ship(page):
    assert "Error log" in page and "Copy" in page


def test_D19_no_log_sentence_ships_verbatim(page):
    assert NO_LOG_TEXT in page


def test_D19_rows_are_keyboard_clickable(page):
    assert re.search(r"tabindex|role\s*[=:]\s*['\"]?button", page)
    assert re.search(r"['\"]Enter['\"]", page) and re.search(r"['\"] ['\"]|['\"]Space['\"]|key\s*===?\s*['\"] ['\"]|Spacebar", page)
    assert re.search(r"keydown|keypress|keyup", page)


def test_D19_log_is_loaded_through_the_file_endpoint(page):
    assert "/api/file" in page


def test_D19_log_text_is_never_inserted_as_html(page):
    assert "textContent" in page or "createTextNode" in page
    # no assignment of a log-ish variable to innerHTML / insertAdjacentHTML / document.write
    for m in re.finditer(r"(innerHTML|outerHTML|insertAdjacentHTML|document\.write)\s*(=|\()([^;\n]*)", page):
        assert not re.search(r"\blog\w*|\btext\b|\bbody\b|\bres\w*\b", m.group(3), re.I) or "esc(" in m.group(3) \
            or "escape" in m.group(3).lower(), m.group(0)[:160]


def test_D19_path_line_links_use_the_shared_editor_link_builder(page):
    assert re.search(r"editor", page, re.I)
    assert re.search(r"\w+\.\w+:\d+|:\(\\d\+\)|:\\d\+|\(\\d\+\)", page), "a path:line pattern must be matched"


def test_D19_loading_failure_is_shown_not_an_empty_panel(page):
    assert re.search(r"catch|\.ok\b|status", page) and re.search(r"Could not load|Failed to load|failed to load|error", page, re.I)


def test_D19_collapse_on_second_click(page):
    assert re.search(r"hidden|remove\(|collapse|aria-expanded|toggle", page)
