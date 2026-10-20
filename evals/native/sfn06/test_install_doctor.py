"""L-01 install.sh and L-13 doctor."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import LSF, PY, SKILL, clean_env, free_port

INSTALL = SKILL / "install.sh"


def need_install():
    if not INSTALL.is_file():
        pytest.fail(f"{INSTALL} does not exist yet (SFN-06 not implemented)", pytrace=False)


def snapshot(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_symlink():
            out[str(p.relative_to(root))] = "->" + os.readlink(p)
    return out


class Box:
    def __init__(self, tmp):
        self.home = tmp / "home"
        self.skills = tmp / "skills"
        self.bin = tmp / "bin"
        for d in (self.home, self.skills, self.bin):
            d.mkdir()
        self.env = clean_env(self.home, CLAUDE_SKILLS_DIR=str(self.skills), LSF_BIN_DIR=str(self.bin))
        self.sh = "sh"

    def install(self, env=None, sh=None):
        need_install()
        e = dict(self.env)
        e.update(env or {})
        return subprocess.run([sh or self.sh, str(INSTALL)], env=e, capture_output=True, text=True, timeout=30,
                              cwd=str(self.home))


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def test_L01_install_copies_skill_and_links_wrapper(box):
    p = box.install()
    assert p.returncode == 0, p.stdout + p.stderr
    dest = box.skills / "lsf"
    for rel in ("SKILL.md", "scripts/lsf.py", "scripts/eli12.py", "assets/dashboard.html", "assets/editor-links.js"):
        assert (dest / rel).is_file(), rel
    assert (dest / "scripts" / "lsf.py").read_bytes() == LSF.read_bytes()
    assert not list(dest.rglob("__pycache__"))
    w = box.bin / "lsf"
    assert w.exists() and os.access(w, os.X_OK)
    body = w.read_text()
    assert "python3" in body and str(dest / "scripts" / "lsf.py") in body
    assert len(body.splitlines()) <= 15, "tiny wrapper"
    assert not body.startswith("#!/usr/bin/env bash")
    h = subprocess.run([str(w), "--help"], env=box.env, capture_output=True, text=True, timeout=20)
    assert h.returncode == 0 and "init" in h.stdout


def test_L01_install_prints_what_it_did(box):
    p = box.install()
    out = p.stdout + p.stderr
    assert str(box.skills / "lsf") in out and str(box.bin / "lsf") in out


def test_L01_install_touches_nothing_outside_the_target_dirs(box):
    box.install()
    assert list(box.home.iterdir()) == []


def test_L01_install_defaults_under_home(tmp_path):
    need_install()
    home = tmp_path / "h"
    home.mkdir()
    env = clean_env(home)
    p = subprocess.run(["sh", str(INSTALL)], env=env, capture_output=True, text=True, timeout=30, cwd=str(home))
    assert p.returncode == 0, p.stderr
    assert (home / ".claude" / "skills" / "lsf" / "SKILL.md").is_file()
    assert (home / ".local" / "bin" / "lsf").exists()


def test_L01_second_run_changes_nothing_and_says_so(box):
    box.install()
    s1, b1 = snapshot(box.skills), snapshot(box.bin)
    mt = (box.bin / "lsf").stat().st_mtime_ns
    p = box.install()
    assert p.returncode == 0
    assert snapshot(box.skills) == s1 and snapshot(box.bin) == b1
    assert (box.bin / "lsf").stat().st_mtime_ns == mt
    assert not [d for d in box.skills.iterdir() if "backup" in d.name]
    assert (p.stdout + p.stderr).strip()


def test_L01_existing_different_lsf_is_backed_up_first(box):
    old = box.skills / "lsf"
    old.mkdir()
    (old / "SKILL.md").write_text("the OLD lsf skill\n")
    (old / "extra.txt").write_text("keep me\n")
    p = box.install()
    assert p.returncode == 0, p.stdout + p.stderr
    backups = [d for d in box.skills.iterdir() if re.fullmatch(r"lsf\.backup-.*\d.*", d.name)]
    assert len(backups) == 1
    assert (backups[0] / "SKILL.md").read_text() == "the OLD lsf skill\n"
    assert (backups[0] / "extra.txt").read_text() == "keep me\n"
    assert "name: lsf" in (box.skills / "lsf" / "SKILL.md").read_text()
    assert not (box.skills / "lsf" / "extra.txt").exists()
    # and a further run does not make another backup
    box.install()
    assert len([d for d in box.skills.iterdir() if d.name.startswith("lsf.backup-")]) == 1


def test_L01_install_works_under_dash_if_present(box):
    if not shutil.which("dash"):
        pytest.skip("dash not installed")
    p = box.install(sh="dash")
    assert p.returncode == 0, p.stderr
    assert (box.skills / "lsf" / "SKILL.md").is_file()


def test_L01_install_script_is_posix_sh_and_macos_safe():
    need_install()
    text = INSTALL.read_text()
    first = text.splitlines()[0]
    assert first in ("#!/bin/sh", "#!/usr/bin/env sh")
    p = subprocess.run(["sh", "-n", str(INSTALL)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    for bad in (r"readlink\s+-f", r"sed\s+-i", r"cp\s+-[a-zA-Z]*a", r"date\s+-d", r"stat\s+-c", r"\[\[", r"<<<",
                r"(^|\s)source\s", r"\becho\s+-e", r"\bdeclare\b", r"\breadarray\b", r"\$'", r"\bmktemp\s+--", r"\brealpath\b",
                r"\bxargs\s+-r", r"\bgrep\s+-P", r"--parents", r"cp\s+--", r"\btac\b", r"\bsha256sum\b"):
        assert not re.search(bad, text, re.M), bad


# ---------------------------------------------------------------- L-13 doctor
def doctor(rig, *args, env=None):
    return rig.run("doctor", "--port", free_port(), *args, env=env)


def lines_for(out, word):
    return [l for l in out.splitlines() if word.lower() in l.lower()]


def test_L13_doctor_passes_on_a_healthy_repo(inited):
    p = doctor(inited)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "PASS" in p.stdout and "FAIL" not in p.stdout
    for w in ("python", "git", "port", "node", "editor", ".lsf", "syntax"):
        assert lines_for(p.stdout, w), w


def tool_path(tmp_path, *names):
    d = tmp_path / "toolbin"
    d.mkdir()
    for n in names:
        src = sys.executable if n == "python3" else shutil.which(n)
        if src:
            os.symlink(src, d / n)
    return str(d)


def test_L13_missing_git_is_a_fail_not_a_pass(inited, tmp_path):
    path = tool_path(tmp_path, "python3")
    p = doctor(inited, env={"PATH": path})
    assert p.returncode == 1, p.stdout + p.stderr
    gl = lines_for(p.stdout, "git")
    assert gl and any("FAIL" in l for l in gl)
    assert not any("PASS" in l for l in gl), "no PASS for a check that could not run"


def test_L13_missing_node_is_informational_only(inited, tmp_path):
    path = tool_path(tmp_path, "python3", "git")
    p = doctor(inited, env={"PATH": path})
    assert p.returncode == 0, p.stdout + p.stderr
    nl = lines_for(p.stdout, "node")
    assert nl and not any("FAIL" in l for l in nl)


def test_L13_occupied_port_fails(inited):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        p = inited.run("doctor", "--port", s.getsockname()[1])
    finally:
        s.close()
    assert p.returncode == 1
    assert any("FAIL" in l for l in lines_for(p.stdout, "port"))


def test_L13_unwritable_lsf_dir_fails(rig):
    (rig.repo / ".lsf").write_text("i am a file, not a directory\n")
    p = doctor(rig)
    assert p.returncode == 1
    assert any("FAIL" in l for l in lines_for(p.stdout, ".lsf"))


def test_L13_not_a_git_repository_fails(rig, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert rig.run("init", cwd=plain).returncode == 0
    p = rig.run("doctor", "--port", free_port(), cwd=plain)
    assert p.returncode == 1
    assert "FAIL" in p.stdout


def test_L13_unknown_editor_fails_and_known_ones_pass(inited):
    inited.edit_profile(lambda p: p.update(editor="emacs-ish"))
    p = doctor(inited)
    assert p.returncode == 1 and any("FAIL" in l for l in lines_for(p.stdout, "editor"))
    for ed in ("vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate", "none"):
        inited.edit_profile(lambda p, ed=ed: p.update(editor=ed))
        assert doctor(inited).returncode == 0, ed


def test_L13_syntax_self_check_flags_python310_code(inited, tmp_path):
    """doctor checks the lsf.py it is running; a copy with 3.10 syntax must FAIL the syntax line."""
    bad = tmp_path / "copy" / "lsf.py"
    bad.parent.mkdir()
    bad.write_text(LSF.read_text() + "\n\nmatch 1:\n    case 1:\n        pass\n")
    p = subprocess.run([PY, str(bad), "doctor", "--port", str(free_port())], cwd=str(inited.repo), env=inited.env,
                       capture_output=True, text=True, timeout=20)
    # the module itself may refuse to import on 3.9-parse; either way it must not report a clean doctor
    assert p.returncode != 0
    assert "PASS" not in "".join(l for l in p.stdout.splitlines() if "syntax" in l.lower())

