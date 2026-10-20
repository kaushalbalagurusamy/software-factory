"""SFN-01 E-01..E-03: the event writer, through its public function `factory.ops.events.emit` and files on disk."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from .conftest import REPO, child_env, commit, emit_fn, git, read_events

AT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\+00:00|Z)$")  # UTC ISO 8601, whole seconds
BASE_KEYS = {"at", "stage", "slice", "sha", "verdict", "note", "source"}


def lines(repo) -> list[str]:
    p = Path(repo) / "ops" / "events.jsonl"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


# ------------------------------------------------------------------ E-01

def test_E01_appends_exactly_one_json_line_with_the_documented_keys(repo):
    emit = emit_fn()
    head = git(repo, "rev-parse", "HEAD")
    assert emit(repo, "4-slice", "s1", "pass") is True
    raw = (repo / "ops" / "events.jsonl").read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    ev = json.loads(raw)
    assert set(ev) == BASE_KEYS  # no `role` unless given
    assert ev["stage"] == "4-slice" and ev["slice"] == "s1" and ev["verdict"] == "pass"
    assert ev["note"] == "" and ev["source"] == "sf" and ev["sha"] == head
    assert AT.match(ev["at"]), ev["at"]


def test_E01_signature_accepts_keywords_and_role_only_when_given(repo):
    emit = emit_fn()
    assert emit(repo, "hitl", "-", "open", note="n", source="hook", role="research") is True
    assert emit(root=repo, stage="x", slice_id="s", verdict="v", note="", source="sf", role=None) is True
    a, b = read_events(repo)
    assert a["role"] == "research" and a["source"] == "hook" and a["note"] == "n"
    assert "role" not in b
    assert emit(str(repo), "x", "s", "v") is True  # a str root works like a Path


def test_E01_at_is_utc_whole_seconds(repo):
    emit = emit_fn()
    emit(repo, "x", "s", "v")
    at = read_events(repo)[0]["at"]
    assert AT.match(at)
    assert "." not in at


def test_E01_sha_is_unknown_outside_git_and_before_first_commit(bare_dir, tmp_path):
    emit = emit_fn()
    assert emit(bare_dir, "x", "s", "v") is True
    assert read_events(bare_dir)[0]["sha"] == "unknown"
    empty = tmp_path / "nocommit"
    empty.mkdir()
    git(empty, "init", "-q")
    assert emit(empty, "x", "s", "v") is True
    assert read_events(empty)[0]["sha"] == "unknown"


def test_E01_sha_follows_head(repo):
    emit = emit_fn()
    emit(repo, "x", "s", "v")
    second = commit(repo, "two")
    emit(repo, "x", "s", "v")
    shas = [e["sha"] for e in read_events(repo)]
    assert shas[1] == second and shas[0] != second


def test_E01_creates_ops_and_appends_after_existing_lines(repo):
    emit = emit_fn()
    (repo / "ops").mkdir()
    old = '{"at": "2026-01-01T00:00:00+00:00", "stage": "old", "slice": "s", "sha": "x", "verdict": "v", "note": ""}\n'
    (repo / "ops" / "events.jsonl").write_text(old, encoding="utf-8")
    assert emit(repo, "new", "s", "v") is True
    assert emit(repo, "newer", "s", "v") is True
    ls = lines(repo)
    assert ls[0] == old.rstrip("\n") and len(ls) == 3
    assert [json.loads(x)["stage"] for x in ls] == ["old", "new", "newer"]


def test_E01_creates_ops_directory_when_absent(repo):
    emit = emit_fn()
    assert not (repo / "ops").exists()
    assert emit(repo, "x", "s", "v") is True
    assert (repo / "ops" / "events.jsonl").is_file()


WRITER = (
    "import sys\n"
    "from factory.ops.events import emit\n"
    "root, tag, n = sys.argv[1], sys.argv[2], int(sys.argv[3])\n"
    "for i in range(n):\n"
    "    assert emit(root, 'conc', tag, 'pass', note=f'{tag}-{i}-' + 'x' * 1500) is True\n"
)


def test_E01_concurrent_writers_never_interleave_a_line(repo):
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(repo), f"w{k}", "40"], env=child_env(),
                              stderr=subprocess.PIPE, text=True) for k in range(4)]
    for p in procs:
        _, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
    evs = read_events(repo)  # raises if any line is not valid JSON
    assert len(evs) == 160
    for k in range(4):
        mine = [e for e in evs if e["slice"] == f"w{k}"]
        assert len(mine) == 40
        assert [e["note"].split("-")[1] for e in mine] == [str(i) for i in range(40)]  # per-writer order kept


# ------------------------------------------------------------------ E-02

@pytest.mark.parametrize("n", [0, 1, 1999, 2000, 2001, 2500])
def test_E02_note_is_truncated_to_exactly_2000_characters(repo, n):
    emit = emit_fn()
    note = "".join(chr(ord("a") + i % 26) for i in range(n))
    assert emit(repo, "x", "s", "v", note=note) is True
    got = read_events(repo)[-1]["note"]
    assert got == note[:2000]
    assert len(got) == min(n, 2000)


def test_E02_truncation_counts_characters_not_bytes(repo):
    emit = emit_fn()
    emit(repo, "x", "s", "v", note="é" * 2001)
    assert read_events(repo)[-1]["note"] == "é" * 2000


def test_E02_control_characters_become_a_space_and_the_event_stays_one_line(repo):
    emit = emit_fn()
    nasty = "a\x00b\tc\nd\re\x1bf\x7fg\x85h\x0bi\x0cj"
    assert emit(repo, "x", "s", "v", note=nasty) is True
    assert len(lines(repo)) == 1
    note = read_events(repo)[0]["note"]
    assert note == "a b c d e f g h i j"
    assert not any(unicodedata.category(c) == "Cc" for c in note)


def test_E02_plain_spaces_and_non_ascii_text_are_kept(repo):
    emit = emit_fn()
    emit(repo, "x", "s", "v", note="caf\u00e9  \u4e2d\u6587 ok")
    assert read_events(repo)[0]["note"] == "caf\u00e9  \u4e2d\u6587 ok"


def test_E02_lone_surrogates_are_replaced_never_raise(repo):
    emit = emit_fn()
    assert emit(repo, "st\ud800age", "sl\udfffice", "ver\ud83ddict", note="x\ud800y\udc00z", source="so\udbffurce") is True
    raw = (repo / "ops" / "events.jsonl").read_bytes()
    text = raw.decode("utf-8")  # strict decode: the file is valid UTF-8
    assert text.count("\n") == 1
    ev = json.loads(text)
    for k, v in ev.items():
        assert not any(0xD800 <= ord(c) <= 0xDFFF for c in v), k
    assert ev["note"].startswith("x") and "y" in ev["note"] and ev["note"].endswith("z")


def test_E02_a_valid_surrogate_pair_as_one_emoji_survives(repo):
    emit = emit_fn()
    emit(repo, "x", "s", "v", note="ok \U0001F600 ok")
    assert read_events(repo)[0]["note"] == "ok \U0001F600 ok"


def test_E02_stage_slice_verdict_control_characters_cannot_break_the_line(repo):
    emit = emit_fn()
    assert emit(repo, "a\nb", "c\rd", "e\x00f", note="") is True
    assert len(lines(repo)) == 1
    ev = read_events(repo)[0]
    assert "\n" not in ev["stage"] + ev["slice"] + ev["verdict"]


def test_E02_ops_symlinked_outside_root_writes_nothing(repo, tmp_path, capsys):
    emit = emit_fn()
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "ops").symlink_to(outside, target_is_directory=True)
    assert emit(repo, "x", "s", "v") is False
    assert list(outside.iterdir()) == []
    err = capsys.readouterr().err
    assert err.startswith("event not recorded: ") and err.count("\n") == 1  # E-03: one line


def test_E02_events_file_symlinked_outside_root_writes_nothing(repo, tmp_path, capsys):
    emit = emit_fn()
    outside = tmp_path / "victim.jsonl"
    outside.write_text("keep\n")
    (repo / "ops").mkdir()
    (repo / "ops" / "events.jsonl").symlink_to(outside)
    assert emit(repo, "x", "s", "v") is False
    assert outside.read_text() == "keep\n"
    assert capsys.readouterr().err.startswith("event not recorded: ")


def test_E02_dangling_symlink_to_outside_is_refused_and_not_created(repo, tmp_path):
    emit = emit_fn()
    target = tmp_path / "not-yet.jsonl"
    (repo / "ops").mkdir()
    (repo / "ops" / "events.jsonl").symlink_to(target)
    assert emit(repo, "x", "s", "v") is False
    assert not target.exists()


def test_E02_symlinked_ops_is_refused_even_when_it_stays_inside_root(repo):
    # Amended after the independent review (docs/reviews/2026-10-20-sfn-review.md, finding 5): a symlink at ops/ or
    # ops/events.jsonl is refused whatever its target (an in-repo target could be an eval file or a git hook).
    emit = emit_fn()
    (repo / "real_ops").mkdir()
    (repo / "ops").symlink_to(repo / "real_ops", target_is_directory=True)
    assert emit(repo, "x", "s", "v") is False
    assert not (repo / "real_ops" / "events.jsonl").exists()


def _fake(prefix: str, body: str) -> str:
    return prefix + body  # assembled at run time so no secret-shaped literal sits in the repository


@pytest.mark.parametrize("secret", [
    _fake("sk-ant-", "A1b2C3d4E5f6G7h8I9j0K1l2"),
    _fake("ghp_", "A1b2C3d4E5f6G7h8I9j0K1l2"),
    _fake("AKIA", "ABCDEFGHIJKLMNOP"),
    _fake("glpat-", "A1b2C3d4E5f6G7h8I9j0K1l2"),
])
def test_E02_secret_shaped_values_in_note_are_replaced(repo, secret):
    emit = emit_fn()
    from factory.hooks.ledger_audit import redact
    note = f"deployed with {secret} ok"
    assert redact(note) != note  # the shape is one the hooks redact
    assert emit(repo, "x", "s", "v", note=note) is True
    got = read_events(repo)[0]["note"]
    assert secret not in got
    assert got == redact(note)
    assert (repo / "ops" / "events.jsonl").read_text().count(secret) == 0


def test_E02_quoted_credential_assignment_in_note_is_replaced(repo):
    emit = emit_fn()
    from factory.hooks.ledger_audit import redact
    note = 'api_key = "' + "Zz9" * 8 + '" end'
    assert redact(note) != note
    emit(repo, "x", "s", "v", note=note)
    assert "Zz9Zz9Zz9" not in read_events(repo)[0]["note"]


def test_E02_secret_split_by_truncation_boundary_is_not_leaked(repo):
    emit = emit_fn()
    secret = _fake("sk-ant-", "A1b2C3d4E5f6G7h8I9j0K1l2")
    emit(repo, "x", "s", "v", note="p" * 1990 + secret)
    got = read_events(repo)[0]["note"]
    assert len(got) <= 2000
    assert "sk-ant-A1b2C3" not in got


# ------------------------------------------------------------------ E-03

def test_E03_read_only_ops_returns_false_one_line_message_no_raise(repo, capsys):
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions; E03_ops_is_a_file covers the failure path")
    emit = emit_fn()
    (repo / "ops").mkdir()
    (repo / "ops").chmod(0o555)
    try:
        assert emit(repo, "x", "s", "v") is False
    finally:
        (repo / "ops").chmod(0o755)
    cap = capsys.readouterr()
    assert cap.out == ""
    assert re.fullmatch(r"event not recorded: [^\n]+\n", cap.err), repr(cap.err)


def test_E03_ops_path_is_a_regular_file_returns_false_without_raising(repo, capsys):
    emit = emit_fn()
    (repo / "ops").write_text("i am a file\n")
    assert emit(repo, "x", "s", "v") is False
    cap = capsys.readouterr()
    assert re.fullmatch(r"event not recorded: [^\n]+\n", cap.err), repr(cap.err)
    assert (repo / "ops").read_text() == "i am a file\n"


def test_E03_root_that_does_not_exist_returns_false_without_raising(tmp_path, capsys):
    emit = emit_fn()
    assert emit(tmp_path / "missing" / "deeper", "x", "s", "v") is False
    assert capsys.readouterr().err.startswith("event not recorded: ")


def test_E03_events_file_is_a_directory_returns_false(repo, capsys):
    emit = emit_fn()
    (repo / "ops" / "events.jsonl").mkdir(parents=True)
    assert emit(repo, "x", "s", "v") is False
    assert capsys.readouterr().err.startswith("event not recorded: ")


@pytest.mark.parametrize("value", ["off"])
def test_E03_SF_EVENTS_off_writes_nothing_says_nothing_returns_false(repo, capsys, monkeypatch, value):
    emit = emit_fn()
    monkeypatch.setenv("SF_EVENTS", value)
    assert emit(repo, "x", "s", "v") is False
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err == ""
    assert not (repo / "ops").exists()


def test_E03_SF_EVENTS_off_leaves_an_existing_log_untouched(repo, monkeypatch):
    emit = emit_fn()
    emit(repo, "x", "s", "v")
    before = (repo / "ops" / "events.jsonl").read_bytes()
    monkeypatch.setenv("SF_EVENTS", "off")
    assert emit(repo, "y", "s", "v") is False
    assert (repo / "ops" / "events.jsonl").read_bytes() == before


def test_E03_other_SF_EVENTS_values_do_not_disable_events(repo, monkeypatch):
    emit = emit_fn()
    monkeypatch.setenv("SF_EVENTS", "on")
    assert emit(repo, "x", "s", "v") is True


def test_E03_successful_emit_prints_nothing(repo, capsys):
    emit = emit_fn()
    assert emit(repo, "x", "s", "v") is True
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err == ""


def test_E03_failed_writes_never_raise_for_odd_input_types(repo, capsys):
    emit = emit_fn()
    # a bad note type is a caller bug, but telemetry must not take the caller down
    try:
        r = emit(repo, "x", "s", "v", note=None)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"emit raised {type(e).__name__}: {e}")
    assert isinstance(r, bool)
