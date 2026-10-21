import os
import re
import subprocess

from conftest import SKILL


def sh(env, *args):
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(["sh", str(SKILL / "install.sh")] + list(args), capture_output=True, text=True, env=e)


def test_install_twice_and_backup(tmp_path):
    skills, bindir = tmp_path / "skills", tmp_path / "bin"
    env = {"CLAUDE_SKILLS_DIR": str(skills), "LSF_BIN_DIR": str(bindir), "HOME": str(tmp_path)}
    r = sh(env)
    assert r.returncode == 0 and (skills / "lsf" / "SKILL.md").is_file() and (bindir / "lsf").is_file()
    wrapper = (bindir / "lsf").read_text()
    assert len(wrapper.splitlines()) <= 15 and "python3" in wrapper and "lsf.py" in wrapper
    launcher = bindir / "claude-lsf"
    assert launcher.is_file()
    launched = subprocess.run([str(launcher), "--help"], capture_output=True, text=True)
    assert launched.returncode == 0 and "--model" in launched.stdout
    again = sh(env)
    assert again.returncode == 0 and "nothing changed" in again.stdout
    assert not [p for p in skills.iterdir() if "backup" in p.name] and not (tmp_path / "skills-backups").exists()
    (skills / "lsf" / "SKILL.md").write_text("different")
    third = sh(env)
    assert not [p for p in skills.iterdir() if "backup" in p.name]
    backups = [p.name for p in (tmp_path / "skills-backups").iterdir() if p.name.startswith("lsf.backup-")]
    assert third.returncode == 0 and len(backups) == 1 and re.match(r"^lsf\.backup-\d+$", backups[0])
    out = subprocess.run([str(bindir / "lsf"), "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "init" in out.stdout


def test_posix_script_has_no_gnu_only_flags():
    t = (SKILL / "install.sh").read_text()
    assert t.startswith("#!/bin/sh")
    for bad in ("sha256sum", "realpath", "cp -a", "mktemp --", "readlink -f", "sed -i", "date -d", "stat -c"):
        assert bad not in t


def test_skill_frontmatter_and_content():
    t = (SKILL / "SKILL.md").read_text()
    fm = t.split("---")[1]
    assert "name: lsf" in fm and "disable-model-invocation: true" in fm
    for must in ("lsf hitl status", "Never run `lsf hitl release`", "60%", "20%", "0-intake", "10-docs", "ELI12", "Ponytail", "models"):
        assert must in t
    assert not re.search(r"(?i)\b(opus|sonnet|haiku|gpt-?\d)", t)


def test_eli12_copy_identical_when_source_exists():
    src = SKILL.parents[1] / "skills" / "eli12-docs" / "scripts" / "eli12.py"
    dst = SKILL / "scripts" / "eli12.py"
    if src.exists():
        assert dst.read_bytes() == src.read_bytes()


def test_eli12_and_jargon_copies_identical_and_installed(tmp_path):
    root = SKILL.parents[1] / "skills" / "eli12-docs"
    for rel in ("scripts/eli12.py", "assets/jargon.txt"):
        assert (SKILL / rel).read_bytes() == (root / rel).read_bytes(), rel
    skills = tmp_path / "s"
    r = sh({"CLAUDE_SKILLS_DIR": str(skills), "LSF_BIN_DIR": str(tmp_path / "b"), "HOME": str(tmp_path)})
    assert r.returncode == 0
    assert (skills / "lsf" / "scripts" / "eli12.py").is_file() and (skills / "lsf" / "assets" / "jargon.txt").is_file()


def test_skill_names_prds_and_dashboard_copy_path():
    t = (SKILL / "SKILL.md").read_text()
    for p in ("docs/prds", "docs/adr", "experiments/", "research/", "docs/eli12", "docs/explorer", "docs/bugs"):
        assert p in t, p
    assert "Copy path" in (SKILL / "assets" / "dashboard.html").read_text()


def test_mac_quick_start_section():
    t = (SKILL / "SKILL.md").read_text()
    assert "## Mac quick start" in t and "python3 --version" in t and "sh install.sh" in t and "lsf serve --open" in t and "#token=" in t
