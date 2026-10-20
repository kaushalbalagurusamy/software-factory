"""SFN-01 E-10: `sf ops autobundle install|uninstall|status` manages a marked block in the post-commit hook."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .conftest import GIT_ID, REPO, SF_CODE, child_env, commit, git, read_events, sf

BEGIN = "# >>> sf ops autobundle >>>"
END = "# <<< sf ops autobundle <<<"
EXISTING = "#!/bin/sh\n# my own hook\ntouch \"$PWD/.ran-existing\"\n"


def hook_path(repo) -> Path:
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks/post-commit"))


def block_of(text: str) -> str:
    assert text.count(BEGIN) == 1 and text.count(END) == 1, text
    return text[text.index(BEGIN): text.index(END) + len(END)]


def shim_bin(tmp_path: Path, body: str | None = None) -> Path:
    """A directory holding an `sf` that runs THIS checkout's code (the installed sf may point elsewhere)."""
    d = tmp_path / "shimbin"
    d.mkdir(exist_ok=True)
    f = d / "sf"
    f.write_text(body or f'#!/bin/sh\nexport PYTHONPATH="{REPO}"\nexec "{sys.executable}" -c \'{SF_CODE}\' "$@"\n')
    f.chmod(0o755)
    return d


def commit_with_path(repo, path_dirs, msg="next"):
    env = child_env(PATH=os.pathsep.join([*map(str, path_dirs), "/usr/bin", "/bin"]))
    t0 = time.monotonic()
    p = subprocess.run(["git", "-C", str(repo), *GIT_ID, "commit", "-q", "--allow-empty", "-m", msg],
                       capture_output=True, text=True, env=env, timeout=40)
    return p, time.monotonic() - t0


def test_E10_install_writes_a_marked_executable_block_that_bundles_head(repo):
    r = sf(repo, "ops", "autobundle", "install")
    assert r.returncode == 0, r.stderr
    p = hook_path(repo)
    text = p.read_text()
    assert text.startswith("#!")
    blk = block_of(text)
    assert "sf ops bundle --sha HEAD" in blk
    assert "timeout" in blk and "120" in blk
    assert "&" in blk  # runs in the background
    assert p.stat().st_mode & stat.S_IXUSR


def test_E10_install_is_idempotent_byte_for_byte(repo):
    sf(repo, "ops", "autobundle", "install")
    first = hook_path(repo).read_bytes()
    r = sf(repo, "ops", "autobundle", "install")
    assert r.returncode == 0
    assert hook_path(repo).read_bytes() == first
    assert first.decode().count(BEGIN) == 1


def test_E10_install_preserves_existing_hook_content_and_still_runs_it(repo, tmp_path):
    p = hook_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(EXISTING)
    p.chmod(0o644)  # not executable yet: install must set the bit
    assert sf(repo, "ops", "autobundle", "install").returncode == 0
    new = p.read_text()
    # Amended after the independent review (finding 3): the block goes right after the shebang so a later top-level
    # `exit` cannot skip it; the existing hook content must survive unchanged and in order after the block.
    first, rest = EXISTING.split("\n", 1)
    assert new.startswith(first + "\n")
    assert rest.rstrip("\n") in new
    assert new.index("# >>> sf ops autobundle >>>") < new.index(rest.rstrip("\n"))
    block_of(new)
    assert p.stat().st_mode & stat.S_IXUSR
    again = p.read_bytes()
    sf(repo, "ops", "autobundle", "install")
    assert p.read_bytes() == again
    proc, _ = commit_with_path(repo, [shim_bin(tmp_path)])
    assert proc.returncode == 0, proc.stderr
    assert (repo / ".ran-existing").exists()


def test_E10_the_hook_bundles_the_new_commit_in_the_background(repo, tmp_path):
    sf(repo, "ops", "autobundle", "install")
    proc, _ = commit_with_path(repo, [shim_bin(tmp_path)], "bundled by hook")
    assert proc.returncode == 0, proc.stderr
    head = git(repo, "rev-parse", "HEAD")
    deadline = time.monotonic() + 12
    done = False
    while time.monotonic() < deadline:
        if (repo / "ops" / "snapshots" / head / "manifest.json").is_file() and any(
                e["stage"] == "11-commit" for e in read_events(repo)):
            done = True
            break
        time.sleep(0.3)
    assert done, "post-commit hook did not produce the snapshot (and its 11-commit event) for the new commit"


def test_E10_a_missing_or_failing_sf_never_fails_the_commit(repo, tmp_path):
    sf(repo, "ops", "autobundle", "install")
    proc, _ = commit_with_path(repo, [])  # no sf on PATH at all
    assert proc.returncode == 0, proc.stderr
    failing = shim_bin(tmp_path, "#!/bin/sh\nexit 7\n")
    proc, _ = commit_with_path(repo, [failing])
    assert proc.returncode == 0, proc.stderr
    hp = subprocess.run(["sh", str(hook_path(repo))], cwd=str(repo), capture_output=True, text=True,
                        env=child_env(PATH="/usr/bin:/bin"), timeout=30)
    assert hp.returncode == 0


def test_E10_the_hook_does_not_make_the_commit_wait_for_the_bundle(repo, tmp_path):
    assert sf(repo, "ops", "autobundle", "install").returncode == 0
    block_of(hook_path(repo).read_text())
    slow = shim_bin(tmp_path, "#!/bin/sh\nsleep 6\n")
    proc, took = commit_with_path(repo, [slow])
    assert proc.returncode == 0
    assert took < 4.5, f"commit took {took:.1f}s: the bundle must run detached (stdio redirected, backgrounded)"


def test_E10_uninstall_removes_only_the_block_and_keeps_other_content(repo):
    p = hook_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(EXISTING)
    p.chmod(0o755)
    sf(repo, "ops", "autobundle", "install")
    r = sf(repo, "ops", "autobundle", "uninstall")
    assert r.returncode == 0, r.stderr
    left = p.read_text()
    assert BEGIN not in left and END not in left and "sf ops bundle" not in left
    assert [ln for ln in left.splitlines() if ln.strip()] == [ln for ln in EXISTING.splitlines() if ln.strip()]
    assert p.stat().st_mode & stat.S_IXUSR


def test_E10_uninstall_deletes_a_hook_that_install_created_alone(repo):
    p = hook_path(repo)
    assert not p.exists()
    sf(repo, "ops", "autobundle", "install")
    assert p.exists()
    assert sf(repo, "ops", "autobundle", "uninstall").returncode == 0
    assert not p.exists()


def test_E10_uninstall_when_nothing_is_installed_changes_nothing(repo):
    p = hook_path(repo)
    r = sf(repo, "ops", "autobundle", "uninstall")
    assert r.returncode == 0
    assert not p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(EXISTING)
    sf(repo, "ops", "autobundle", "uninstall")
    assert p.read_text() == EXISTING


def test_E10_status_reports_installed_or_not(repo):
    before = sf(repo, "ops", "autobundle", "status")
    assert "not installed" in (before.stdout + before.stderr).lower()
    sf(repo, "ops", "autobundle", "install")
    after = sf(repo, "ops", "autobundle", "status")
    text = (after.stdout + after.stderr).lower()
    assert "installed" in text and "not installed" not in text
    sf(repo, "ops", "autobundle", "uninstall")
    assert "not installed" in (sf(repo, "ops", "autobundle", "status").stdout).lower()


def test_E10_status_changes_nothing(repo):
    sf(repo, "ops", "autobundle", "install")
    first = hook_path(repo).read_bytes()
    sf(repo, "ops", "autobundle", "status")
    assert hook_path(repo).read_bytes() == first


def test_E10_repo_option_from_another_directory(repo, bare_dir):
    assert sf(bare_dir, "ops", "autobundle", "install", "--repo", str(repo)).returncode == 0
    block_of(hook_path(repo).read_text())
    assert not (bare_dir / ".git").exists()


def test_E10_linked_worktree_uses_the_common_hooks_directory(repo, tmp_path):
    wt = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "wtbranch", str(wt))
    assert sf(wt, "ops", "autobundle", "install").returncode == 0
    common = repo / ".git" / "hooks" / "post-commit"
    block_of(common.read_text())
    assert not list((repo / ".git" / "worktrees").glob("*/hooks/post-commit"))
    assert "not installed" not in sf(wt, "ops", "autobundle", "status").stdout.lower()
    assert sf(wt, "ops", "autobundle", "uninstall").returncode == 0
    assert not common.exists()


def test_E10_outside_a_git_repository_is_refused(bare_dir):
    r = sf(bare_dir, "ops", "autobundle", "install")
    assert r.returncode != 0 and "git" in r.stderr.lower() and "invalid choice" not in r.stderr
    assert not (bare_dir / ".git").exists()
