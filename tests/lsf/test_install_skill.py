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
    again = sh(env)
    assert again.returncode == 0 and "nothing changed" in again.stdout
    assert not [p for p in skills.iterdir() if "backup" in p.name]
    (skills / "lsf" / "SKILL.md").write_text("different")
    third = sh(env)
    backups = [p.name for p in skills.iterdir() if p.name.startswith("lsf.backup-")]
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
