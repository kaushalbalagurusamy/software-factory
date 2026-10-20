"""Q-03 check: exit codes, finding codes, boundaries, --paths, --changed, --json."""
from __future__ import annotations

import json
import os
import re
import subprocess

from .conftest import (C_DEPS, C_FORMAT, C_JARGON, C_LONG, C_MISSING, C_ORPHAN, C_PARAM, C_SIG, C_TODO, C_UNPARSE, SKILL,
                       CORE, UTIL, check, codes, doc_path, edit_section, eli, fill_all, findings, scaffold_all, write)


def _edit_doc(root, module, fn):
    p = doc_path(root, module)
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def _what(sentence):
    return lambda t: edit_section(t, "helper", lambda s: re.sub(r"(?m)^\*\*What it does:\*\*.*$",
                                                                 "**What it does:** " + sentence, s, 1))


def test_Q03_clean_project_exits_0_with_no_output(clean):
    p = check(clean)
    assert p.returncode == 0 and p.stdout.strip() == ""


def test_Q03_usage_errors_exit_2(clean, tmp_path):
    assert eli("check", "--root", str(tmp_path / "does-not-exist"), cwd=clean).returncode == 2
    assert eli("check", "--bogus-flag", cwd=clean).returncode == 2


def test_Q03_missing_entry(clean):
    write(clean, "pkg/util.py", UTIL + "\n\ndef brand_new(a: int) -> int:\n    return a\n")
    p = check(clean)
    assert p.returncode == 1
    hits = [f for f in findings(p) if f["code"] == C_MISSING]
    assert hits and any("brand_new" in f["msg"] for f in hits)


def test_Q03_missing_entry_when_no_doc_file_at_all(proj):
    p = check(proj)
    assert p.returncode == 1
    assert {"helper", "run"} <= {f["msg"].split()[0].strip("`'\"") for f in findings(p) if f["code"] == C_MISSING} \
        or any("helper" in f["msg"] for f in findings(p) if f["code"] == C_MISSING)


def test_Q03_private_names_need_no_entry(clean):
    # clean fixture already has _private and Box._hidden undocumented; also __init__
    assert check(clean).returncode == 0


def test_Q03_orphan_entry_when_symbol_removed(clean):
    write(clean, "pkg/core.py", CORE.replace("def outer(n: int) -> int:\n    return run(helper(n))\n", ""))
    p = check(clean)
    assert p.returncode == 1
    assert any(f["code"] == C_ORPHAN and "outer" in f["msg"] for f in findings(p))


def test_Q03_signature_change_is_stale_signature(clean):
    write(clean, "pkg/util.py", UTIL.replace("def helper(x: int) -> int:", "def helper(x: int, y: int = 0) -> int:"))
    p = check(clean)
    assert p.returncode == 1
    assert any(f["code"] == C_SIG and "helper" in f["msg"] for f in findings(p))


def test_Q03_rename_param_and_annotation_changes_are_stale(clean):
    write(clean, "pkg/util.py", UTIL.replace("def helper(x: int)", "def helper(z: int)"))
    assert C_SIG in codes(check(clean))
    write(clean, "pkg/util.py", UTIL.replace("def helper(x: int) -> int:", "def helper(x: float) -> int:"))
    assert C_SIG in codes(check(clean))
    write(clean, "pkg/util.py", UTIL.replace("def helper(x: int) -> int:", "def helper(x: int) -> float:"))
    assert C_SIG in codes(check(clean))


def test_Q03_body_only_edit_and_line_shift_are_not_stale(clean):
    write(clean, "pkg/util.py", UTIL.replace("return x + 1", "return x + 2"))
    assert check(clean).returncode == 0
    # inserting lines shifts every path:line; names are what is compared
    write(clean, "pkg/util.py", "# shifted\n# down\n" + UTIL.replace("return x + 1", "return x + 2"))
    write(clean, "pkg/core.py", "# shifted\n" + CORE)
    p = check(clean)
    assert p.returncode == 0, p.stdout


def test_Q03_decorator_change_is_not_a_signature_change(clean):
    write(clean, "pkg/core.py", CORE.replace("@functools.lru_cache(maxsize=None)", "@functools.lru_cache(maxsize=8)"))
    assert C_SIG not in codes(check(clean))


def test_Q03_dependency_change_after_editing_a_call(clean):
    write(clean, "pkg/core.py", CORE.replace("return run(helper(n))", "return unresolved(helper(n))"))
    p = check(clean)
    assert p.returncode == 1
    msgs = [f["msg"] for f in findings(p) if f["code"] == C_DEPS]
    assert any("outer" in m for m in msgs), msgs          # outer now depends on unresolved
    assert any("run" in m for m in msgs), msgs            # run lost a user (its Used by changed)


def test_Q03_dependency_change_in_other_module_flags_callee_doc(clean):
    write(clean, "pkg/util.py", UTIL.replace("        return helper(self.v)", "        return self.v"))
    p = check(clean)
    assert any(f["code"] == C_DEPS and "helper" in f["msg"] for f in findings(p)), p.stdout
    assert any(f["code"] == C_DEPS and "get" in f["msg"] for f in findings(p)), p.stdout


def test_Q03_todo_detected_with_exact_doc_line(clean):
    path = doc_path(clean, "pkg.util")
    lines = path.read_text().splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith("**What it does:**"))
    lines[idx] = "**What it does:** TODO"
    path.write_text("\n".join(lines) + "\n")
    p = check(clean)
    hits = [f for f in findings(p) if f["code"] == C_TODO]
    assert [int(f["line"]) for f in hits] == [idx + 1]
    assert hits[0]["path"].endswith("pkg.util.md")


def test_Q03_section_label_order(clean):
    def swap(sec):
        a = re.search(r"(?m)^\*\*Expects:\*\*.*$", sec).group(0)
        b = re.search(r"(?m)^\*\*Gives back:\*\*.*$", sec).group(0)
        return sec.replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
    _edit_doc(clean, "pkg.util", lambda t: edit_section(t, "ping", swap))
    p = check(clean)
    assert p.returncode == 1
    assert any(f["code"] == C_FORMAT and "ping" in f["msg"] for f in findings(p))


def test_Q03_missing_labelled_line(clean):
    _edit_doc(clean, "pkg.util", lambda t: edit_section(
        t, "ping", lambda s: re.sub(r"(?m)^\*\*Gives back:\*\*.*\n", "", s, 1)))
    p = check(clean)
    assert any(f["code"] == C_FORMAT and "ping" in f["msg"] for f in findings(p)), p.stdout


def test_Q03_what_it_does_word_limit_25_vs_26(clean):
    ok = " ".join(["word"] * 24 + ["end."])         # exactly 25 words
    bad = " ".join(["word"] * 25 + ["end."])        # 26 words
    _edit_doc(clean, "pkg.util", _what(ok))
    assert check(clean).returncode == 0
    _edit_doc(clean, "pkg.util", _what(bad))
    p = check(clean)
    assert p.returncode == 1 and any(f["code"] == C_LONG and "helper" in f["msg"] for f in findings(p))


def test_Q03_what_it_does_must_be_one_sentence(clean):
    _edit_doc(clean, "pkg.util", _what("It adds one. It also logs."))
    p = check(clean)
    assert any(f["code"] == C_LONG and "helper" in f["msg"] for f in findings(p)), p.stdout
    _edit_doc(clean, "pkg.util", _what("It adds one to the number you give it."))
    assert check(clean).returncode == 0


def _watch(n):
    prefix = "**Watch out:** "
    body = ("abc " * 80)[: n - len(prefix) - 1].rstrip()
    line = prefix + body + "z" * (n - len(prefix) - len(body))
    assert len(line) == n
    return lambda t: edit_section(t, "ping", lambda s: s.rstrip("\n") + "\n" + line + "\n\n")


def test_Q03_line_length_160_ok(clean):
    _edit_doc(clean, "pkg.util", _watch(160))
    assert check(clean).returncode == 0


def test_Q03_line_length_161_too_long(clean):
    _edit_doc(clean, "pkg.util", _watch(161))
    p = check(clean)
    assert p.returncode == 1
    assert any(f["code"] == C_LONG for f in findings(p)), p.stdout


def test_Q03_param_line_format(clean):
    _edit_doc(clean, "pkg.util", lambda t: edit_section(
        t, "helper", lambda s: s.replace("x (int):", "x -", 1)))
    p = check(clean)
    assert any(f["code"] == C_PARAM and "helper" in f["msg"] for f in findings(p)), p.stdout
    _edit_doc(clean, "pkg.util", lambda t: edit_section(
        t, "helper", lambda s: s.replace("x -", "x (int):", 1)))
    assert check(clean).returncode == 0


def test_Q03_unparseable_file_is_a_finding_not_a_skip(clean):
    write(clean, "pkg/broken.py", "def oops(:\n    pass\n")
    p = check(clean)
    assert p.returncode == 1
    hits = [f for f in findings(p) if f["code"] == C_UNPARSE]
    assert len(hits) == 1 and hits[0]["path"].endswith("pkg/broken.py")
    assert "Traceback" not in p.stderr
    # healthy modules are still checked in the same run
    write(clean, "pkg/util.py", UTIL.replace("def helper(x: int) -> int:", "def helper(x: int, y: int = 0) -> int:"))
    assert C_SIG in codes(check(clean))


def test_Q03_scaffold_does_not_write_doc_for_unparseable(proj):
    write(proj, "pkg/broken.py", "def oops(:\n    pass\n")
    eli("scaffold", "--root", str(proj), "pkg/broken.py", cwd=proj)
    assert not doc_path(proj, "pkg.broken").exists()


def test_Q03_jargon_flagged_without_glossary_entry(clean):
    write(clean, "docs/eli12/jargon.txt", "idempotent\nzorblax\n")
    _edit_doc(clean, "pkg.util", _what("It is idempotent and adds one."))
    p = check(clean)
    assert p.returncode == 1
    assert any(f["code"] == C_JARGON and "idempotent" in f["msg"] for f in findings(p)), p.stdout
    # case-insensitive
    _edit_doc(clean, "pkg.util", _what("It is IDEMPOTENT and adds one."))
    assert C_JARGON in codes(check(clean))
    # glossary entry silences it
    write(clean, "docs/eli12/GLOSSARY.md",
          "# Glossary\n\n## idempotent\n\n**idempotent**: doing it twice gives the same result as once.\n")
    assert C_JARGON not in codes(check(clean))


def test_Q03_jargon_matches_whole_words_only(clean):
    write(clean, "docs/eli12/jargon.txt", "api\n")
    _edit_doc(clean, "pkg.util", _what("It adds one to a capital number."))
    assert C_JARGON not in codes(check(clean))


def test_Q03_jargon_root_list_replaces_shipped_default(clean):
    write(clean, "docs/eli12/jargon.txt", "zorblax\n")
    shipped = _shipped_terms()
    _edit_doc(clean, "pkg.util", _what("It uses %s and adds one." % shipped[0]))
    assert C_JARGON not in codes(check(clean))
    _edit_doc(clean, "pkg.util", _what("It uses zorblax and adds one."))
    assert C_JARGON in codes(check(clean))


def test_Q03_shipped_default_jargon_list_used_when_root_has_none(clean):
    shipped = _shipped_terms()
    assert not (clean / "docs" / "eli12" / "jargon.txt").exists()
    _edit_doc(clean, "pkg.util", _what("It is %s and adds one." % shipped[0]))
    assert any(f["code"] == C_JARGON for f in findings(check(clean)))


def _shipped_terms():
    files = sorted(SKILL.glob("**/jargon*.txt"))
    assert files, "no shipped default jargon list inside skills/eli12-docs"
    terms = [l.strip() for l in files[0].read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert terms
    return terms


def test_Q03_output_is_one_finding_per_line(clean):
    write(clean, "pkg/util.py", UTIL + "\n\ndef brand_new(a: int) -> int:\n    return a\n")
    write(clean, "pkg/broken.py", "def oops(:\n")
    p = check(clean)
    assert p.returncode == 1
    fs = findings(p)  # asserts every non-empty stdout line matches path:line: code: message
    assert len(fs) >= 2 and len(fs) == len([l for l in p.stdout.splitlines() if l.strip()])


def test_Q03_output_is_deterministic(clean):
    write(clean, "pkg/util.py", UTIL + "\n\ndef brand_new(a: int) -> int:\n    return a\n")
    assert check(clean).stdout == check(clean).stdout


def test_Q03_json_output_valid_and_matches_text(clean):
    write(clean, "pkg/util.py", UTIL + "\n\ndef brand_new(a: int) -> int:\n    return a\n")
    text = findings(check(clean))
    p = check(clean, "--json")
    assert p.returncode == 1
    data = json.loads(p.stdout)
    items = data["findings"] if isinstance(data, dict) else data
    assert len(items) == len(text)
    for it in items:
        assert {"path", "line", "code", "message"} <= set(it), it
        assert isinstance(it["line"], int)
    assert {(i["path"], i["line"], i["code"]) for i in items} == {(f["path"], int(f["line"]), f["code"]) for f in text}


def test_Q03_json_clean_is_valid_json_exit_0(clean):
    p = check(clean, "--json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert (data["findings"] if isinstance(data, dict) else data) == []


def test_Q03_paths_limits_scope(clean):
    write(clean, "pkg/util.py", UTIL + "\n\ndef brand_new(a: int) -> int:\n    return a\n")
    write(clean, "pkg/core.py", CORE + "\n\ndef another(a: int) -> int:\n    return a\n")
    p = check(clean, "--paths", "pkg/core.py")
    msgs = " ".join(f["msg"] for f in findings(p))
    assert "another" in msgs and "brand_new" not in msgs


# ---- --changed -----------------------------------------------------------------------------------------------------

def _git(root, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    return subprocess.run(["git", *args], cwd=str(root), env=env, check=True, capture_output=True, text=True)


def test_Q03_changed_scope_includes_changed_and_mentioning_modules(proj):
    # three modules: util (changes), core (mentions util in its docs), solo (unrelated, has a TODO since the base)
    write(proj, "pkg/solo.py", "def alone(a: int) -> int:\n    return a\n")
    scaffold_all(proj, ("pkg/util.py", "pkg/core.py", "pkg/solo.py"))
    fill_all(proj)
    # pre-existing, unrelated problems: a TODO in core's docs (core mentions util) and in solo's docs
    for mod in ("pkg.core", "pkg.solo"):
        p = doc_path(proj, mod)
        p.write_text(re.sub(r"(?m)^\*\*What it does:\*\* .*$", "**What it does:** TODO", p.read_text(), count=1))
    _git(proj, "init", "-q")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "base")
    _git(proj, "tag", "base")
    write(proj, "pkg/util.py", UTIL.replace("return x + 1", "return x + 2"))   # util changed, docs still fine
    _git(proj, "commit", "-q", "-am", "edit util")
    everything = findings(check(proj))
    scoped = findings(check(proj, "--changed", "base"))
    ev_paths = {f["path"] for f in everything}
    sc_paths = {f["path"] for f in scoped}
    assert any(p.endswith("pkg.solo.md") for p in ev_paths) and any(p.endswith("pkg.core.md") for p in ev_paths)
    assert any(p.endswith("pkg.core.md") for p in sc_paths), "module whose docs mention a changed module is in scope"
    assert not any(p.endswith("pkg.solo.md") for p in sc_paths), "unrelated module must be out of scope"


def test_Q03_changed_with_nothing_changed_is_clean_even_if_other_findings(proj):
    write(proj, "pkg/solo.py", "def alone(a: int) -> int:\n    return a\n")
    scaffold_all(proj, ("pkg/solo.py",))        # all TODO, never filled
    _git(proj, "init", "-q")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "base")
    assert check(proj).returncode == 1
    p = check(proj, "--changed", "HEAD")
    assert p.returncode == 0 and p.stdout.strip() == ""


def test_Q03_changed_with_bad_ref_is_usage_error(proj):
    _git(proj, "init", "-q")
    assert check(proj, "--changed", "no-such-ref").returncode == 2
