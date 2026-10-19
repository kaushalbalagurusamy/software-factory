"""Unit tests for the stop gate (TB-09). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import stop_gate
from factory.hooks.core import HookConfig, parse_payload, run_hook

GOOD_TEST = "def test_a():\n    assert 1 + 1 == 2\n"


def sh(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


def make_cfg(root: Path, **extra) -> HookConfig:
    paths = {"eval": ["evals/**"]}
    paths.update(extra.pop("paths", {}))
    data = {"schema_version": 1, "project": {"name": "demo"}, "paths": paths}
    data.update(extra)
    return HookConfig.from_profile(parse_profile(data), root)


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    sh(root, "init", "-q")
    write(root, "src/app.py", "x = 1\n")
    write(root, "tests/test_a.py", GOOD_TEST)
    write(root, "tests/test_b.py", GOOD_TEST.replace("test_a", "test_b"))
    write(root, ".gitignore", ".factory/\n")
    sh(root, "add", ".")
    sh(root, "commit", "-q", "-m", "init")
    return root


def payload(root: Path, event="SubagentStop", agent_type="implement", agent_id="a1", **extra) -> str:
    d = {"session_id": "s", "cwd": str(root), "hook_event_name": event, "permission_mode": "default"}
    if agent_type:
        d["agent_type"] = agent_type
    if agent_id:
        d["agent_id"] = agent_id
    d.update(extra)
    return json.dumps(d)


def decide(root, cfg, **kw):
    return stop_gate.decide(parse_payload(payload(root, **kw)), cfg)


def transcript(root: Path, calls: list[tuple[str, dict]]) -> str:
    lines = []
    for i, (name, inp) in enumerate(calls):
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}))
    p = root.parent / "transcript.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return str(p)


# ---- role and event gating ----------------------------------------------------------------------
@pytest.mark.parametrize("role", ["test", "review", "research", "design", "audit", "orchestrator"])
def test_other_roles_allowed_even_with_bad_changes(repo, role):
    write(repo, "tests/test_c.py", "import pytest\n@pytest.mark.skip\ndef test_c(): pass\n")
    assert decide(repo, make_cfg(repo), agent_type=role).kind == "allow"


def test_main_session_stop_uses_main_session_role(repo):
    write(repo, "tests/test_c.py", "import pytest\n@pytest.mark.skip\ndef test_c(): pass\n")
    assert decide(repo, make_cfg(repo), event="Stop", agent_type=None, agent_id=None).kind == "allow"
    cfg = make_cfg(repo, main_session_role="implement")
    d = decide(repo, cfg, event="Stop", agent_type=None, agent_id=None)
    assert d.kind == "block" and "tests/test_c.py" in d.reason


def test_clean_implement_stop_allowed(repo):
    write(repo, "src/app.py", "x = 2\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


# ---- check 3: markers ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "import pytest\n@pytest.mark.skip\ndef test_c(): pass\n",
    "import pytest\n@pytest.mark.skip(reason='x')\ndef test_c(): pass\n",
    "import pytest\n@pytest.mark.skipif(True, reason='x')\ndef test_c(): pass\n",
    "import pytest\n@pytest.mark.xfail\ndef test_c(): assert 0\n",
    "import pytest\ndef test_c():\n    pytest.skip('no')\n",
    "import unittest\nclass T(unittest.TestCase):\n    @unittest.skip('x')\n    def test_c(self): pass\n",
])
def test_python_skip_markers_block(repo, text):
    write(repo, "tests/test_c.py", text)
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "tests/test_c.py" in d.reason and "skip" in d.reason


@pytest.mark.parametrize("text", [
    "it.skip('x', () => {})\n", "test.skip('x', () => {})\n", "xit('x', () => {})\n",
    "xdescribe('x', () => {})\n",
])
def test_js_skip_markers_block(repo, text):
    write(repo, "web/a.test.js", text)
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "web/a.test.js" in d.reason


def test_marker_in_modified_tracked_test_blocks(repo):
    write(repo, "tests/test_a.py", GOOD_TEST + "\n@pytest.mark.xfail\ndef test_z(): assert 0\n")
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "xfail" in d.reason


def test_marker_outside_test_files_ignored(repo):
    write(repo, "src/helper.py", "import pytest\npytest.skip('x')\nxit = 1\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


def test_sys_exit_does_not_match_xit(repo):
    write(repo, "tests/test_c.py", "import sys\ndef test_c():\n    assert sys.exit is not None\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


@pytest.mark.parametrize("text", [
    "def test_c():\n    assert True\n",
    "def test_c():\n    assert 1\n",
    "def test_c():\n    assert True, 'msg'\n",
    "def test_c(self):\n    self.assertTrue(True)\n",
    "it('x', () => { expect(true).toBe(true) })\n",
])
def test_trivial_assertions_block(repo, text):
    write(repo, "tests/test_c.py" if "def " in text else "web/x.spec.ts", text)
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "trivial assertion" in d.reason


def test_assert_one_equals_not_trivial(repo):
    write(repo, "tests/test_c.py", "def f(): return 1\ndef test_c():\n    assert 1 == f()\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


def test_removed_lines_with_markers_are_not_added(repo):
    write(repo, "tests/test_a.py", GOOD_TEST + "@pytest.mark.skip\ndef test_q(): pass\n")
    sh(repo, "add", "tests/test_a.py")
    sh(repo, "commit", "-q", "-m", "skip exists already")
    write(repo, "tests/test_a.py", GOOD_TEST + "def test_q(): pass\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


# ---- removals -----------------------------------------------------------------------------------
def test_deleted_test_file_blocks(repo):
    (repo / "tests/test_b.py").unlink()
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "tests/test_b.py" in d.reason and "removed" in d.reason


def test_deleted_staged_test_file_blocks(repo):
    sh(repo, "rm", "-q", "tests/test_b.py")
    assert decide(repo, make_cfg(repo)).kind == "block"


def test_deleted_test_function_blocks(repo):
    write(repo, "tests/test_a.py", "# gone\n")
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "test_a" in d.reason and "tests/test_a.py" in d.reason


def test_renamed_test_function_is_not_removal(repo):
    write(repo, "tests/test_a.py", "def test_a():\n    assert 2 == 2\n")
    assert decide(repo, make_cfg(repo)).kind == "allow"


def test_deleted_non_test_file_allowed(repo):
    (repo / "src/app.py").unlink()
    assert decide(repo, make_cfg(repo)).kind == "allow"


# ---- check 4: frozen files ----------------------------------------------------------------------
def freeze(repo: Path, manifest: dict | None = None) -> HookConfig:
    if manifest is None:
        manifest = {rel: hashlib.sha256((repo / rel).read_bytes()).hexdigest()
                    for rel in ("tests/test_a.py", "tests/test_b.py")}
    write(repo, ".factory/baseline.json", json.dumps(manifest))
    return make_cfg(repo, paths={"frozen_tests": ["tests/**"]})


def test_frozen_unchanged_allowed(repo):
    assert decide(repo, freeze(repo)).kind == "allow"


def test_frozen_changed_hash_blocks(repo):
    cfg = freeze(repo)
    write(repo, "tests/test_b.py", GOOD_TEST.replace("test_a", "test_b") + "# edit\n")
    d = decide(repo, cfg)
    assert d.kind == "block" and "tests/test_b.py" in d.reason and "frozen" in d.reason
    assert "tests/test_a.py" not in d.reason


def test_frozen_missing_from_manifest_blocks(repo):
    cfg = freeze(repo, {"tests/test_a.py": hashlib.sha256(GOOD_TEST.encode()).hexdigest()})
    d = decide(repo, cfg)
    assert d.kind == "block" and "tests/test_b.py" in d.reason and "baseline.json" in d.reason


def test_frozen_missing_on_disk_blocks(repo):
    cfg = freeze(repo)
    (repo / "tests/test_b.py").unlink()
    d = decide(repo, cfg)
    assert d.kind == "block" and "missing on disk" in d.reason


def test_frozen_without_baseline_blocks(repo):
    d = decide(repo, make_cfg(repo, paths={"frozen_tests": ["tests/**"]}))
    assert d.kind == "block" and "baseline.json" in d.reason


@pytest.mark.parametrize("bad", ["not json", "[1]", '{"a": 1}'])
def test_frozen_malformed_baseline_blocks(repo, bad):
    write(repo, ".factory/baseline.json", bad)
    assert decide(repo, make_cfg(repo, paths={"frozen_tests": ["tests/**"]})).kind == "block"


def test_no_frozen_globs_skips_hash_check(repo):
    assert decide(repo, make_cfg(repo)).kind == "allow"


# ---- check 5: evidence of a full-suite run ------------------------------------------------------
TEST_CMD = "pytest -q tests"


def checks_cfg(repo):
    return make_cfg(repo, checks={"test": TEST_CMD})


def test_missing_test_run_after_edit_blocks(repo):
    t = transcript(repo, [("Write", {"file_path": "a"}), ("Bash", {"command": "ls"})])
    d = decide(repo, checks_cfg(repo), agent_transcript_path=t)
    assert d.kind == "block" and "checks.test" in d.reason


def test_test_run_before_last_edit_blocks(repo):
    t = transcript(repo, [("Bash", {"command": TEST_CMD}), ("Edit", {"file_path": "a"})])
    assert decide(repo, checks_cfg(repo), agent_transcript_path=t).kind == "block"


def test_test_run_after_edit_allows_by_containment(repo):
    t = transcript(repo, [("Edit", {"file_path": "a"}), ("Bash", {"command": f"cd x && {TEST_CMD} tests/test_a.py"})])
    assert decide(repo, checks_cfg(repo), agent_transcript_path=t).kind == "allow"


def test_no_edit_in_transcript_passes(repo):
    t = transcript(repo, [("Read", {"file_path": "a"})])
    assert decide(repo, checks_cfg(repo), agent_transcript_path=t).kind == "allow"


def test_checks_test_unset_skips_and_logs_nothing(repo):
    t = transcript(repo, [("Write", {"file_path": "a"})])
    assert decide(repo, make_cfg(repo), agent_transcript_path=t).kind == "allow"
    assert decide(repo, make_cfg(repo), agent_transcript_path="/nonexistent").kind == "allow"
    assert not (repo / ".factory/stop_gate.log").exists()


@pytest.mark.parametrize("content", [None, "", "not json\n"])
def test_unreadable_transcript_skips_check_and_logs(repo, content):
    p = repo.parent / "bad.jsonl"
    if content is not None:
        p.write_text(content)
    assert decide(repo, checks_cfg(repo), agent_transcript_path=str(p)).kind == "allow"
    assert (repo / ".factory/stop_gate.log").read_text().count("\n") == 1


def test_stop_event_uses_transcript_path(repo):
    t = transcript(repo, [("Write", {"file_path": "a"})])
    cfg = make_cfg(repo, main_session_role="implement", checks={"test": TEST_CMD})
    d = decide(repo, cfg, event="Stop", agent_type=None, agent_id=None, transcript_path=t)
    assert d.kind == "block" and "checks.test" in d.reason
    d = decide(repo, cfg, event="Stop", agent_type=None, agent_id=None)
    assert d.kind == "allow"


# ---- check 6: ownership -------------------------------------------------------------------------
def test_own_paths_outside_blocks(repo):
    write(repo, ".factory/own.json", json.dumps({"paths": ["src/**"]}))
    write(repo, "src/app.py", "x = 3\n")
    write(repo, "docs/new.md", "hi\n")
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "docs/new.md" in d.reason and "src/app.py" not in d.reason


def test_own_paths_inside_allowed(repo):
    write(repo, ".factory/own.json", json.dumps({"paths": ["src/**", "tests/*.py"]}))
    write(repo, "src/deep/new.py", "x = 3\n")
    write(repo, "tests/test_n.py", GOOD_TEST.replace("test_a", "test_n"))
    assert decide(repo, make_cfg(repo)).kind == "allow"


def test_own_invalid_blocks(repo):
    write(repo, ".factory/own.json", "{bad")
    assert decide(repo, make_cfg(repo)).kind == "block"


def test_own_gate_state_files_not_counted(repo):
    write(repo, ".factory/own.json", json.dumps({"paths": ["src/**"]}))
    (repo / ".gitignore").write_text("")  # state files become visible to git
    sh(repo, "add", ".gitignore")
    sh(repo, "commit", "-q", "-m", "ungitignore")
    write(repo, "src/x.py", "x\n")
    write(repo, "docs/new.md", "hi\n")
    cfg = make_cfg(repo)
    assert decide(repo, cfg).kind == "block"
    d = decide(repo, cfg)
    assert d.kind == "block" and ".factory/state" not in d.reason and "stop_gate.log" not in d.reason


# ---- git unavailable ----------------------------------------------------------------------------
def test_not_a_repository_blocks(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    d = decide(root, make_cfg(root))
    assert d.kind == "block" and "git" in d.reason


def test_no_head_commit_blocks(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    sh(root, "init", "-q")
    d = decide(root, make_cfg(root))
    assert d.kind == "block" and "git" in d.reason


def test_no_git_executable_blocks(repo, monkeypatch):
    monkeypatch.setenv("PATH", str(repo.parent / "nowhere"))
    d = decide(repo, make_cfg(repo))
    assert d.kind == "block" and "git" in d.reason


# ---- reasons: every failed check, stable order --------------------------------------------------
def test_reason_lists_every_failure_in_stable_order(repo):
    freeze(repo)
    cfg = make_cfg(repo, paths={"frozen_tests": ["tests/**"]}, checks={"test": TEST_CMD})
    write(repo, "tests/test_a.py", "import pytest\n@pytest.mark.skip\ndef test_a():\n    assert True\n")
    (repo / "tests/test_b.py").unlink()
    write(repo, ".factory/own.json", json.dumps({"paths": ["src/**"]}))
    t = transcript(repo, [("Edit", {"file_path": "a"})])
    d = decide(repo, cfg, agent_transcript_path=t)
    assert d.kind == "block"
    order = ["skip or expected-failure marker", "trivial assertion", "test removed",
             "frozen test changed", "frozen test missing on disk", "no full-suite run",
             "change outside"]
    positions = [d.reason.index(s) for s in order]
    assert positions == sorted(positions)
    again = decide(repo, cfg, agent_transcript_path=t, agent_id="a2")
    assert again.reason.split("\n", 1)[1] == d.reason.split("\n", 1)[1]


def test_files_listed_in_sorted_order(repo):
    write(repo, "tests/test_z.py", "import pytest\n@pytest.mark.skip\ndef test_z(): pass\n")
    write(repo, "tests/test_m.py", "import pytest\n@pytest.mark.skip\ndef test_m(): pass\n")
    r = decide(repo, make_cfg(repo)).reason
    assert r.index("test_m.py") < r.index("test_z.py")


# ---- iteration cap ------------------------------------------------------------------------------
def bad(repo):
    write(repo, "tests/test_c.py", "def test_c():\n    assert True\n")


def test_cap_blocks_five_times_then_allows_and_logs(repo):
    cfg = make_cfg(repo)
    bad(repo)
    for n in range(1, 6):
        assert decide(repo, cfg).kind == "block"
        assert (repo / ".factory/state/stop_gate_a1").read_text().strip() == str(n)
    assert decide(repo, cfg).kind == "allow"
    log = (repo / ".factory/stop_gate.log").read_text().splitlines()
    assert len(log) == 1 and "trivial assertion" in log[0] and "tests/test_c.py" in log[0] and "a1" in log[0]
    assert decide(repo, cfg).kind == "allow"
    assert len((repo / ".factory/stop_gate.log").read_text().splitlines()) == 2


def test_cap_is_per_agent(repo):
    cfg = make_cfg(repo)
    bad(repo)
    for _ in range(5):
        decide(repo, cfg)
    assert decide(repo, cfg).kind == "allow"
    assert decide(repo, cfg, agent_id="other").kind == "block"


def test_clean_stop_resets_counter(repo):
    cfg = make_cfg(repo)
    bad(repo)
    for _ in range(3):
        decide(repo, cfg)
    (repo / "tests/test_c.py").unlink()
    assert decide(repo, cfg).kind == "allow"
    assert not (repo / ".factory/state/stop_gate_a1").exists()
    bad(repo)
    for _ in range(5):
        assert decide(repo, cfg).kind == "block"


def test_other_roles_do_not_touch_counter(repo):
    bad(repo)
    decide(repo, make_cfg(repo), agent_type="test")
    assert not (repo / ".factory/state").exists()


def test_agent_id_sanitised_for_filename(repo):
    bad(repo)
    decide(repo, make_cfg(repo), agent_id="../../evil")
    assert not (repo.parent / "evil").exists()
    assert list((repo / ".factory/state").iterdir())[0].name.startswith("stop_gate_")


# ---- protocol -----------------------------------------------------------------------------------
def test_run_hook_block_json_and_allow(repo):
    cfg = make_cfg(repo)
    assert run_hook(stop_gate.decide, payload(repo), cfg).stdout == ""
    bad(repo)
    r = run_hook(stop_gate.decide, payload(repo), cfg)
    assert r.exit_code == 0 and json.loads(r.stdout)["decision"] == "block"


def test_malformed_input_fails_closed(repo):
    r = run_hook(stop_gate.decide, "{nope", make_cfg(repo))
    assert r.exit_code == 2 and r.stderr.startswith("hook error:")


def test_non_stop_events_allowed(repo):
    bad(repo)
    p = parse_payload(payload(repo, event="PreToolUse", tool_name="Bash", tool_input={"command": "ls"}))
    assert stop_gate.decide(p, make_cfg(repo)).kind == "allow"


def test_registry_resolves_module():
    from factory.hooks import registry
    h = registry.get_hook("stop_gate")
    assert h.implemented and h.decide is stop_gate.decide


# ---- helpers ------------------------------------------------------------------------------------
@pytest.mark.parametrize("rel,expected", [
    ("tests/a.py", True), ("test/a.py", True), ("web/__tests__/a.js", True), ("src/test_x.py", True),
    ("src/x_test.py", True), ("a.test.ts", True), ("a.spec.js", True), ("src/app.py", False),
    ("src/testing.py", False),
])
def test_is_test_file(rel, expected):
    assert stop_gate.is_test_file(rel) is expected


def test_glob_semantics():
    rx = stop_gate.glob_to_regex("tests/**/*.py")
    assert rx.match("tests/a.py") and rx.match("tests/x/y/a.py") and not rx.match("tests/a.txt")
    assert not stop_gate.glob_to_regex("src/*.py").match("src/x/a.py")
