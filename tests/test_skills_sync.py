"""Tests for scripts/skills_sync.py. All filesystem work happens under tmp_path."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "skills_sync.py"


def run(*args, expect=None):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True, text=True,
    )
    if expect is not None:
        assert proc.returncode == expect, proc.stdout + proc.stderr
    return proc


def make_skill(root: Path, name: str, body: str = "body\n", fm_name=None):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {fm_name or name}\ndescription: >-\n  Does a thing.\n---\n{body}"
    )
    return d


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo_skills"
    live = tmp_path / "live"
    backups = tmp_path / "backups"
    repo.mkdir()
    live.mkdir()
    make_skill(repo, "alpha")
    make_skill(repo, "beta")
    return repo, live, backups


def common(repo, live, backups=None):
    a = ["--repo-skills", repo, "--skills-dir", live]
    if backups is not None:
        a += ["--backup-dir", backups]
    return a


# ---- install ----------------------------------------------------------

def test_install_links_when_absent(env):
    repo, live, backups = env
    run("install", *common(repo, live, backups), expect=0)
    assert (live / "alpha").is_symlink()
    assert (live / "alpha").resolve() == (repo / "alpha").resolve()
    assert (live / "beta").is_symlink()


def test_no_clobber_without_adopt(env):
    repo, live, backups = env
    make_skill(live, "alpha", body="different\n")
    proc = run("install", *common(repo, live, backups))
    assert proc.returncode != 0
    assert not (live / "alpha").is_symlink()
    assert "different" in (live / "alpha" / "SKILL.md").read_text()
    assert "differs" in proc.stdout
    assert not backups.exists()
    # the absent one may still be linked, but the real dir is untouched
    assert (live / "alpha" / "SKILL.md").exists()


def test_adopt_backs_up_then_links(env):
    repo, live, backups = env
    make_skill(live, "alpha", body="old live copy\n")
    run("install", "--adopt", *common(repo, live, backups), expect=0)
    assert (live / "alpha").is_symlink()
    saved = list(backups.glob("*/alpha/SKILL.md"))
    assert len(saved) == 1
    assert "old live copy" in saved[0].read_text()


def test_install_idempotent(env):
    repo, live, backups = env
    make_skill(live, "alpha")
    run("install", "--adopt", *common(repo, live, backups), expect=0)
    before = sorted(p.name for p in backups.glob("*"))
    run("install", "--adopt", *common(repo, live, backups), expect=0)
    run("install", *common(repo, live, backups), expect=0)
    assert sorted(p.name for p in backups.glob("*")) == before
    assert (live / "alpha").is_symlink()


def test_dry_run_changes_nothing(env):
    repo, live, backups = env
    make_skill(live, "alpha", body="keep\n")
    proc = run("install", "--adopt", "--dry-run", *common(repo, live, backups), expect=0)
    assert "alpha" in proc.stdout and "beta" in proc.stdout
    assert not (live / "alpha").is_symlink()
    assert not (live / "beta").exists()
    assert not backups.exists()


def test_install_never_deletes_foreign_link(env, tmp_path):
    repo, live, backups = env
    other = tmp_path / "elsewhere"
    other.mkdir()
    (live / "alpha").symlink_to(other)
    proc = run("install", *common(repo, live, backups))
    assert proc.returncode != 0
    assert (live / "alpha").is_symlink() and (live / "alpha").resolve() == other.resolve()


# ---- status -----------------------------------------------------------

def test_status_classifications(env):
    repo, live, backups = env
    make_skill(repo, "gamma")
    make_skill(repo, "delta")
    make_skill(live, "alpha")                        # identical
    make_skill(live, "beta", body="changed\n")       # differs
    (live / "gamma").symlink_to(repo / "gamma")      # link to repo
    # delta: missing-installed
    out = run("status", *common(repo, live), expect=0).stdout
    lines = {l.split()[0]: l for l in out.splitlines() if l.strip()}
    assert "identical" in lines["alpha"]
    assert "differs" in lines["beta"]
    assert "installed-is-link-to-repo" in lines["gamma"]
    assert "missing-installed" in lines["delta"]


def test_status_diff_option(env):
    repo, live, _ = env
    make_skill(live, "alpha", body="changed\n")
    out = run("status", "--diff", *common(repo, live), expect=0).stdout
    assert "+changed" in out and "-body" in out


def test_status_ignores_pycache(env):
    repo, live, _ = env
    make_skill(live, "alpha")
    (live / "alpha" / "__pycache__").mkdir()
    (live / "alpha" / "__pycache__" / "x.pyc").write_bytes(b"x")
    out = run("status", *common(repo, live), expect=0).stdout
    assert "identical" in [l for l in out.splitlines() if l.startswith("alpha")][0]


# ---- check ------------------------------------------------------------

def test_check_passes_on_good_tree(env):
    repo, _, _ = env
    run("check", "--repo-skills", repo, expect=0)


def test_check_fails_name_mismatch(env):
    repo, _, _ = env
    make_skill(repo, "gamma", fm_name="other")
    proc = run("check", "--repo-skills", repo)
    assert proc.returncode != 0 and "gamma" in proc.stdout + proc.stderr


def test_check_fails_missing_frontmatter(env):
    repo, _, _ = env
    (repo / "alpha" / "SKILL.md").write_text("no frontmatter\n")
    assert run("check", "--repo-skills", repo).returncode != 0


def test_check_fails_missing_description(env):
    repo, _, _ = env
    (repo / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\nx\n")
    assert run("check", "--repo-skills", repo).returncode != 0


def test_check_fails_pycache(env):
    repo, _, _ = env
    (repo / "alpha" / "__pycache__").mkdir()
    assert run("check", "--repo-skills", repo).returncode != 0


@pytest.mark.parametrize("secret", [
    "sk-" + "a1B2c3D4" * 4,
    "ghp_" + "a1B2c3D4e5" * 3,
    "glpat-" + "a1B2c3D4e5f6g7h8",
    "AKIA" + "ABCDEFGH12345678",
    "-----BEGIN " + "RSA PRIVATE KEY-----",
    'api_key = "' + "q" * 32 + '"',
])
def test_check_fails_planted_secret(env, secret):
    repo, _, _ = env
    (repo / "alpha" / "notes.md").write_text(f"hello\n{secret}\n")
    proc = run("check", "--repo-skills", repo)
    assert proc.returncode != 0
    assert "alpha/notes.md" in proc.stdout + proc.stderr


def test_check_passes_on_real_repo_skills():
    proc = run("check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_real_repo_has_loop_skills():
    for n in ["sf", "prd-writer", "implementation-review", "orchestration",
              "ops-dashboard-design", "eval-designer", "axiomatic-spec", "doc-sync"]:
        assert (REPO / "skills" / n / "SKILL.md").is_file(), n
