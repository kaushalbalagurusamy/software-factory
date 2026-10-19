"""Native installer: install/uninstall/doctor against a throwaway project directory."""
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

from factory.install.__main__ import main

REPO = Path(__file__).resolve().parent.parent
ROLES_WITH_OPUS = ("orchestrator", "design", "review", "test")
ROLE_IDS = ("orchestrator", "research", "design", "audit", "implement", "test", "review")


def inst(proj, *extra, expect=0):
    rc = main(["install", "--project", str(proj), "--factory-root", str(REPO),
               "--python", sys.executable, *map(str, extra)])
    assert rc == expect
    return rc


def snapshot(proj):
    return {str(p.relative_to(proj)): p.read_bytes() for p in sorted(proj.rglob("*")) if p.is_file()}


def settings(proj):
    return json.loads((proj / ".claude/settings.json").read_text())


def agent_model(proj, role):
    text = (proj / f".claude/agents/{role}.md").read_text()
    return yaml.safe_load(text.split("---")[1])["model"]


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


USER = {
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(./.env)"]},
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/mine/check.sh"}]}]},
    "theme": "dark",
}


def test_fresh_install_writes_everything(proj, capsys):
    inst(proj)
    out = capsys.readouterr().out
    assert "profile: created" in out
    for r in ROLE_IDS:
        assert (proj / f".claude/agents/{r}.md").is_file()
    assert (proj / ".factory/profile.yaml").is_file()
    man = json.loads((proj / ".factory/install-manifest.json").read_text())
    assert man["model_pin"] == "sonnet" and man["python"] == sys.executable
    paths = {i["path"]: i for i in man["items"]}
    assert paths[".factory/profile.yaml"]["origin"] == "created"
    for i in man["items"]:
        assert i["sha256"] == hashlib.sha256((proj / i["path"]).read_bytes()).hexdigest()


def test_idempotent_second_run_changes_nothing(proj, capsys):
    (proj / ".claude").mkdir()
    (proj / ".claude/settings.json").write_text(json.dumps(USER))
    inst(proj)
    before = snapshot(proj)
    capsys.readouterr()
    inst(proj)
    assert "unchanged" in capsys.readouterr().out
    assert snapshot(proj) == before
    assert len(list((proj / ".claude/backups").iterdir())) == 1  # exactly one backup, from run 1


def test_user_settings_preserved_and_permissions_untouched(proj):
    (proj / ".claude").mkdir()
    orig = json.dumps(USER, indent=1)
    (proj / ".claude/settings.json").write_text(orig)
    inst(proj)
    s = settings(proj)
    assert s["permissions"] == USER["permissions"]
    assert s["theme"] == "dark"
    assert USER["hooks"]["PreToolUse"][0] in s["hooks"]["PreToolUse"]
    (b,) = list((proj / ".claude/backups").rglob("settings.json"))
    assert b.read_text() == orig


def test_no_permissions_key_added(proj):
    inst(proj)
    assert "permissions" not in settings(proj)


def test_model_pin_env_and_agent_models(proj):
    inst(proj)
    s = settings(proj)
    assert s["model"] == "sonnet"
    assert s["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert s["env"]["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] == "1"
    for r in ROLE_IDS:
        assert agent_model(proj, r) == "sonnet"


def test_roles_really_propose_opus():
    from factory.agents.roles import load_roles
    assert {r for r, s in load_roles().items() if s.model == "opus"} == set(ROLES_WITH_OPUS)


def test_allow_model_widens_explicitly(proj):
    inst(proj, "--allow-model", "opus")
    assert agent_model(proj, "orchestrator") == "opus"
    assert agent_model(proj, "implement") == "sonnet"
    assert settings(proj)["model"] == "sonnet"


def test_existing_env_merged(proj):
    (proj / ".claude").mkdir()
    (proj / ".claude/settings.json").write_text(json.dumps({"env": {"FOO": "1"}, "model": "opus"}))
    inst(proj)
    s = settings(proj)
    assert s["env"]["FOO"] == "1" and s["model"] == "sonnet"


def test_hook_commands_absolute_and_prefix_only(proj):
    inst(proj)
    cmds = [h["command"] for ev in settings(proj)["hooks"].values() for e in ev for h in e["hooks"]]
    assert cmds
    for c in cmds:
        assert c.startswith(f"PYTHONPATH={REPO} {sys.executable} -m factory.hooks ")
    # frontmatter hooks in agent files carry the same absolute commands
    assert str(REPO) in (proj / ".claude/agents/implement.md").read_text()


def test_reinstall_does_not_duplicate_hooks(proj):
    inst(proj)
    n = sum(len(e) for e in settings(proj)["hooks"].values())
    inst(proj, "--python", sys.executable)
    assert sum(len(e) for e in settings(proj)["hooks"].values()) == n


def test_unresolvable_python_fails_and_writes_nothing(proj, capsys):
    rc = main(["install", "--project", str(proj), "--factory-root", str(REPO), "--python", "/nonexistent/py"])
    assert rc != 0 and snapshot(proj) == {}
    assert "/nonexistent/py" in capsys.readouterr().err


def test_python_without_z3_fails(proj, tmp_path, capsys):
    fake = tmp_path / "py"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    rc = main(["install", "--project", str(proj), "--factory-root", str(REPO), "--python", str(fake)])
    assert rc != 0 and snapshot(proj) == {}


def test_missing_project_fails(tmp_path):
    assert main(["install", "--project", str(tmp_path / "nope"), "--factory-root", str(REPO),
                 "--python", sys.executable]) != 0


def test_existing_profile_never_modified(proj):
    (proj / ".factory").mkdir()
    prof = "schema_version: 1\nproject: {name: Mine}\npaths:\n  eval: [qa/**]\n"
    (proj / ".factory/profile.yaml").write_text(prof)
    inst(proj)
    assert (proj / ".factory/profile.yaml").read_text() == prof
    man = json.loads((proj / ".factory/install-manifest.json").read_text())
    assert {i["path"]: i["origin"] for i in man["items"]}[".factory/profile.yaml"] == "existing"


def test_invalid_existing_profile_fails_untouched(proj):
    (proj / ".factory").mkdir()
    (proj / ".factory/profile.yaml").write_text("schema_version: 9\n")
    inst(proj, expect=1)
    assert not (proj / ".claude").exists()


def test_profile_option_copied(proj, tmp_path):
    src = tmp_path / "p.yaml"
    src.write_text("schema_version: 1\nproject: {name: Copied}\npaths:\n  eval: [x/**]\n")
    inst(proj, "--profile", src)
    assert (proj / ".factory/profile.yaml").read_text() == src.read_text()


def test_malformed_existing_settings_refused(proj):
    (proj / ".claude").mkdir()
    (proj / ".claude/settings.json").write_text("{not json")
    inst(proj, expect=1)
    assert (proj / ".claude/settings.json").read_text() == "{not json"


def test_changed_agent_file_backed_up_then_overwritten(proj):
    inst(proj)
    a = proj / ".claude/agents/review.md"
    a.write_text("hand edited")
    inst(proj)
    assert a.read_text() != "hand edited"
    assert any(p.read_text() == "hand edited" for p in (proj / ".claude/backups").rglob("review.md"))


def test_dry_run_writes_nothing_and_prints_diff(proj, capsys):
    (proj / ".claude").mkdir()
    (proj / ".claude/settings.json").write_text(json.dumps(USER))
    before = snapshot(proj)
    inst(proj, "--dry-run")
    out = capsys.readouterr().out
    assert snapshot(proj) == before
    assert "--- " in out and '+  "model": "sonnet"' in out


def test_no_hooks_and_no_agents(proj):
    inst(proj, "--no-hooks", "--no-agents")
    assert "hooks" not in settings(proj) and not (proj / ".claude/agents").exists()
    assert settings(proj)["model"] == "sonnet"


def test_no_git_commands_run(proj):
    inst(proj)
    assert not (proj / ".git").exists()


# ---- uninstall

def test_uninstall_restores_original(proj):
    (proj / ".claude").mkdir()
    orig = json.dumps(USER)
    (proj / ".claude/settings.json").write_text(orig)
    (proj / "keep.txt").write_text("unrelated")
    inst(proj)
    assert main(["uninstall", "--project", str(proj)]) == 0
    assert (proj / ".claude/settings.json").read_text() == orig
    assert not (proj / ".claude/agents").exists()
    assert not (proj / ".factory").exists()
    assert (proj / "keep.txt").read_text() == "unrelated"


def test_uninstall_refuses_modified_file(proj, capsys):
    inst(proj)
    a = proj / ".claude/agents/test.md"
    a.write_text("mine now")
    capsys.readouterr()
    assert main(["uninstall", "--project", str(proj)]) == 1
    assert a.read_text() == "mine now"
    assert "test.md" in capsys.readouterr().err
    assert not (proj / ".claude/agents/implement.md").exists()
    assert (proj / ".factory/install-manifest.json").exists()  # kept so a retry is possible


def test_uninstall_without_manifest_fails(proj):
    assert main(["uninstall", "--project", str(proj)]) != 0


def test_uninstall_leaves_existing_profile(proj):
    (proj / ".factory").mkdir()
    prof = "schema_version: 1\nproject: {name: Mine}\npaths:\n  eval: [qa/**]\n"
    (proj / ".factory/profile.yaml").write_text(prof)
    inst(proj)
    assert main(["uninstall", "--project", str(proj)]) == 0
    assert (proj / ".factory/profile.yaml").read_text() == prof


# ---- doctor

@pytest.fixture
def env(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    for d in (REPO / "skills").iterdir():
        if d.is_dir() and (d / "SKILL.md").is_file() and not d.name.startswith("_"):
            (skills / d.name).symlink_to(d)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sf = bindir / "sf"
    sf.write_text(f"#!/bin/sh\nexec {sys.executable} -m factory.cli \"$@\"\n")
    sf.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    return skills


def doc(proj, skills, *extra):
    return main(["doctor", "--project", str(proj), "--skills-dir", str(skills), "--factory-root", str(REPO),
                 "--python", sys.executable, *map(str, extra)])


def lines(capsys):
    return capsys.readouterr().out.splitlines()


def test_doctor_all_pass(proj, env, capsys):
    inst(proj)
    capsys.readouterr()
    assert doc(proj, env) == 0
    out = lines(capsys)
    assert all(l.startswith(("PASS", "SKIP")) for l in out), out
    joined = "\n".join(out)
    assert "hook bash_guard deny" in joined and joined.count("PASS skill ") == 13


def test_doctor_json(proj, env, capsys):
    inst(proj)
    capsys.readouterr()
    assert doc(proj, env, "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert all(c["status"] in ("PASS", "SKIP") for c in data["checks"])


def test_doctor_fails_when_hook_command_cannot_run(proj, env, capsys):
    inst(proj)
    s = settings(proj)
    for ev in s["hooks"].values():
        for e in ev:
            for h in e["hooks"]:
                h["command"] = h["command"].replace(sys.executable, "/nonexistent/python")
    (proj / ".claude/settings.json").write_text(json.dumps(s))
    capsys.readouterr()
    assert doc(proj, env) == 1
    out = "\n".join(lines(capsys))
    assert "FAIL hook bash_guard run" in out and "FAIL manifest" in out and "NOT run" in out


def test_doctor_fails_when_hook_missing(proj, env, capsys):
    inst(proj)
    s = settings(proj)
    s["hooks"].pop("SessionStart")
    (proj / ".claude/settings.json").write_text(json.dumps(s))
    capsys.readouterr()
    assert doc(proj, env) == 1
    assert "FAIL hooks registered" in "\n".join(lines(capsys))


def test_doctor_fails_on_non_sonnet_agent_unless_allowed(proj, env, capsys):
    inst(proj, "--allow-model", "opus")
    capsys.readouterr()
    assert doc(proj, env) == 1
    assert "FAIL agent orchestrator" in "\n".join(lines(capsys))
    assert doc(proj, env, "--allow-model", "opus") == 0


def test_doctor_fails_on_missing_pin(proj, env, capsys):
    inst(proj)
    s = settings(proj)
    s.pop("model")
    s["env"].pop("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")
    (proj / ".claude/settings.json").write_text(json.dumps(s))
    capsys.readouterr()
    assert doc(proj, env) == 1
    out = "\n".join(lines(capsys))
    assert "FAIL model pin" in out and "FAIL env pin" in out


def test_doctor_fails_on_installer_permission_allow(proj, env, capsys):
    inst(proj)
    s = settings(proj)
    s["permissions"] = {"allow": [f"Bash({sys.executable} -m factory.hooks:*)"]}
    (proj / ".claude/settings.json").write_text(json.dumps(s))
    capsys.readouterr()
    assert doc(proj, env) == 1
    assert "FAIL permissions" in "\n".join(lines(capsys))


def test_doctor_fails_on_skill_problems(proj, env, capsys):
    inst(proj)
    (env / "sf").unlink()
    (env / "qa-supervisor").unlink()
    (env / "qa-supervisor").mkdir()
    (env / "qa-supervisor/SKILL.md").write_text("---\nname: other\n---\n")
    capsys.readouterr()
    assert doc(proj, env) == 1
    out = "\n".join(lines(capsys))
    assert "FAIL skill sf" in out and "FAIL skill qa-supervisor" in out


def test_doctor_fails_without_sf_on_path(proj, env, monkeypatch, capsys):
    inst(proj)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    capsys.readouterr()
    assert doc(proj, env) == 1
    assert "FAIL sf command" in "\n".join(lines(capsys))


def test_doctor_without_project_runs_global_checks(env, capsys):
    assert main(["doctor", "--skills-dir", str(env), "--factory-root", str(REPO), "--python", sys.executable]) == 0


def test_default_profile_makes_releasing_a_human_stop_a_one_way_door(tmp_path):
    """A `--by human:<ref>` declaration is typeable by an agent, so the guard must ask or deny the release command."""
    from factory.agents.profile import load_profile
    from factory.install.core import DEFAULT_PROFILE

    prof = tmp_path / "profile.yaml"
    prof.write_text(DEFAULT_PROFILE.format(name="demo"))
    p = load_profile(prof)
    assert any("hitl" in pat and "release" in pat for pat in p.one_way_door_patterns)


def _door_patterns(tmp_path):
    import re
    from factory.agents.profile import load_profile
    from factory.install.core import DEFAULT_PROFILE
    prof = tmp_path / "profile.yaml"
    prof.write_text(DEFAULT_PROFILE.format(name="demo"))
    return [re.compile(x) for x in load_profile(prof).one_way_door_patterns]


@pytest.mark.parametrize("cmd", [
    "python -c \"import factory.hitl.store as s; s.release('.', 'a', 'human:x')\"",
    "python -m factory.hitl release --root . --name a --by human:x",
    "python -m factory.cli hitl release --root . --name a --by human:x",
    "sf hitl --x release --name a", "sf hitl release --name a", "cat > .factory/stops/log.jsonl",
    "rm -rf .factory/stops"])
def test_release_and_store_access_match_door_patterns(tmp_path, cmd):
    assert any(p.search(cmd) for p in _door_patterns(tmp_path))


@pytest.mark.parametrize("cmd", ["sf hitl status --root .", "sf hitl request --name a --reason r", "ls .factory", "cat .factory/profile.yaml"])
def test_ordinary_hitl_commands_do_not_match(tmp_path, cmd):
    assert not any(p.search(cmd) for p in _door_patterns(tmp_path))


def test_doctor_never_runs_a_command_from_settings(proj, env, tmp_path, capsys):
    inst(proj)
    marker = tmp_path / "pwned"
    s = settings(proj)
    good = s["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = f"touch {marker}; {good}"
    s["hooks"]["SessionStart"][0]["hooks"].append(
        {"type": "command", "command": f"touch {marker} # -m factory.hooks session_start"})
    (proj / ".claude/settings.json").write_text(json.dumps(s))
    capsys.readouterr()
    assert doc(proj, env) == 1
    out = "\n".join(lines(capsys))
    assert not marker.exists()
    assert "FAIL hook path_guard run" in out and "FAIL hook command" in out and "NOT run" in out


def test_doctor_trusts_arguments_not_the_manifest(proj, env, tmp_path, capsys):
    inst(proj)
    man = json.loads((proj / ".factory/install-manifest.json").read_text())
    man["python"] = "/bin/false"
    (proj / ".factory/install-manifest.json").write_text(json.dumps(man))
    capsys.readouterr()
    assert doc(proj, env) == 0  # a poisoned manifest python is ignored; hooks ran via the trusted argv
    out = "\n".join(lines(capsys))
    assert "PASS hook bash_guard deny" in out
