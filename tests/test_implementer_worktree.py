"""The blind-implementer worktree script must really leave protected paths out of the working tree."""
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "implementer-worktree.sh"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def run(*args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "evals").mkdir(parents=True)
    (repo / "held_out").mkdir()
    (repo / "src").mkdir()
    (repo / "evals" / "case.py").write_text("SECRET_CASE = 1\n")
    (repo / "held_out" / "h.py").write_text("H = 1\n")
    (repo / "src" / "app.py").write_text("X = 1\n")
    run("git", "init", "-q", cwd=repo)
    run(*GIT, "add", "evals", "held_out", "src", cwd=repo)
    run(*GIT, "commit", "-q", "-m", "init", cwd=repo)
    return repo


def test_default_protects_evals(tmp_path):
    repo = make_repo(tmp_path)
    r = run("bash", str(SCRIPT), "impl1", "HEAD", "--root", str(tmp_path / "wt"), cwd=repo)
    wt = tmp_path / "wt" / "impl1"
    assert (wt / "src" / "app.py").exists()
    assert not (wt / "evals").exists(), r.stdout
    deny = json.loads((wt / ".claude" / "settings.local.json").read_text())["permissions"]["deny"]
    assert "Read(./evals/**)" in deny


def test_extra_protected_paths_and_branch(tmp_path):
    repo = make_repo(tmp_path)
    run("bash", str(SCRIPT), "impl2", "HEAD", "--protect", "evals/", "--protect", "held_out/", "--root", str(tmp_path / "wt"), cwd=repo)
    wt = tmp_path / "wt" / "impl2"
    assert not (wt / "evals").exists() and not (wt / "held_out").exists()
    assert (wt / "src").is_dir()
    assert run("git", "branch", "--show-current", cwd=wt).stdout.strip() == "sf/impl2"


def test_commits_in_worktree_do_not_resurrect_protected_paths(tmp_path):
    repo = make_repo(tmp_path)
    run("bash", str(SCRIPT), "impl3", "HEAD", "--root", str(tmp_path / "wt"), cwd=repo)
    wt = tmp_path / "wt" / "impl3"
    (wt / "src" / "app.py").write_text("X = 2\n")
    run(*GIT, "add", "src/app.py", cwd=wt)
    run(*GIT, "commit", "-q", "-m", "change", cwd=wt)
    assert not (wt / "evals").exists()
    # the local deny file is excluded from status, so it cannot be committed by accident
    assert ".claude" not in run("git", "status", "--short", cwd=wt).stdout


def test_refuses_existing_destination_and_bad_name(tmp_path):
    repo = make_repo(tmp_path)
    run("bash", str(SCRIPT), "impl4", "HEAD", "--root", str(tmp_path / "wt"), cwd=repo)
    again = run("bash", str(SCRIPT), "impl4", "HEAD", "--root", str(tmp_path / "wt"), cwd=repo, check=False)
    assert again.returncode != 0
    bad = run("bash", str(SCRIPT), "../escape", "HEAD", "--root", str(tmp_path / "wt"), cwd=repo, check=False)
    assert bad.returncode != 0
