"""Native install of the factory into a project: agents, settings (hooks, Sonnet pin), profile, manifest.

Never runs git in the project, never touches ``permissions``, never overwrites a differing file
without a backup, and writes nothing when the result would be byte-identical (idempotent).
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from factory.agents.generate import HOOK_REGISTRATION, GenerationError, generate_agents
from factory.agents.profile import ProfileError, load_profile, parse_profile
from factory.agents.roles import RoleError, ROLE_IDS, load_roles
from factory.agents.settings import emit_settings

MODEL = "sonnet"
ENV_PIN = {"CLAUDE_CODE_SUBAGENT_MODEL": MODEL, "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"}
MANIFEST = ".factory/install-manifest.json"
PROFILE = ".factory/profile.yaml"
SETTINGS = ".claude/settings.json"
DEFAULT_PROFILE = """\
# Written by `python -m factory.install` because the project had no profile. Edit freely; the
# installer never modifies an existing profile. Defaults: generic protected paths, the
# orchestrator as the main-session role, and the standard stage graph (the `graph` key is omitted,
# so the factory's default graph applies).
schema_version: 1
project: {{name: {name}}}
main_session_role: orchestrator
paths:
  eval: ["evals/**"]
  held_out: ["tests/held_out/**"]
  frozen_tests: ["tests/frozen/**"]
  baseline_update: ["evals/baselines/**"]
# Releasing a human stop is a one-way door: the orchestrator is asked, every other role is denied
# (a declaration `--by human:<ref>` alone would let an agent type it).
one_way_door_patterns:
  - 'factory\\.cli\\s+hitl'
  - '\\bsf\\s+hitl\\b.*\\brelease'
  - 'factory\\.hitl'
  - '\\.factory/stops'
"""


class InstallError(Exception):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def hook_command_prefix(root: Path, py: str) -> str:
    return f"PYTHONPATH={shlex.quote(str(root))} {shlex.quote(py)}"


def check_python(py: str, root: Path) -> None:
    """The interpreter must exist, be executable and import factory.hooks, z3 and yaml."""
    if not (os.path.isfile(py) and os.access(py, os.X_OK)):
        raise InstallError(f"python {py} does not exist or is not executable")
    env = dict(os.environ, PYTHONPATH=str(root))
    try:
        r = subprocess.run([py, "-c", "import factory.hooks, z3, yaml"], capture_output=True, text=True,
                           env=env, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise InstallError(f"python {py} cannot run: {e}") from None
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["no output"])[-1]
        raise InstallError(f"python {py} cannot import factory.hooks, z3 and yaml (root {root}): {tail}")


def _is_own(cmd) -> bool:
    return isinstance(cmd, str) and (cmd.startswith("python -m factory.hooks") or cmd.startswith("PYTHONPATH=")) \
        and any(cmd.endswith(f"-m factory.hooks {h}") for h in HOOK_REGISTRATION)


def _read_json(p: Path, what: str):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InstallError(f"{what} {p} is not readable JSON ({e}); refusing to overwrite it") from None


def _pin_agent(text: str, allowed: set[str], prefix: str) -> tuple[str, str, str]:
    """Return (text, proposed model, pinned model); only the frontmatter is touched."""
    head, sep, rest = text.partition("\n---\n")
    m = re.search(r"^model: (.*)$", head, re.M)
    proposed = m.group(1).strip() if m else ""
    pinned = proposed if proposed in allowed else MODEL
    head = re.sub(r"^model: .*$", f"model: {pinned}", head, count=1, flags=re.M)
    head = re.sub(r"command: python -m factory\.hooks (\w+)",
                  lambda mm: "command: " + json.dumps(f"{prefix} -m factory.hooks {mm.group(1)}"), head)
    return head + sep + rest, proposed, pinned


def _merge_settings(cur: dict, own_hooks: dict | None) -> dict:
    new = copy.deepcopy(cur)
    if own_hooks is not None:
        old = new.get("hooks") or {}
        if not isinstance(old, dict):
            raise InstallError("settings 'hooks' is not an object; refusing to overwrite it")
        merged: dict = {}
        for ev, entries in old.items():
            if not isinstance(entries, list):
                raise InstallError(f"settings hooks.{ev} is not a list; refusing to overwrite it")
            kept = []
            for e in entries:
                inner = e.get("hooks") if isinstance(e, dict) else None
                if not isinstance(inner, list):
                    kept.append(e)
                    continue
                rest = [h for h in inner if not (isinstance(h, dict) and _is_own(h.get("command")))]
                if rest:
                    kept.append({**e, "hooks": rest})
            if kept:
                merged[ev] = kept
        for ev, entries in own_hooks.items():
            merged[ev] = merged.get(ev, []) + entries
        new["hooks"] = merged
    new["model"] = MODEL
    env = new.get("env", {})
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise InstallError("settings 'env' is not an object; refusing to overwrite it")
    new["env"] = {**env, **ENV_PIN}
    return new


def _factory_version(root: Path) -> dict:
    v = None
    try:
        m = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
        v = m.group(1) if m else None
    except OSError:
        pass
    commit = None
    try:  # the factory checkout, never the target project
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        commit = r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"root": str(root), "version": v, "commit": commit}


def _atomic(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".sf-install-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, p)


def _diff(rel: str, old: bytes | None, new: bytes) -> str:
    a = (old or b"").decode("utf-8", "replace").splitlines()
    b = new.decode("utf-8", "replace").splitlines()
    return "\n".join(difflib.unified_diff(a, b, f"a/{rel}" if old is not None else "/dev/null",
                                          f"b/{rel}", lineterm="")) + "\n"


def install(project, *, factory_root=None, python=None, profile_src=None, hooks=True, agents=True,
            allow_models=(), dry_run=False, out=print) -> bool:
    """Install; return True when anything changed (or would change in a dry run)."""
    proj = Path(project).absolute()
    if not proj.is_dir():
        raise InstallError(f"project {proj} does not exist or is not a directory")
    root = Path(factory_root).resolve() if factory_root else Path(__file__).resolve().parents[2]
    if not (root / "factory" / "hooks" / "__main__.py").is_file():
        raise InstallError(f"{root} is not a factory checkout (no factory/hooks/__main__.py)")
    py = os.path.abspath(python) if python else str(root / ".venv" / "bin" / "python")
    check_python(py, root)
    allowed = {MODEL, *allow_models}
    prefix = hook_command_prefix(root, py)

    # profile
    prof_path = proj / PROFILE
    new_files: dict[str, bytes] = {}
    if prof_path.exists():
        try:
            profile = load_profile(prof_path)
        except (ProfileError, OSError, UnicodeDecodeError) as e:
            raise InstallError(f"existing profile {prof_path} is invalid: {e}") from None
        profile_state = "existing"
    else:
        if profile_src:
            text = Path(profile_src).read_text(encoding="utf-8")
        else:
            name = "project-" + sha(str(proj).encode())[:8]
            text = DEFAULT_PROFILE.format(name=name)
        try:
            profile = parse_profile(yaml.safe_load(text))
        except (ProfileError, yaml.YAMLError) as e:
            raise InstallError(f"profile to install is invalid: {e}") from None
        new_files[PROFILE] = text.encode()
        profile_state = "created"

    roles = None
    agent_models: dict = {}
    if agents or hooks:
        try:
            roles = load_roles()
            generated = generate_agents(profile, roles)
        except (GenerationError, RoleError) as e:
            raise InstallError(f"cannot generate agents: {e}") from None
    if agents:
        for rel, text in generated.items():
            text, proposed, pinned = _pin_agent(text, allowed, prefix)
            new_files[rel] = text.encode()
            agent_models[Path(rel).stem] = {"proposed": proposed, "pinned": pinned}

    # settings
    sp = proj / SETTINGS
    cur = {}
    cur_bytes = sp.read_bytes() if sp.exists() else None
    if cur_bytes is not None:
        cur = _read_json(sp, "settings")
        if not isinstance(cur, dict):
            raise InstallError(f"settings {sp} is not a JSON object; refusing to overwrite it")
    own = None
    if hooks:
        own = emit_settings(profile, roles)["hooks"]
        for entries in own.values():
            for e in entries:
                for h in e["hooks"]:
                    h["command"] = h["command"].replace("python -m factory.hooks", f"{prefix} -m factory.hooks", 1)
    new = _merge_settings(cur, own)
    if cur_bytes is None or new != cur:
        new_files[SETTINGS] = (json.dumps(new, indent=2, ensure_ascii=False) + "\n").encode()

    # manifest + backups
    prev = {"items": [], "backups": []}
    mp = proj / MANIFEST
    if mp.exists():
        prev = _read_json(mp, "manifest")
    prev_items = {i["path"]: i for i in prev.get("items", [])}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = proj / ".claude" / "backups" / stamp
    n = 1
    while bdir.exists():
        n += 1
        bdir = proj / ".claude" / "backups" / f"{stamp}-{n}"
    backups = list(prev.get("backups", []))
    to_write: dict[str, bytes] = {}
    items = []
    tracked = [PROFILE, *sorted(k for k in new_files if k not in (PROFILE, SETTINGS)), SETTINGS]
    for rel in tracked:
        p = proj / rel
        before = p.read_bytes() if p.exists() else None
        after = new_files.get(rel, before)
        if after is None:
            continue
        pi = prev_items.get(rel)
        origin = pi["origin"] if pi else ("created" if before is None else "existing")
        backup = pi.get("backup") if pi else None
        if rel in new_files and before is not None and before != after:
            b = str(bdir.relative_to(proj) / rel)
            to_write[b] = before
            backups.append(b)
            if origin == "existing" and backup is None:
                backup = b
        if rel in new_files and before != after:
            to_write[rel] = after
        items.append({"path": rel, "origin": origin, "sha256": sha(after), "backup": backup,
                      "tracked": rel != PROFILE})
    items += [i for r, i in prev_items.items() if r not in tracked]  # e.g. agents from an earlier full install
    manifest = {
        "schema": 1, "factory": _factory_version(root), "python": py, "model_pin": MODEL,
        "allowed_models": sorted(allowed), "env_pin": ENV_PIN,
        "options": {"hooks": hooks, "agents": agents},
        "agent_models": agent_models or prev.get("agent_models", {}),
        "items": items, "backups": backups,
    }
    mbytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    old_m = mp.read_bytes() if mp.exists() else None
    if old_m != mbytes:
        to_write[MANIFEST] = mbytes

    out(f"profile: {profile_state}" if profile_state == "created" or PROFILE in to_write
        else "profile: existing, not modified" if profile_state == "existing" else "profile: unchanged")
    if not to_write:
        out("unchanged")
        return False
    for rel in sorted(to_write):
        p = proj / rel
        before = p.read_bytes() if p.exists() else None
        if dry_run:
            out(_diff(rel, before, to_write[rel]).rstrip("\n"))
        else:
            out(f"{rel}: {'created' if before is None else 'updated'}")
    if dry_run:
        out("dry run: nothing written")
        return True
    for rel in sorted(to_write, key=lambda r: (r == MANIFEST, r)):
        _atomic(proj / rel, to_write[rel])
    return True


def uninstall(project, out=print, err=None) -> bool:
    """Undo an install from its manifest; True when every item was handled."""
    import sys
    err = err or (lambda m: print(m, file=sys.stderr))
    proj = Path(project).absolute()
    mp = proj / MANIFEST
    if not mp.exists():
        raise InstallError(f"no manifest at {mp}; nothing to uninstall")
    man = _read_json(mp, "manifest")
    left, refused = [], False
    for it in reversed(man["items"]):
        p = proj / it["path"]
        if not p.exists():
            out(f"{it['path']}: already absent")
            continue
        cur = sha(p.read_bytes())
        b = proj / it["backup"] if it.get("backup") else None
        if b is not None and b.exists() and cur == sha(b.read_bytes()):
            out(f"{it['path']}: already restored")
            continue
        if cur != it["sha256"]:
            err(f"REFUSED {it['path']}: changed since install (hash differs); left in place")
            left.append(it)
            refused = True
        elif it["origin"] == "created":
            p.unlink()
            out(f"{it['path']}: removed")
        elif b is not None:
            if not b.exists():
                err(f"REFUSED {it['path']}: backup {it['backup']} is missing")
                left.append(it)
                refused = True
                continue
            _atomic(p, b.read_bytes())
            out(f"{it['path']}: restored from {it['backup']}")
        else:
            out(f"{it['path']}: pre-existing and identical, left alone")
    if refused:
        man["items"] = list(reversed(left))
        _atomic(mp, (json.dumps(man, indent=2, sort_keys=True) + "\n").encode())
        return False
    mp.unlink()
    for d in (proj / ".claude" / "agents", proj / ".claude", proj / ".factory"):
        try:
            d.rmdir()
        except OSError:
            pass
    return True
