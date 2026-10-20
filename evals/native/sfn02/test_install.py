"""SFN-02 acceptance: eight-agent idempotent install (A-08) and non-regression guards (A-09)."""
from __future__ import annotations

import json
import subprocess
import sys

from .conftest import REPO, ROLES8, lines


def test_A08_install_generates_eight_agent_files_and_manifest(rig):
    r = rig.install()
    assert r.returncode == 0, r.stderr
    assert [p.stem for p in rig.agents()] == sorted(ROLES8)
    man = json.loads((rig.proj / ".factory/install-manifest.json").read_text())
    tracked = {i["path"] for i in man["items"]}
    assert {f".claude/agents/{r}.md" for r in ROLES8} <= tracked
    assert set(man["agent_models"]) == set(ROLES8)
    assert {v["pinned"] for v in man["agent_models"].values()} == {"sonnet"}


def test_A08_every_installed_agent_is_sonnet(rig):
    rig.install()
    assert {rig.agent_fm(r)["model"] for r in ROLES8} == {"sonnet"}


def test_A08_second_install_reports_unchanged_and_changes_nothing(rig):
    rig.install()
    snap = {str(p.relative_to(rig.proj)): p.read_bytes() for p in rig.proj.rglob("*") if p.is_file()}
    r = rig.install()
    assert r.returncode == 0 and "unchanged" in r.stdout
    assert {str(p.relative_to(rig.proj)): p.read_bytes() for p in rig.proj.rglob("*") if p.is_file()} == snap


def test_A08_uninstall_removes_the_eight_agent_files(rig):
    rig.install()
    assert len(rig.agents()) == 8
    r = rig.uninstall()
    assert r.returncode == 0, r.stderr
    assert rig.agents() == []
    for role in ROLES8:
        assert not (rig.proj / f".claude/agents/{role}.md").exists()


def test_A08_install_over_a_seven_agent_project_adds_qa_without_losing_others(rig):
    rig.install()
    (rig.proj / ".claude/agents/qa.md").unlink()
    r = rig.install()
    assert r.returncode == 0 and (rig.proj / ".claude/agents/qa.md").is_file()
    assert len(rig.agents()) == 8


def test_A08_dry_run_writes_nothing(rig):
    r = rig.install("--dry-run")
    assert r.returncode == 0 and rig.agents() == []


def test_A08_pin_external_is_a_real_subcommand_and_bad_flags_exit_2(rig):
    assert rig.run("pin-external", "--help").returncode == 0
    assert rig.run("pin-external", "--bogus-flag").returncode == 2


# ---- A-09: the existing suites must still run; the conflicting pins are reported, not edited.
def test_A09_existing_unit_suite_for_roles_graph_and_install_is_collectable():
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/agents", "tests/test_install.py"],
                       cwd=REPO, capture_output=True, text=True, timeout=18)
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]


def test_A09_doctor_baseline_lines_keep_their_shape(ready):
    r = ready.doctor()
    for needle in ("PASS model pin", "PASS env pin", "PASS profile", "PASS hook bash_guard deny", "PASS sf command"):
        assert any(l.startswith(needle) for l in lines(r)), needle
    assert r.returncode == 0, "\n".join(lines(r))
