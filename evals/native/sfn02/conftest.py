"""Shared harness for SFN-02 acceptance tests. Everything runs in tmp dirs; HOME is redirected.

An isolated factory copy (factory/, skills/, scripts/, docs/external-skills.json when present) is the
--factory-root AND the cwd/PYTHONPATH of every subprocess, so a test can edit a role yaml without
touching the repo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
ROLES8 = ("orchestrator", "research", "design", "audit", "implement", "qa", "test", "review")
EXTERNAL = ("minesweeper", "spec-recomposition", "biz-decomposer", "grounded-research", "deep-research",
            "experiment-designer", "one-way-door", "progress-briefing", "away-mode", "good-night")
BUILTIN = {"claude-api"}


class Rig:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.root = tmp / "root"
        shutil.copytree(REPO / "factory", self.root / "factory", ignore=shutil.ignore_patterns("__pycache__"))
        for d in (REPO / "skills").iterdir():  # SKILL.md only: the tree is large and doctor reads just that
            if d.is_dir() and (d / "SKILL.md").is_file() and not d.name.startswith("_"):
                (self.root / "skills" / d.name).mkdir(parents=True)
                shutil.copy(d / "SKILL.md", self.root / "skills" / d.name / "SKILL.md")
        shutil.copytree(REPO / "scripts", self.root / "scripts")
        (self.root / "docs").mkdir()
        if (REPO / "docs/external-skills.json").is_file():
            shutil.copy(REPO / "docs/external-skills.json", self.root / "docs/external-skills.json")
        self.home = tmp / "home"
        self.skills = tmp / "userskills"
        self.proj = tmp / "proj"
        for d in (self.home, self.skills, self.proj):
            d.mkdir()
        bindir = tmp / "bin"
        bindir.mkdir()
        sf = bindir / "sf"
        sf.write_text(f'#!/bin/sh\nexec {sys.executable} -m factory.cli "$@"\n')
        sf.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PYTHONPATH=str(self.root),
                        PATH=f"{bindir}:{os.environ['PATH']}")
        self.env.pop("CLAUDE_CONFIG_DIR", None)

    # ---- fake skill universe -------------------------------------------------------------
    @property
    def roles_dir(self) -> Path:
        return self.root / "factory/agents/roles"

    def role_skills(self) -> set[str]:
        out: set[str] = set()
        for f in self.roles_dir.glob("*.yaml"):
            out |= set(yaml.safe_load(f.read_text())["skills"])
        return out

    def stock_skills(self) -> None:
        """Make every skill any role names, plus the ten external ones, resolvable."""
        for d in (self.root / "skills").iterdir():
            if d.is_dir() and (d / "SKILL.md").is_file() and not d.name.startswith("_"):
                if not (self.skills / d.name).is_symlink():
                    (self.skills / d.name).symlink_to(d)
        plugins: dict = {}
        for name in self.role_skills() | set(EXTERNAL):
            if ":" in name:
                plug, skill = name.split(":", 1)
                base = self.home / ".claude/plugins/cache" / plug
                plugins[f"{plug}@test"] = [{"scope": "user", "installPath": str(base)}]
                self.stub(base / "skills" / skill, name)
            elif name in BUILTIN or (self.skills / name).exists():
                continue
            else:
                self.stub(self.skills / name, name)
        pj = self.home / ".claude/plugins/installed_plugins.json"
        pj.parent.mkdir(parents=True, exist_ok=True)
        pj.write_text(json.dumps({"version": 2, "plugins": plugins}))

    @staticmethod
    def stub(d: Path, name: str, extra: str = "") -> None:
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {name.split(':')[-1]}\ndescription: stub {name}{extra}\n---\n\nbody\n")

    # ---- commands --------------------------------------------------------------------------
    def run(self, *args, timeout=18):
        return subprocess.run([sys.executable, "-m", "factory.install", *map(str, args)], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=timeout)

    def common(self):
        return ["--factory-root", self.root, "--python", sys.executable]

    def install(self, *extra):
        return self.run("install", "--project", self.proj, *self.common(), *extra)

    def uninstall(self):
        return self.run("uninstall", "--project", self.proj)

    def doctor(self, *extra, project=True):
        a = ["doctor", "--skills-dir", self.skills, *self.common()]
        if project:
            a += ["--project", self.proj]
        return self.run(*a, *extra)

    def pin(self, *extra, accept_changed=True):
        # Amended after the independent review (finding: pin-external must not launder a changed skill): re-pinning
        # skills whose hash differs from the shipped pin needs --accept-changed NAME. The fixture's stub skills always
        # differ from the shipped pins, so --yes calls here accept them explicitly; test_pin_external_requires_accept_changed
        # covers the refusal.
        acc = []
        if accept_changed and "--yes" in extra:
            for n in EXTERNAL:
                acc += ["--accept-changed", n]
        return self.run("pin-external", "--skills-dir", self.skills, "--factory-root", self.root, *extra, *acc)

    @property
    def pins(self) -> Path:
        return self.root / "docs/external-skills.json"

    def agents(self) -> list[Path]:
        return sorted((self.proj / ".claude/agents").glob("*.md"))

    def agent_fm(self, role: str) -> dict:
        return yaml.safe_load((self.proj / f".claude/agents/{role}.md").read_text().split("---")[1])

    def set_role(self, role: str, **kv) -> None:
        p = self.roles_dir / f"{role}.yaml"
        d = yaml.safe_load(p.read_text())
        d.update(kv)
        p.write_text(yaml.safe_dump(d, sort_keys=False))


@pytest.fixture
def rig(tmp_path):
    yield Rig(tmp_path)
    shutil.rmtree(tmp_path, ignore_errors=True)  # shared /tmp is small; do not leave copies behind


@pytest.fixture
def stocked(rig):
    """Installed project and every named skill resolvable; externals NOT pinned by the test."""
    rig.stock_skills()
    assert rig.install().returncode == 0, "install must succeed"
    return rig


@pytest.fixture
def ready(stocked):
    """Installed project, stocked skills, freshly pinned externals: doctor should be clean."""
    rig = stocked
    assert rig.pin("--yes").returncode == 0, "pin-external --yes must succeed"
    return rig


def lines(r):
    return (r.stdout + r.stderr).splitlines()
