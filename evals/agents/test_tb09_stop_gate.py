"""TB-09: Implement stop gate hook (R-15).

Expectations come only from docs/prds/TB-09-stop-gate.md and docs/contracts/hook-io.md / profile.md.
Each fixture project is a real temporary git repository: an initial commit, then the change under test.
The transcript (agent_transcript_path) is written outside the repository so it never enters the change set.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from evals.agents import lib

HOOK = "factory.hooks.stop_gate"
R = ["R-15"]


def case(cid: str, tier: str = "diagnostic", reqs=None):
    return pytest.mark.case(cid, tier=tier, tb="09", reqs=reqs or R)


# ---------------------------------------------------------------- fixtures

CALC = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    return -a\n"
TEST_CALC = (
    "from src.calc import add\n\n\n"
    "def test_add():\n    assert add(1, 2) == 3\n\n\n"
    "def test_add_negative():\n    assert add(-1, -2) == -3\n"
)
TEST_CALC_JS = (
    'const { add } = require("../src/calc.js");\n\n'
    'describe("add", () => {\n  it("adds", () => {\n    expect(add(1, 2)).toBe(3);\n  });\n});\n'
)
FROZEN = "def test_contract():\n    assert 2 + 2 == 4\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def prof(name: str = "base", checks: bool = False, **paths) -> dict:
    """Fixture profile. By default `checks` is removed so behaviour 5 is skipped (PRD: 'if checks.test is not
    set, this check is skipped'), isolating the check under test."""
    data = lib.profile_dict(name)
    if not checks:
        data.pop("checks", None)
    for k, v in paths.items():
        data["paths"][k] = v
    return data


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=root, check=True, capture_output=True, text=True)


def repo(tmp_path: Path, profile: dict | str | None = None, committed: dict | None = None,
         changes: dict | None = None, deletions=(), stage=()) -> Path:
    """git init + initial commit of `committed` (plus .factory/profile.yaml), then apply `changes`/`deletions`."""
    files = {"src/calc.py": CALC, "tests/test_calc.py": TEST_CALC, "README.md": "fixture\n"}
    files.update(committed or {})
    root = lib.make_project(tmp_path, profile if profile is not None else prof(), files=files)
    git(root, "init", "-q")
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "initial")
    for rel, content in (changes or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for rel in deletions:
        (root / rel).unlink()
    for rel in stage:
        git(root, "add", rel)
    return root


def transcript(tmp_path: Path, calls=()) -> Path:
    """Claude Code native transcript JSON lines: assistant tool_use blocks followed by user tool_result lines."""
    p = tmp_path / "transcript.jsonl"
    lines = [{"type": "user", "message": {"role": "user", "content": "Implement the change."}}]
    for i, (name, inp) in enumerate(calls):
        lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": inp}]}})
        lines.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"toolu_{i}", "content": "ok"}]}})
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return p


def stop_payload(root: Path, tmp_path: Path, agent_type: str = "implement", agent_id: str = "impl-1",
                 tp: Path | None = None) -> dict:
    tp = tp or transcript(tmp_path)
    return lib.payload(root, event="SubagentStop", agent_type=agent_type, agent_id=agent_id,
                       agent_transcript_path=str(tp), last_assistant_message="Done.", stop_hook_active=False)


def decide(root: Path, pl: dict):
    return lib.run_decide(HOOK, pl, root)


def cli(root: Path, pl: dict, env: dict | None = None) -> str:
    """Run through the command line; returns 'allow' or 'block' per the hook-io adapter table (Stop/SubagentStop)."""
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.hooks.registry")
    lib.need(HOOK, "decide")
    proc = lib.run_cli("stop_gate", pl, root, env=env)
    assert proc.returncode == 0, f"Stop/SubagentStop must exit 0, got {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    if not out:
        return "allow"
    data = json.loads(out)
    assert data.get("decision") == "block" and data.get("reason"), out
    return "block"


def with_test_fn(extra: str) -> str:
    return TEST_CALC + "\n\n" + extra


CLEAN_CALC = CALC + "\n\ndef sub(a, b):\n    return a - b\n"
CLEAN_TEST = TEST_CALC.replace("from src.calc import add", "from src.calc import add, sub") + \
    "\n\ndef test_sub():\n    assert sub(3, 1) == 2\n"


# ---------------------------------------------------------------- golden

@case("TB09-G-001", "golden")
def test_g001_added_skip_marker_blocks(tmp_path):
    """PRD b3: 'Blocks when the added lines contain a new skip ... marker (`@pytest.mark.skip` ...)'; b8: the
    reason names the file."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": TEST_CALC.replace(
        "def test_add_negative", '@pytest.mark.skip(reason="later")\ndef test_add_negative')})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_calc.py" in d.reason


@case("TB09-G-002", "golden")
def test_g002_trivial_assert_true_blocks(tmp_path):
    """PRD b3: blocks when added lines contain a trivial assertion (`assert True`)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": TEST_CALC.replace(
        "assert add(-1, -2) == -3", "assert True")})
    assert decide(root, stop_payload(root, tmp_path)).kind == "block"


@case("TB09-G-003", "golden")
def test_g003_removed_test_function_blocks(tmp_path):
    """PRD b3: blocks 'when a test file or test function is removed'."""
    lib.need(HOOK, "decide")
    body = "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    root = repo(tmp_path, changes={"tests/test_calc.py": body})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_calc.py" in d.reason


@case("TB09-G-004", "golden")
def test_g004_frozen_hash_mismatch_blocks(tmp_path):
    """PRD b4: blocks when a file matching `paths.frozen_tests` has a SHA-256 that differs from its entry in
    `.factory/baseline.json`."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": sha(FROZEN)})},
                changes={"tests/frozen/test_contract.py": FROZEN.replace("== 4", "== 4 or True")})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_contract.py" in d.reason


@case("TB09-G-005", "golden")
def test_g005_change_outside_own_paths_blocks(tmp_path):
    """PRD b6: if `.factory/own.json` exists, blocks when the change set includes a file outside those paths."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"README.md": "fixture, edited\n"})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "README.md" in d.reason


@case("TB09-G-006", "golden")
def test_g006_clean_change_allows(tmp_path):
    """Negative control. PRD b3-b6: a change that adds a real function and a real test, keeps frozen files at their
    baseline hash and stays inside own paths trips no check, so the gate allows."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": sha(FROZEN)}),
                                     ".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"src/calc.py": CLEAN_CALC, "tests/test_calc.py": CLEAN_TEST})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


@case("TB09-G-007", "golden")
def test_g007_other_role_allowed(tmp_path):
    """Negative control. PRD b1: 'for every other role, allow' (a review sub-agent stopping with a skip marker in
    the tree is not this hook's concern)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": with_test_fn('@pytest.mark.skip\ndef test_x():\n    pass\n')})
    assert decide(root, stop_payload(root, tmp_path, agent_type="review")).kind == "allow"


@case("TB09-G-008", "golden")
def test_g008_iteration_cap_five_blocks_then_allow(tmp_path):
    """PRD b7: 'it blocks at most 5 times per `agent_id` ... after that it allows'. Calls 1 to 5 block, call 6
    allows (driven through the command line so decide and record both run)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": TEST_CALC.replace("assert add(-1, -2) == -3", "assert True")})
    pl = stop_payload(root, tmp_path, agent_id="cap-1")
    results = [cli(root, pl) for _ in range(6)]
    assert results == ["block"] * 5 + ["allow"]


@case("TB09-G-009", "golden")
def test_g009_reason_lists_every_failed_check(tmp_path):
    """PRD b8: 'Each block reason lists every failed check with file names'. Three failures in three files: a skip
    marker, a frozen hash mismatch and a file outside own paths."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": sha(FROZEN)}),
                                     ".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"tests/test_calc.py": with_test_fn("@pytest.mark.xfail\ndef test_x():\n    assert add(1, 1) == 3\n"),
                         "tests/frozen/test_contract.py": FROZEN + "# touched\n",
                         "README.md": "edited\n"})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    for name in ("test_calc.py", "test_contract.py", "README.md"):
        assert name in d.reason, name


# ---------------------------------------------------------------- diagnostic: b3 markers and trivial assertions

PY_ADD = {
    "skipif": '@pytest.mark.skipif(True, reason="x")\ndef test_x():\n    assert add(1, 1) == 2\n',
    "xfail": "@pytest.mark.xfail\ndef test_x():\n    assert add(1, 1) == 2\n",
    "pytest_skip_call": 'def test_x():\n    pytest.skip("later")\n',
    "unittest_skip": '@unittest.skip("later")\ndef test_x():\n    assert add(1, 1) == 2\n',
    "assert_1": "def test_x():\n    assert 1\n",
    "assertTrue_True": "class T:\n    def test_x(self):\n        self.assertTrue(True)\n",
}
JS_ADD = {
    "it_skip": '  it.skip("later", () => {\n    expect(add(2, 2)).toBe(4);\n  });\n',
    "test_skip": '  test.skip("later", () => {\n    expect(add(2, 2)).toBe(4);\n  });\n',
    "xit": '  xit("later", () => {\n    expect(add(2, 2)).toBe(4);\n  });\n',
    "xdescribe": '  xdescribe("later", () => {\n    it("a", () => { expect(add(2, 2)).toBe(4); });\n  });\n',
    "expect_true": '  it("trivial", () => {\n    expect(true).toBe(true);\n  });\n',
}


@pytest.mark.parametrize("key", [
    pytest.param(k, marks=case(f"TB09-D-{i:03d}"), id=k) for i, k in enumerate(PY_ADD, start=1)])
def test_d_python_marker_blocks(tmp_path, key):
    """PRD b3: each listed skip / expected-failure marker (`skipif`, `xfail`, `pytest.skip(`, `@unittest.skip`) and
    trivial assertion (`assert 1`, `assertTrue(True)`) in added lines blocks."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": with_test_fn(PY_ADD[key])})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_calc.py" in d.reason


@pytest.mark.parametrize("key", [
    pytest.param(k, marks=case(f"TB09-D-{i:03d}"), id=k) for i, k in enumerate(JS_ADD, start=7)])
def test_d_js_marker_blocks(tmp_path, key):
    """PRD b3: JS markers `it.skip`, `test.skip`, `xit`, `xdescribe` and the trivial `expect(true).toBe(true)` in
    added lines block."""
    lib.need(HOOK, "decide")
    changed = TEST_CALC_JS[: TEST_CALC_JS.rindex("});")] + JS_ADD[key] + "});\n"
    root = repo(tmp_path, committed={"tests/calc.test.js": TEST_CALC_JS}, changes={"tests/calc.test.js": changed})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "calc.test.js" in d.reason


# ---------------------------------------------------------------- diagnostic: b3 removals

@case("TB09-D-012")
def test_d012_deleted_test_file_blocks(tmp_path):
    """PRD b3: blocks when a test file is removed (tracked tests/test_calc.py deleted)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, deletions=["tests/test_calc.py"])
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_calc.py" in d.reason


@case("TB09-D-013")
def test_d013_removing_a_skip_marker_allows(tmp_path):
    """Negative control. PRD b3 looks at *added* lines: deleting an existing skip marker (a removed line) while
    keeping the test function is not a block."""
    lib.need(HOOK, "decide")
    skipped = TEST_CALC.replace("def test_add_negative", '@pytest.mark.skip(reason="old")\ndef test_add_negative')
    root = repo(tmp_path, committed={"tests/test_calc.py": skipped}, changes={"tests/test_calc.py": TEST_CALC})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


@case("TB09-D-014")
def test_d014_removing_non_test_function_allows(tmp_path):
    """Negative control. PRD b3 blocks removal of a *test* file or *test* function; removing an application
    function (`neg` in src/calc.py) is allowed."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"src/calc.py": "def add(a, b):\n    return a + b\n"})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


# ---------------------------------------------------------------- diagnostic: b2 change set

@case("TB09-D-015")
def test_d015_staged_change_is_in_change_set(tmp_path):
    """PRD b2: the change set comes from `git diff HEAD` (which includes staged changes); a staged skip marker
    blocks."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"])}, stage=["tests/test_calc.py"])
    assert decide(root, stop_payload(root, tmp_path)).kind == "block"


@case("TB09-D-016")
def test_d016_git_unavailable_blocks_cli(tmp_path):
    """PRD b2: 'if git is unavailable, block with a reason'. PATH points at an empty directory so no `git`
    executable can be found; the command line must answer block (exit 0 + decision block)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"src/calc.py": CLEAN_CALC})
    empty = tmp_path / "emptybin"
    empty.mkdir()
    assert cli(root, stop_payload(root, tmp_path), env={"PATH": str(empty)}) == "block"


@case("TB09-D-017")
def test_d017_git_unavailable_blocks_decide(tmp_path, monkeypatch):
    """PRD b2: git unavailable -> block with a reason (decide returns a block Decision, not an exception)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"src/calc.py": CLEAN_CALC})
    pl = stop_payload(root, tmp_path)
    empty = tmp_path / "emptybin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    d = decide(root, pl)
    assert d.kind == "block" and d.reason


# ---------------------------------------------------------------- diagnostic: b4 frozen tests

@case("TB09-D-018")
def test_d018_frozen_file_missing_from_manifest_blocks(tmp_path):
    """PRD b4: 'a frozen file missing from the manifest also blocks'."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN, "tests/frozen/test_other.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": sha(FROZEN)})})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_other.py" in d.reason


@case("TB09-D-019")
def test_d019_missing_baseline_with_frozen_file_blocks(tmp_path):
    """PRD b4 (missing-file boundary): with no `.factory/baseline.json`, every frozen file is missing from the
    manifest, so the gate blocks."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN})
    assert cli(root, stop_payload(root, tmp_path)) == "block"


@case("TB09-D-020")
def test_d020_no_frozen_files_no_baseline_allows(tmp_path):
    """Negative control. PRD b4 concerns files matching `paths.frozen_tests`; with none present and no manifest,
    nothing is frozen and a clean change is allowed."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"src/calc.py": CLEAN_CALC, "tests/test_calc.py": CLEAN_TEST})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


@case("TB09-D-021")
def test_d021_frozen_hash_checked_on_disk_not_only_diff(tmp_path):
    """PRD b4: the check compares the SHA-256 of every file matching `paths.frozen_tests` with the manifest, so a
    committed, unchanged frozen file whose manifest digest is wrong still blocks."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": "0" * 64})})
    assert decide(root, stop_payload(root, tmp_path)).kind == "block"


@case("TB09-D-022")
def test_d022_empty_baseline_file_blocks(tmp_path):
    """PRD b4 (empty-file boundary): an empty `.factory/baseline.json` holds no digest for the frozen file, so the
    gate must not allow (checked through the command line, where a hook error is also a block)."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN, ".factory/baseline.json": ""})
    assert cli(root, stop_payload(root, tmp_path)) == "block"


@case("TB09-D-023")
def test_d023_alt_profile_frozen_path_blocks(tmp_path):
    """PRD b4 with the alt profile (`frozen_tests: [qa/frozen/**]`): a mismatched qa/frozen file blocks."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, profile=prof("alt"),
                committed={"qa/frozen/test_contract.py": FROZEN,
                           ".factory/baseline.json": json.dumps({"qa/frozen/test_contract.py": sha(FROZEN)})},
                changes={"qa/frozen/test_contract.py": FROZEN + "# edited\n"})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_contract.py" in d.reason


@case("TB09-D-024")
def test_d024_alt_profile_ignores_base_frozen_path(tmp_path):
    """PRD b4 reads `paths.frozen_tests` from the profile: under alt, tests/frozen/** is not frozen, so an
    unchanged file there without a manifest entry does not block."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, profile=prof("alt"), committed={"tests/frozen/test_contract.py": FROZEN})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


# ---------------------------------------------------------------- diagnostic: b6 own paths

@case("TB09-D-025")
def test_d025_untracked_file_outside_own_paths_blocks(tmp_path):
    """PRD b2 + b6: untracked files (`git ls-files --others --exclude-standard`) are in the change set; a new file
    outside own.json paths blocks and is named."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"scripts/tool.py": "print('x')\n"})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "tool.py" in d.reason


@case("TB09-D-026")
def test_d026_changes_inside_own_paths_allow(tmp_path):
    """Negative control. PRD b6: every changed file inside own.json paths -> no block from this check."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"src/calc.py": CLEAN_CALC, "tests/test_calc.py": CLEAN_TEST, "src/new_mod.py": "X = 1\n"})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


@case("TB09-D-027")
def test_d027_no_own_json_means_no_path_check(tmp_path):
    """PRD b6: the own-paths check applies only 'If `.factory/own.json` ... exists'; without it, editing README.md
    is allowed."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"README.md": "edited\n", "docs/notes.md": "new\n"})
    assert decide(root, stop_payload(root, tmp_path)).kind == "allow"


# ---------------------------------------------------------------- diagnostic: b5 evidence of a test run
# Transcripts use Claude Code's native JSON-lines format (see coverage/ambiguities-C.md, item C-01).

EDIT = ("Edit", {"file_path": "src/calc.py", "old_string": "a + b", "new_string": "b + a"})
WRITE = ("Write", {"file_path": "src/new_mod.py", "content": "X = 1\n"})


def b5(tmp_path, calls, profile_name="base"):
    root = repo(tmp_path, profile=prof(profile_name, checks=True), changes={"src/calc.py": CLEAN_CALC})
    return decide(root, stop_payload(root, tmp_path, tp=transcript(tmp_path, calls)))


@case("TB09-D-028")
def test_d028_test_run_after_last_edit_allows(tmp_path):
    """PRD b5: a Bash call containing `checks.test` (`pytest -q`) after the last Edit/Write satisfies the check."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, ("Bash", {"command": "pytest -q"})]).kind == "allow"


@case("TB09-D-029")
def test_d029_no_test_run_blocks(tmp_path):
    """PRD b5: an Edit with no later Bash call containing `checks.test` blocks."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT]).kind == "block"


@case("TB09-D-030")
def test_d030_test_run_before_last_edit_blocks(tmp_path):
    """PRD b5: the test run must come *after the last* Edit or Write; run-then-edit blocks."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, ("Bash", {"command": "pytest -q"}), WRITE]).kind == "block"


@case("TB09-D-031")
def test_d031_command_containing_test_check_counts(tmp_path):
    """PRD b5: the Bash call need only *contain* `checks.test` (`cd . && pytest -q`)."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, WRITE, ("Bash", {"command": "cd . && pytest -q"})]).kind == "allow"


@case("TB09-D-032")
def test_d032_other_bash_command_is_not_evidence(tmp_path):
    """PRD b5: a Bash call that does not contain `checks.test` (a lint run) is not evidence of a test run."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, ("Bash", {"command": "ruff check ."})]).kind == "block"


@case("TB09-D-033")
def test_d033_alt_profile_test_command(tmp_path):
    """PRD b5 reads `profile.checks.test`: under alt (`npm test`) an `npm test` run after the edit allows."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, ("Bash", {"command": "npm test"})], "alt").kind == "allow"


@case("TB09-D-034")
def test_d034_alt_profile_rejects_base_test_command(tmp_path):
    """PRD b5 with alt (`checks.test: npm test`): a `pytest -q` run does not contain `npm test`, so it blocks."""
    lib.need(HOOK, "decide")
    assert b5(tmp_path, [EDIT, ("Bash", {"command": "pytest -q"})], "alt").kind == "block"


@case("TB09-D-035")
def test_d035_checks_unset_skips_test_run_check(tmp_path):
    """PRD b5: 'if `checks.test` is not set, this check is skipped' - an Edit with no test run is allowed."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"src/calc.py": CLEAN_CALC})
    assert decide(root, stop_payload(root, tmp_path, tp=transcript(tmp_path, [EDIT]))).kind == "allow"


# ---------------------------------------------------------------- diagnostic: b1 events and roles

@pytest.mark.parametrize("role", [
    pytest.param(r, marks=case(f"TB09-D-{i:03d}"), id=r)
    for i, r in enumerate(["test", "orchestrator", "research", "design", "audit"], start=36)])
def test_d_other_roles_allowed(tmp_path, role):
    """PRD b1: the gate runs for implement; 'for every other role, allow' even when the tree has a skip marker."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"])})
    assert decide(root, stop_payload(root, tmp_path, agent_type=role)).kind == "allow"


@case("TB09-D-041")
def test_d041_stop_main_session_implement_blocks(tmp_path):
    """PRD b1: runs on Stop 'for the main session when its role is `implement`' (profile main_session_role)."""
    lib.need(HOOK, "decide")
    p = prof()
    p["main_session_role"] = "implement"
    root = repo(tmp_path, profile=p, changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"])})
    pl = lib.payload(root, event="Stop", last_assistant_message="Done.", stop_hook_active=False)
    assert decide(root, pl).kind == "block"


@case("TB09-D-042")
def test_d042_stop_main_session_orchestrator_allows(tmp_path):
    """PRD b1 + hook-io: with no `main_session_role` the main session is `orchestrator`, which this gate allows."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"])})
    pl = lib.payload(root, event="Stop", last_assistant_message="Done.", stop_hook_active=False)
    assert decide(root, pl).kind == "allow"


# ---------------------------------------------------------------- diagnostic: b7 iteration cap

def cap_repo(tmp_path):
    return repo(tmp_path, changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"])})


@case("TB09-D-043")
def test_d043_fifth_call_still_blocks(tmp_path):
    """PRD b7 boundary: 'blocks at most 5 times' - the 5th consecutive call still blocks."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    pl = stop_payload(root, tmp_path, agent_id="cap-5")
    assert [cli(root, pl) for _ in range(5)] == ["block"] * 5


@case("TB09-D-044")
def test_d044_after_cap_keeps_allowing(tmp_path):
    """PRD b7: 'after that it allows' - calls 6 and 7 both allow."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    pl = stop_payload(root, tmp_path, agent_id="cap-7")
    assert [cli(root, pl) for _ in range(7)][5:] == ["allow", "allow"]


@case("TB09-D-045")
def test_d045_cap_appends_log_line_with_reasons(tmp_path):
    """PRD b7: after the cap it 'appends a line to `.factory/stop_gate.log` naming the unresolved reasons'."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    pl = stop_payload(root, tmp_path, agent_id="cap-log")
    for _ in range(6):
        cli(root, pl)
    log = root / ".factory" / "stop_gate.log"
    assert log.is_file()
    text = log.read_text()
    assert text.strip() and "test_calc.py" in text


@case("TB09-D-046")
def test_d046_counter_file_location(tmp_path):
    """PRD b7: the count is 'kept in `.factory/state/stop_gate_<agent_id>`'."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    assert cli(root, stop_payload(root, tmp_path, agent_id="cnt-1")) == "block"
    assert (root / ".factory" / "state" / "stop_gate_cnt-1").exists()


@case("TB09-D-047")
def test_d047_cap_is_per_agent_id(tmp_path):
    """PRD b7: the cap is 'per `agent_id`': after agent a-1 exhausts its 5 blocks, agent a-2 is still blocked."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    pl1 = stop_payload(root, tmp_path, agent_id="a-1")
    for _ in range(6):
        cli(root, pl1)
    assert cli(root, stop_payload(root, tmp_path, agent_id="a-2")) == "block"


@case("TB09-D-048")
def test_d048_no_log_line_before_cap(tmp_path):
    """PRD b7: the log line is written 'after that' (once the cap is reached); a single block writes none."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    cli(root, stop_payload(root, tmp_path, agent_id="early"))
    log = root / ".factory" / "stop_gate.log"
    assert not log.exists() or not log.read_text().strip()


# ---------------------------------------------------------------- diagnostic: b8 reasons

@case("TB09-D-049")
def test_d049_reason_names_every_failing_file(tmp_path):
    """PRD b8: every failed check is listed with file names - skip markers in two different files both appear."""
    lib.need(HOOK, "decide")
    js = TEST_CALC_JS[: TEST_CALC_JS.rindex("});")] + JS_ADD["xit"] + "});\n"
    root = repo(tmp_path, committed={"tests/calc.test.js": TEST_CALC_JS},
                changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"]), "tests/calc.test.js": js})
    d = decide(root, stop_payload(root, tmp_path))
    assert d.kind == "block"
    assert "test_calc.py" in d.reason and "calc.test.js" in d.reason


@case("TB09-D-050")
def test_d050_reason_order_is_stable(tmp_path):
    """PRD b8: failed checks are listed 'in a stable order' - two evaluations of the same tree list the files in
    the same relative order."""
    lib.need(HOOK, "decide")
    root = repo(tmp_path, committed={"tests/frozen/test_contract.py": FROZEN,
                                     ".factory/baseline.json": json.dumps({"tests/frozen/test_contract.py": sha(FROZEN)}),
                                     ".factory/own.json": json.dumps({"paths": ["src/**", "tests/**"]})},
                changes={"tests/test_calc.py": with_test_fn(PY_ADD["xfail"]),
                         "tests/frozen/test_contract.py": FROZEN + "# x\n", "README.md": "edited\n"})
    names = ("test_calc.py", "test_contract.py", "README.md")
    orders = []
    for _ in range(2):
        r = decide(root, stop_payload(root, tmp_path)).reason
        assert all(n in r for n in names)
        orders.append(sorted(names, key=r.index))
    assert orders[0] == orders[1]


@case("TB09-D-051")
def test_d051_cli_block_output_shape(tmp_path):
    """hook-io adapter: a Stop/SubagentStop block is exit 0 with stdout {"decision":"block","reason":...}."""
    lib.need(HOOK, "decide")
    root = cap_repo(tmp_path)
    assert cli(root, stop_payload(root, tmp_path, agent_id="shape")) == "block"
