"""SFN-02 unit coverage: eight agent files, role/skill and external-pin doctor checks, pin-external."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from factory.install import doctor
from factory.install.__main__ import main
from factory.install.core import EXTERNAL_SKILLS, pin_external

REPO = Path(__file__).resolve().parent.parent
ROLES = ("orchestrator", "research", "design", "audit", "implement", "qa", "test", "review")


def inst(proj, *extra):
    return main(["install", "--project", str(proj), "--factory-root", str(REPO),
                 "--python", sys.executable, *map(str, extra)])


def test_install_eight_agents_idempotent_and_uninstall(tmp_path, capsys):
    proj = tmp_path / "p"
    proj.mkdir()
    assert inst(proj) == 0
    assert sorted(p.stem for p in (proj / ".claude/agents").glob("*.md")) == sorted(ROLES)
    capsys.readouterr()
    assert inst(proj) == 0
    assert "unchanged" in capsys.readouterr().out
    assert main(["uninstall", "--project", str(proj)]) == 0
    assert not (proj / ".claude/agents").exists()


def test_profile_allow_models_flows_to_installer_only_when_role_needs_it(tmp_path):
    # shipped roles are all sonnet, so allow_models is accepted and changes nothing
    proj = tmp_path / "p"
    (proj / ".factory").mkdir(parents=True)
    (proj / ".factory/profile.yaml").write_text(
        "schema_version: 1\nproject: {name: X}\npaths:\n  eval: [e/**]\nallow_models: [opus]\n")
    assert inst(proj) == 0


@pytest.fixture
def skills(tmp_path):
    d = tmp_path / "skills"
    for n in EXTERNAL_SKILLS:
        (d / n).mkdir(parents=True)
        (d / n / "SKILL.md").write_text(f"---\nname: {n}\n---\nbody\n")
    return d


def test_check_roles_reports_per_skill_and_fails_unresolved(skills, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))  # no plugins: plugin skills cannot resolve
    out = doctor.check_roles(REPO, skills, {"sonnet"})
    by = {n: (s, d) for n, s, d in out}
    assert by["role review skill doc-sync"][0] == "PASS"
    assert by["role review skill minesweeper"][0] == "PASS"
    assert by["role implement skill claude-api"] == ("PASS", "built-in")
    s, d = by["role qa skill superpowers:verification-before-completion"]
    assert s == "FAIL" and "qa" in d
    assert by["role qa model"][0] == "PASS"


def test_check_roles_model_fail_from_factory_root(skills, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(REPO / "factory/agents/roles", root / "factory/agents/roles")
    p = root / "factory/agents/roles/qa.yaml"
    p.write_text(p.read_text().replace("model: sonnet", "model: opus"))
    by = {n: s for n, s, _ in doctor.check_roles(root, skills, {"sonnet"})}
    assert by["role qa model"] == "FAIL"
    by = {n: s for n, s, _ in doctor.check_roles(root, skills, {"sonnet", "opus"})}
    assert by["role qa model"] == "PASS"


def test_plugin_skill_resolves_via_registry(skills, tmp_path, monkeypatch):
    home = tmp_path / "home"
    inst_path = home / ".claude/plugins/cache/m/pl/1"
    (inst_path / "skills/s1").mkdir(parents=True)
    (inst_path / "skills/s1/SKILL.md").write_text("x")
    (home / ".claude/plugins/installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"pl@m": [{"installPath": str(inst_path)}]}}))
    monkeypatch.setenv("HOME", str(home))
    assert doctor._skill_resolves("pl:s1", REPO, skills)
    assert doctor._skill_resolves("pl:nope", REPO, skills) is None
    assert doctor._skill_resolves("other:s1", REPO, skills) is None


def _root_with_pins(tmp_path, skills):
    root = tmp_path / "froot"
    (root / "docs").mkdir(parents=True)
    pins = {n: {"sha256": hashlib.sha256((skills / n / "SKILL.md").read_bytes()).hexdigest()} for n in EXTERNAL_SKILLS}
    (root / "docs/external-skills.json").write_text(json.dumps({"schema": 1, "skills": pins}))
    return root


def test_external_pass_changed_warn_missing_fail(skills, tmp_path):
    root = _root_with_pins(tmp_path, skills)
    assert {s for _, s, _ in doctor.check_external(root, skills)} == {"PASS"}
    (skills / "minesweeper/SKILL.md").write_text("edited")
    shutil.rmtree(skills / "good-night")
    by = {n: (s, d) for n, s, d in doctor.check_external(root, skills)}
    assert by["external minesweeper"][0] == "WARN" and "changed since pinned" in by["external minesweeper"][1]
    assert by["external good-night"][0] == "FAIL"


def test_external_pin_file_missing_or_corrupt_fails(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    assert doctor.check_external(root, skills)[0][1] == "FAIL"
    (root / "docs").mkdir()
    (root / "docs/external-skills.json").write_text("{not json")
    assert doctor.check_external(root, skills)[0][1] == "FAIL"


def test_pin_external_requires_yes_then_writes(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    out = []
    assert pin_external(skills, root, False, out.append) == 2
    assert not (root / "docs/external-skills.json").exists()
    assert pin_external(skills, root, True, out.append) == 0
    data = json.loads((root / "docs/external-skills.json").read_text())
    assert data["schema"] == 1 and set(data["skills"]) == set(EXTERNAL_SKILLS)
    assert data["skills"]["away-mode"]["sha256"] == hashlib.sha256((skills / "away-mode/SKILL.md").read_bytes()).hexdigest()
    assert doctor.check_external(root, skills) and {s for _, s, _ in doctor.check_external(root, skills)} == {"PASS"}


def test_pin_external_reports_skill_without_skill_md(skills, tmp_path):
    (skills / "away-mode/SKILL.md").unlink()
    root = tmp_path / "r"
    root.mkdir()
    out = []
    pin_external(skills, root, True, out.append)
    assert any("not pinned: away-mode" in o for o in out)
    assert "away-mode" not in json.loads((root / "docs/external-skills.json").read_text())["skills"]
    assert dict((n, s) for n, s, _ in doctor.check_external(root, skills))["external away-mode"] == "FAIL"
