"""SFN-03 T-05: `sf qa promote-notes --slice DIR [--root R]` turns the .sf QA attempt log into a committed qa-notes.md."""
from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

from factory.qa.cli import main as qa_main
from factory.qa.store import SliceStore

from .conftest import git, mkrepo, run, sf, tree, write

ERR = "AssertionError: total mismatch for invoice batch 17 at 2026-10-01T10:00:00Z"
ERR_FRAGMENT = "total mismatch for invoice batch"
PROTECTED_LINE = "assert quarterly widget reconciliation matches ledger totals exactly"
EXPECTED_PHRASE = "invoice total equals the sum of its lines"


def qa(root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = qa_main(["--root", str(root), "--slice", "s1", *argv])
    assert rc == 0, (argv, buf.getvalue())
    return buf.getvalue()


def make_qa_root(tmp_path, leak=False, fails=3, proposal=True, name="proj"):
    """A git repo with a QA attempt log for slice s1: `fails` counted failures of one signature."""
    root = mkrepo(tmp_path, {
        ".factory/profile.yaml": "paths:\n  eval:\n    - evals/hidden\n",
        "evals/hidden/test_hidden.py": f"def test_x():\n    {PROTECTED_LINE}\n",
        ".sf/policy.yaml": "flake_reruns: 0\n",
    }, name=name)
    qa(root, "init", "--criteria", "C-1", "C-2")
    err = ERR + (f"\n{PROTECTED_LINE}" if leak else "")
    for _ in range(fails):
        qa(root, "record", "--status", "fail", "--case", "case_invoice", "--criterion", "C-1", "--error", err)
    sig = SliceStore(root, "s1").facts()["current_sig"]
    assert sig
    qa(root, "feedback", "--criterion", "C-1", "--observed", "the total is wrong", "--expected", EXPECTED_PHRASE,
       "--repro", "open the invoice page")
    if proposal:
        qa(root, "regression-propose", "--signature", sig, "--criterion", "C-1", "--input-class", "multi-line invoice",
           "--expected", "totals add up", "--recurred", "case_invoice")
    (root / "docs" / "slices" / "s1").mkdir(parents=True)
    return root, sig


def promote(root, d, *extra, cwd=None):
    return run(cwd or root, "promote-notes", "--slice", str(d), "--root", str(root), *extra, module="factory.qa")


def section(text, sig):
    """The block (a heading and the lines under it, up to the next heading) that mentions `sig`."""
    blocks, cur = [], []
    for ln in text.splitlines():
        if ln.startswith("#") and cur:
            blocks.append("\n".join(cur))
            cur = []
        cur.append(ln)
    blocks.append("\n".join(cur))
    hits = [b for b in blocks if sig in b]
    assert hits, f"nothing mentions signature {sig}:\n{text}"
    return "\n".join(hits)


def test_T05_writes_notes_with_signature_count_criteria_summary_and_proposal(tmp_path):
    root, sig = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    p = promote(root, d)
    assert p.returncode == 0, p.stdout + p.stderr
    notes = (d / "qa-notes.md").read_text()
    s = section(notes, sig)
    assert re.search(r"(?i)attempts?\D{0,15}\b3\b|\b3\s+(?:counted\s+)?(?:attempt|failure)", s), s
    assert "C-1" in s
    assert ERR_FRAGMENT in s, "the observed summary comes from the recorded error"
    assert EXPECTED_PHRASE in s, "the expected summary comes from the QA feedback written for the signature"
    assert "proposal" in s.lower(), "the regression proposal for the signature is referenced"
    assert "C-2" not in s, "only the criteria the signature failed"


def test_T05_attempt_count_follows_the_log(tmp_path):
    root, sig = make_qa_root(tmp_path, fails=2)
    d = root / "docs" / "slices" / "s1"
    assert promote(root, d).returncode == 0
    s = section((d / "qa-notes.md").read_text(), sig)
    assert re.search(r"(?i)attempts?\D{0,15}\b2\b|\b2\s+(?:counted\s+)?(?:attempt|failure)", s), s
    qa(root, "record", "--status", "fail", "--case", "case_invoice", "--criterion", "C-1", "--error", ERR)
    assert promote(root, d).returncode == 0
    s = section((d / "qa-notes.md").read_text(), sig)
    assert re.search(r"(?i)attempts?\D{0,15}\b3\b|\b3\s+(?:counted\s+)?(?:attempt|failure)", s), s


def test_T05_second_run_is_byte_identical_and_changes_nothing_else(tmp_path):
    root, _ = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    assert promote(root, d).returncode == 0
    first = (d / "qa-notes.md").read_bytes()
    before = tree(root)
    assert promote(root, d).returncode == 0
    assert (d / "qa-notes.md").read_bytes() == first
    assert tree(root) == before, "an unchanged second run touches no file (not even the mtime of the notes)"


def test_T05_notes_carry_no_wall_clock_time(tmp_path):
    root, _ = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    assert promote(root, d).returncode == 0
    a = (d / "qa-notes.md").read_bytes()
    (d / "qa-notes.md").unlink()
    import time
    time.sleep(1.1)
    assert promote(root, d).returncode == 0
    assert (d / "qa-notes.md").read_bytes() == a


def test_T05_leak_check_refuses_protected_material_and_writes_nothing(tmp_path):
    root, _ = make_qa_root(tmp_path, leak=True)
    d = root / "docs" / "slices" / "s1"
    before = tree(root)
    p = promote(root, d)
    assert p.returncode == 1, p.stdout + p.stderr
    assert not (d / "qa-notes.md").exists()
    assert tree(root) == before, "nothing at all is written when the leak check refuses"
    assert PROTECTED_LINE not in p.stdout + p.stderr, "findings never echo the protected text"


def test_T05_leak_refusal_keeps_an_existing_notes_file_untouched(tmp_path):
    root, _ = make_qa_root(tmp_path, leak=True)
    d = root / "docs" / "slices" / "s1"
    (d / "qa-notes.md").write_text("previous notes\n")
    assert promote(root, d).returncode == 1
    assert (d / "qa-notes.md").read_text() == "previous notes\n"


def test_T05_writes_only_inside_dir(tmp_path):
    root, _ = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    before = {k: v for k, v in tree(root).items() if not k.startswith("docs/slices/s1/")}
    assert promote(root, d).returncode == 0
    after = {k: v for k, v in tree(root).items() if not k.startswith("docs/slices/s1/")}
    assert after == before
    assert sorted(p.name for p in d.iterdir()) == ["qa-notes.md"]


def test_T05_symlinked_notes_file_that_escapes_dir_is_refused(tmp_path):
    root, _ = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    outside = tmp_path / "outside.md"
    outside.write_text("KEEP\n")
    (d / "qa-notes.md").symlink_to(outside)
    p = promote(root, d)
    assert p.returncode != 0, p.stdout + p.stderr
    assert "invalid choice" not in p.stderr, "the command must exist; the refusal is about the symlink"
    assert re.search(r"(?i)symlink|outside|escape", p.stderr), p.stderr
    assert outside.read_text() == "KEEP\n"
    assert (d / "qa-notes.md").is_symlink()


def test_T05_symlinked_dir_that_escapes_the_root_is_refused(tmp_path):
    root, _ = make_qa_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "linked").mkdir()
    link = root / "linked" / "s1"  # same slice id as the real log, so only the escape can cause the refusal
    link.symlink_to(elsewhere)
    p = promote(root, link)
    assert p.returncode != 0
    assert "invalid choice" not in p.stderr, "the command must exist; the refusal is about the symlink"
    assert re.search(r"(?i)symlink|outside|escape", p.stderr), p.stderr
    assert list(elsewhere.iterdir()) == []


def test_T05_missing_attempt_log_exits_1_and_writes_nothing(tmp_path):
    root = mkrepo(tmp_path, {".factory/profile.yaml": "paths:\n  eval:\n    - evals/hidden\n",
                             "evals/hidden/t.py": "x = 1\n"})
    d = root / "docs" / "slices" / "nolog"
    d.mkdir(parents=True)
    p = promote(root, d)
    assert p.returncode == 1, p.stdout + p.stderr
    assert ".sf" in p.stderr, "the message names the missing log"
    assert not (d / "qa-notes.md").exists()


def test_T05_a_slice_with_a_log_but_no_failures_writes_no_failure_sections(tmp_path):
    root = mkrepo(tmp_path, {".factory/profile.yaml": "paths:\n  eval:\n    - evals/hidden\n",
                             "evals/hidden/t.py": "x = 1\n", ".sf/policy.yaml": "flake_reruns: 0\n"})
    qa(root, "init", "--criteria", "C-1")
    qa(root, "record", "--status", "pass", "--case", "ok_case", "--criterion", "C-1")
    d = root / "docs" / "slices" / "s1"
    d.mkdir(parents=True)
    p = promote(root, d)
    assert p.returncode == 0, p.stdout + p.stderr
    text = (d / "qa-notes.md").read_text() if (d / "qa-notes.md").exists() else ""
    assert "case_invoice" not in text and not re.search(r"\b[0-9a-f]{16}\b", text)


def test_T05_the_sf_cli_dispatches_promote_notes(tmp_path):
    root, sig = make_qa_root(tmp_path)
    d = root / "docs" / "slices" / "s1"
    p = sf(root, "qa", "promote-notes", "--slice", str(d), "--root", str(root))
    assert p.returncode == 0, p.stdout + p.stderr
    assert sig in (d / "qa-notes.md").read_text()
