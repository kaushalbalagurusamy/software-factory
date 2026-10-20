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


def test_cli_pin_external_needs_yes(skills, tmp_path, capsys):
    root = tmp_path / "r"
    root.mkdir()
    args = ["pin-external", "--skills-dir", str(skills), "--factory-root", str(root)]
    assert main(args) == 2
    assert not (root / "docs/external-skills.json").exists()
    assert "external-skills.json" in capsys.readouterr().out
    assert main([*args, "--yes"]) == 0
    assert (root / "docs/external-skills.json").is_file()


def test_profile_allow_models_alone_does_not_widen(tmp_path, capsys):
    from factory.install import core
    proj = tmp_path / "p"
    (proj / ".factory").mkdir(parents=True)
    (proj / ".factory/profile.yaml").write_text(
        "schema_version: 1\nproject: {name: X}\npaths:\n  eval: [e/**]\nallow_models: [opus]\n")
    assert inst(proj) == 0
    assert "extra allowed models" not in capsys.readouterr().out
    assert inst(proj, "--allow-model", "opus") == 0
    assert "extra allowed models: opus" in capsys.readouterr().out
    assert core.MODEL == "sonnet"


def _bad_root(tmp_path, old="model: sonnet", new="model: opus", role="qa"):
    root = tmp_path / "root"
    shutil.copytree(REPO / "factory/agents/roles", root / "factory/agents/roles")
    p = root / f"factory/agents/roles/{role}.yaml"
    p.write_text(p.read_text().replace(old, new, 1))
    return root


def _args(root, skills, *allow, project=None):
    import argparse
    return argparse.Namespace(project=project, factory_root=str(root), python=sys.executable,
                              skills_dir=str(skills), json=False, allow_model=list(allow))


def test_doctor_non_sonnet_role_is_a_fail_line_not_a_traceback(skills, tmp_path, capsys):
    root = _bad_root(tmp_path)
    assert doctor.run_doctor(_args(root, skills)) == 1
    out = capsys.readouterr().out
    assert any(l.startswith("FAIL role qa model") and "opus" in l for l in out.splitlines())
    capsys.readouterr()
    doctor.run_doctor(_args(root, skills, "opus"))
    out = capsys.readouterr().out
    assert "FAIL role qa model" not in out and "extra allowed models: opus" in out


def test_doctor_project_checks_survive_a_non_sonnet_role(skills, tmp_path):
    root = _bad_root(tmp_path)
    proj = tmp_path / "p"
    proj.mkdir()
    assert inst(proj) == 0
    got = doctor.check_agents(proj, None, {"sonnet"}, root)
    assert len(got) == 8 and all(n.startswith("agent ") for n, _, _ in got)
    hooks = doctor.check_hooks(proj, {}, None, root, sys.executable)
    assert hooks and hooks[0][0] == "hooks registered"  # ran, did not raise


def test_doctor_invalid_role_file_is_fail_lines(skills, tmp_path):
    root = _bad_root(tmp_path, "max_tools: 20", "max_tools: 99", role="qa")
    proj = tmp_path / "p"
    proj.mkdir()
    assert doctor.check_agents(proj, None, {"sonnet"}, root)[0][1] == "FAIL"
    assert doctor.check_hooks(proj, {}, None, root, sys.executable)[0][1] == "FAIL"


def test_doctor_check_that_raises_becomes_fail_line():
    def boom():
        raise RuntimeError("x")
    assert doctor._safe("t", boom) == [("t", "FAIL", "check could not run: RuntimeError: x")]


def test_doctor_missing_role_file_does_not_raise(skills, tmp_path, capsys):
    root = _bad_root(tmp_path)
    (root / "factory/agents/roles/qa.yaml").unlink()
    assert doctor.run_doctor(_args(root, skills)) == 1
    assert "FAIL role qa file" in capsys.readouterr().out


def test_loader_check_model_false_skips_only_the_model_policy(tmp_path):
    from factory.agents.roles import RoleError, load_roles
    root = _bad_root(tmp_path)
    rdir = root / "factory/agents/roles"
    assert load_roles(rdir, check_model=False)["qa"].model == "opus"
    with pytest.raises(RoleError):
        load_roles(rdir)
    p = rdir / "qa.yaml"
    p.write_text(p.read_text().replace("max_tools: 20", "max_tools: 99"))
    with pytest.raises(RoleError):  # other validation stays
        load_roles(rdir, check_model=False)


def test_runtime_hooks_ignore_a_roles_model(tmp_path, monkeypatch):
    from factory.agents import roles as roles_mod
    from factory.hooks import blindness_guard, path_guard
    root = _bad_root(tmp_path, old="model: sonnet", new="model: opus", role="research")
    monkeypatch.setattr(roles_mod, "DEFAULT_DIR", root / "factory/agents/roles")
    path_guard._roles.cache_clear()
    assert path_guard._roles()["research"].model == "opus"
    for name in dir(blindness_guard):
        f = getattr(blindness_guard, name)
        if callable(f) and hasattr(f, "cache_clear") and name.startswith("_role"):
            f.cache_clear()
            assert f()["research"].model == "opus"
    path_guard._roles.cache_clear()


def test_doctor_hooks_run_with_non_sonnet_role_only_role_line_fails(skills, tmp_path, capsys):
    froot = tmp_path / "froot"
    shutil.copytree(REPO / "factory", froot / "factory", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "docs", froot / "docs", ignore=shutil.ignore_patterns("explorer", "native-verification"))
    shutil.copytree(REPO / "scripts", froot / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "skills", froot / "skills", ignore=shutil.ignore_patterns("_archive"))
    r = froot / "factory/agents/roles/research.yaml"
    r.write_text(r.read_text().replace("model: sonnet", "model: opus"))
    proj = tmp_path / "p"
    proj.mkdir()
    assert main(["install", "--project", str(proj), "--factory-root", str(froot), "--python", sys.executable,
                 "--allow-model", "opus"]) == 0
    capsys.readouterr()

    def run(*allow):
        doctor.run_doctor(_args(froot, skills, *allow, project=str(proj)))
        return [l for l in capsys.readouterr().out.splitlines() if l.startswith("FAIL") and ("opus" in l or l.startswith("FAIL hook"))]

    assert run("opus") == []
    fails = run()
    assert fails and all(l.startswith(("FAIL role research model", "FAIL agent research")) for l in fails)


def test_empty_skill_md_does_not_resolve(skills, tmp_path):
    (skills / "away-mode/SKILL.md").write_text("")
    (skills / "good-night/SKILL.md").write_text("  \n")
    assert doctor._skill_resolves("away-mode", REPO, skills) is None
    assert doctor._skill_resolves("good-night", REPO, skills) is None
    assert doctor._skill_resolves("minesweeper", REPO, skills)


@pytest.mark.parametrize("name", ["../skills/sf", "a/b", "..", "x:../y", "x:y/z", ""])
def test_skill_names_that_leave_their_directory_never_resolve(skills, name):
    assert doctor._skill_resolves(name, REPO, skills) is None


def test_disabled_plugin_skill_does_not_resolve(skills, tmp_path, monkeypatch):
    home = tmp_path / "home"
    ip = home / ".claude/plugins/cache/m/pl/1"
    (ip / "skills/s1").mkdir(parents=True)
    (ip / "skills/s1/SKILL.md").write_text("x")
    (home / ".claude/plugins/installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"pl@m": [{"installPath": str(ip)}]}}))
    monkeypatch.setenv("HOME", str(home))
    assert doctor._skill_resolves("pl:s1", REPO, skills)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"pl@m": True}}))
    assert doctor._skill_resolves("pl:s1", REPO, skills)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"pl@m": False}}))
    assert doctor._skill_resolves("pl:s1", REPO, skills) is None


def test_unhashable_model_is_a_fail_line(skills, tmp_path):
    root = _bad_root(tmp_path, new="model: [sonnet]")
    by = {n: s for n, s, _ in doctor.check_roles(root, skills, {"sonnet"})}
    assert by["role qa model"] == "FAIL" and by["role review model"] == "PASS"


def test_profile_model_override_is_policed(skills, tmp_path):
    proj = tmp_path / "p"
    (proj / ".factory").mkdir(parents=True)
    (proj / ".factory/profile.yaml").write_text(
        "schema_version: 1\nproject: {name: X}\npaths:\n  eval: [e/**]\nagents:\n  review: {model: opus}\n")
    assert inst(proj, "--allow-model", "opus") == 0
    for allowed, expect in (({"sonnet"}, "FAIL"), ({"sonnet", "opus"}, None)):
        out = doctor.check_project(proj, allowed, REPO, sys.executable, skills)[0]
        fails = [n for n, s, d in out if s == "FAIL" and n == "role review model"]
        assert bool(fails) == (expect == "FAIL")


def test_agent_file_missing_role_skills_fails(skills, tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    assert inst(proj) == 0
    f = proj / ".claude/agents/review.md"
    f.write_text(f.read_text().replace("- minesweeper\n", ""))
    out = {n: s for n, s, _ in doctor.check_agents(proj, None, {"sonnet"}, REPO, skills)}
    assert out["agent review skills"] == "FAIL"


def test_pin_external_changed_skill_needs_accept_changed(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    out = []
    assert pin_external(skills, root, True, out.append) == 0
    pinned = (root / "docs/external-skills.json").read_bytes()
    (skills / "minesweeper/SKILL.md").write_text("poisoned")
    out.clear()
    assert pin_external(skills, root, True, out.append) == 2
    assert (root / "docs/external-skills.json").read_bytes() == pinned
    assert any("changed since pinned: minesweeper" in o for o in out)
    assert any(o.startswith("---") or "minesweeper" in o and "sha256" in o for o in out)  # diff shown
    assert pin_external(skills, root, True, out.append, accept_changed=["away-mode"]) == 2
    assert pin_external(skills, root, False, out.append, accept_changed=["minesweeper"]) == 2
    assert (root / "docs/external-skills.json").read_bytes() == pinned
    assert pin_external(skills, root, True, out.append, accept_changed=["minesweeper"]) == 0
    assert (root / "docs/external-skills.json").read_bytes() != pinned


def test_pin_external_vanished_skill_needs_accept_changed(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    assert pin_external(skills, root, True, lambda *_: None) == 0
    shutil.rmtree(skills / "good-night")
    assert pin_external(skills, root, True, lambda *_: None) == 2
    assert pin_external(skills, root, True, lambda *_: None, accept_changed=["good-night"]) == 0


def test_cli_accept_changed_flag(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    base = ["pin-external", "--skills-dir", str(skills), "--factory-root", str(root)]
    assert main([*base, "--yes"]) == 0
    (skills / "away-mode/SKILL.md").write_text("changed")
    assert main([*base, "--yes"]) == 2
    assert main([*base, "--yes", "--accept-changed", "away-mode"]) == 0


def test_pin_external_message_names_both_flags(skills, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    out = []
    assert pin_external(skills, root, False, out.append) == 2
    assert any("--yes" in o for o in out)
    assert pin_external(skills, root, True, out.append) == 0
    (skills / "minesweeper/SKILL.md").write_text("changed")
    out.clear()
    assert pin_external(skills, root, False, out.append) == 2
    msg = [o for o in out if o.startswith("not written")][0]
    assert "--yes" in msg and "--accept-changed minesweeper" in msg
    out.clear()
    assert pin_external(skills, root, True, out.append) == 2
    msg = [o for o in out if o.startswith("not written")][0]
    assert "--yes" not in msg and "--accept-changed minesweeper" in msg
