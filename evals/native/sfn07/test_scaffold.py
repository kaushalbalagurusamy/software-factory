"""Q-01 (format), Q-02 (computed lines, no overwrite), Q-05 (index.json after scaffold)."""
from __future__ import annotations

import json
import re

from .conftest import (C_SIG, CORE, SKILL, UTIL, block, check, codes, doc_path, eli, fill_text, scaffold_all,
                       sections, src_line, write)

LABELS = ["What it does", "Expects", "Gives back", "Used by", "Depends on"]


def _doc(root, module):
    return doc_path(root, module).read_text(encoding="utf-8")


def test_Q01_one_file_per_module_with_title_and_purpose(proj):
    scaffold_all(proj)
    for mod in ("pkg.util", "pkg.core"):
        assert doc_path(proj, mod).is_file(), mod
    lines = _doc(proj, "pkg.core").splitlines()
    assert re.fullmatch(r"# (pkg\.core|pkg/core\.py)", lines[0]), lines[0]
    paras = [p for p in re.split(r"\n\s*\n", _doc(proj, "pkg.core")) if p.strip()]
    assert not paras[1].startswith("#"), "second paragraph must be the one-sentence purpose"
    assert "TODO" in paras[1]


def test_Q01_sections_for_public_symbols_only(proj):
    scaffold_all(proj)
    secs = sections(_doc(proj, "pkg.util"))
    assert set(secs) == {"helper", "ping", "Box", "Box.get"}, set(secs)
    secs = sections(_doc(proj, "pkg.core"))
    assert set(secs) == {"run", "outer", "unresolved", "cached", "fetch"}, set(secs)


def test_Q01_labelled_lines_in_order_with_hidden_sig(proj):
    scaffold_all(proj)
    for mod in ("pkg.util", "pkg.core"):
        for name, sec in sections(_doc(proj, mod)).items():
            found = re.findall(r"(?m)^\*\*(What it does|Expects|Gives back|Used by|Depends on|Watch out):\*\*", sec)
            assert [l for l in found if l != "Watch out"] == LABELS, (name, found)
            assert re.search(r"(?m)^<!-- sig:[0-9a-f]{8} -->\s*$", sec), name


def test_Q01_expects_param_format_and_nothing(proj):
    scaffold_all(proj)
    util = sections(_doc(proj, "pkg.util"))
    assert re.search(r"x \(int\):", block(util["helper"], "Expects"))
    assert "nothing" in block(util["ping"], "Expects").lower()
    # self is not a parameter a reader passes
    assert "self" not in block(util["Box.get"], "Expects")
    core = sections(_doc(proj, "pkg.core"))
    assert re.search(r"url \(str\):", block(core["fetch"], "Expects"))  # async def


def test_Q01_decorated_and_async_get_sections(proj):
    scaffold_all(proj)
    secs = sections(_doc(proj, "pkg.core"))
    assert "cached" in secs and "fetch" in secs
    assert re.search(r"str", block(secs["fetch"], "Gives back"))


def test_Q02_unfilled_text_is_todo_never_invented(proj):
    scaffold_all(proj)
    secs = sections(_doc(proj, "pkg.util"))
    assert "TODO" in block(secs["helper"], "What it does")
    assert "TODO" in block(secs["helper"], "Gives back")
    assert "TODO" in block(secs["helper"], "Expects")


def test_Q02_depends_on_and_used_by_are_computed(proj):
    scaffold_all(proj)
    core = sections(_doc(proj, "pkg.core"))
    util = sections(_doc(proj, "pkg.util"))
    dep = block(core["outer"], "Depends on")
    assert re.search(r"pkg\.core\.run \(pkg/core\.py:\d+\)", dep), dep
    assert re.search(r"pkg\.util\.helper \(pkg/util\.py:\d+\)", dep), dep
    assert "(maybe)" not in "".join(l for l in dep.splitlines() if "run" in l or "helper" in l)
    used = block(util["helper"], "Used by")
    assert re.search(r"pkg\.core\.run \(pkg/core\.py:\d+\)", used), used
    assert re.search(r"pkg\.core\.outer \(pkg/core\.py:\d+\)", used), used
    assert re.search(r"pkg\.util\.Box\.get \(pkg/util\.py:\d+\)", used), used
    # cross-module reference through `from pkg import util; util.Box(...)`
    assert re.search(r"pkg\.util\.Box\b", block(core["run"], "Depends on"))
    assert re.search(r"pkg\.core\.run \(pkg/core\.py:\d+\)", block(util["Box"], "Used by"))
    # a caller's line number points at the call site
    line = src_line(proj, "pkg/core.py", "return run(helper(n))")
    assert re.search(r"pkg\.core\.outer \(pkg/core\.py:%d\)" % line, used), used


def test_Q02_unresolved_calls_are_maybe_not_dropped_not_certain(proj):
    scaffold_all(proj)
    dep = block(sections(_doc(proj, "pkg.core"))["unresolved"], "Depends on")
    lines = [l for l in dep.splitlines() if "mystery_call" in l]
    assert lines, "unresolved call silently dropped:\n" + dep
    assert all("(maybe)" in l for l in lines), lines
    assert "pkg." not in "".join(lines), "must not be claimed as a project symbol"


def test_Q02_leaf_function_has_no_invented_dependencies(proj):
    scaffold_all(proj)
    dep = block(sections(_doc(proj, "pkg.util"))["ping"], "Depends on")
    assert "pkg." not in dep


def test_Q02_scaffold_never_overwrites_human_text(proj):
    scaffold_all(proj)
    path = doc_path(proj, "pkg.util")
    text = fill_text(_doc(proj, "pkg.util"))
    text = text.replace("**What it does:** a plain thing here", "**What it does:** Adds one to a whole number.", 1)
    text = text.replace("x (int): a plain thing here", "x (int): any whole number, for example 41.", 1)
    path.write_text(text, encoding="utf-8")
    # the author also adds a Watch out line to helper
    secs = sections(text)
    path.write_text(text.replace(secs["helper"], secs["helper"].rstrip("\n") + "\n**Watch out:** KEEPME warning.\n\n", 1),
                    encoding="utf-8")
    # source changes: new public function, changed return annotation, new caller
    write(proj, "pkg/util.py", UTIL.replace("def helper(x: int) -> int:", "def helper(x: int) -> str:")
          + "\n\ndef added(a: int) -> int:\n    return helper(a)\n")
    eli("scaffold", "--root", str(proj), "pkg/util.py", cwd=proj)
    after = _doc(proj, "pkg.util")
    assert "Adds one to a whole number." in after
    assert "any whole number, for example 41." in after
    assert "KEEPME warning." in after
    secs = sections(after)
    assert "added" in secs and "TODO" in secs["added"]
    # sig refreshed so the stale-signature finding is gone
    assert C_SIG not in codes(check(proj, "--paths", "pkg/util.py"))


def test_Q02_scaffold_is_idempotent(proj):
    scaffold_all(proj)
    first = {p.name: p.read_bytes() for p in (proj / "docs" / "eli12").iterdir()}
    scaffold_all(proj)
    second = {p.name: p.read_bytes() for p in (proj / "docs" / "eli12").iterdir()}
    assert first == second


def test_Q02_scaffold_sig_is_deterministic_across_trees(tmp_path):
    sigs = []
    for name in ("one", "two"):
        root = tmp_path / name
        write(root, "pkg/util.py", UTIL)
        write(root, "pkg/core.py", CORE)
        scaffold_all(root)
        sigs.append(re.findall(r"sig:([0-9a-f]{8})", _doc(root, "pkg.util")))
    assert sigs[0] == sigs[1] and len(set(sigs[0])) == len(sigs[0]) == 4  # four symbols, four hashes


def test_Q02_scaffold_usage_errors_exit_2(proj):
    assert eli("scaffold", "--root", str(proj), cwd=proj).returncode == 2  # no FILE
    assert eli(cwd=proj).returncode == 2
    assert eli("frobnicate", cwd=proj).returncode == 2


def test_Q02_scaffold_accepts_absolute_paths(proj):
    p = eli("scaffold", "--root", str(proj), str(proj / "pkg" / "util.py"), cwd=proj)
    assert p.returncode == 0, p.stderr
    assert doc_path(proj, "pkg.util").is_file()


def test_Q05_scaffold_writes_machine_readable_index_json(proj):
    scaffold_all(proj)
    data = json.loads((proj / "docs" / "eli12" / "index.json").read_text())
    flat = json.dumps(data)
    assert "docs/eli12/pkg.core.md" in flat and "docs/eli12/pkg.util.md" in flat
    assert "pkg/core.py" in flat or "pkg.core" in flat


def test_Q01_skill_file_exists_with_frontmatter():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head = text.split("---", 2)[1]
    assert re.search(r"(?m)^name:\s*eli12-docs\s*$", head)
    assert re.search(r"(?m)^description:", head)
    for must in ("What it does", "Expects", "Gives back", "Used by", "Depends on", "stage 10", "lsf"):
        assert must in text, must
