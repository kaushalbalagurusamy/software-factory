"""``doctor``: verify an install by running things, never by trusting files.

A hook command that cannot run exits non-2 and Claude Code treats that as a non-blocking error, so
a broken install fails OPEN. Hence every registered hook command is executed here with canned
payloads and the exit code is checked: a command that cannot run is a FAIL, never a PASS.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from factory.agents.generate import HOOK_REGISTRATION
from factory.agents.roles import load_roles

from .core import ENV_PIN, MANIFEST, MODEL, PROFILE, SETTINGS

BENIGN = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
          "agent_type": "implement", "agent_id": "doctor"}
DENY = {**BENIGN, "tool_input": {"command": "git add -A"}}
_EVENT_PAYLOAD = {"Stop": {"hook_event_name": "Stop", "last_assistant_message": "done"},
                  "SubagentStop": {"hook_event_name": "SubagentStop", "last_assistant_message": "done",
                                   "agent_type": "implement", "agent_id": "doctor"},
                  "SessionStart": {"hook_event_name": "SessionStart"}}
Check = tuple[str, str, str]  # name, PASS|FAIL|SKIP, detail


def _run(args, **kw):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=kw.pop("timeout", 60), **kw)
    except (OSError, subprocess.TimeoutExpired) as e:
        return e


def _fail_detail(r) -> str:
    if isinstance(r, Exception):
        return f"{type(r).__name__}: {r}"
    return f"exit {r.returncode}: {((r.stderr or r.stdout).strip().splitlines() or ['no output'])[-1]}"


def _load_skills_sync(root: Path):
    spec = importlib.util.spec_from_file_location("skills_sync", root / "scripts" / "skills_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_tools(py: str, root: Path) -> list[Check]:
    out = []
    env = dict(os.environ, PYTHONPATH=str(root))
    for label, stmt in (("factory importable", "import factory.hooks"), ("z3 importable", "import z3"),
                        ("yaml importable", "import yaml")):
        r = _run([py, "-c", stmt], env=env, timeout=120)
        ok = not isinstance(r, Exception) and r.returncode == 0
        out.append((label, "PASS" if ok else "FAIL", f"{py}" if ok else f"{py}: {_fail_detail(r)}"))
    return out


def check_skills(root: Path, skills_dir: Path) -> list[Check]:
    try:
        ss = _load_skills_sync(root)
        names = ss.skill_names(root / "skills")
    except Exception as e:  # noqa: BLE001
        return [("skills", "FAIL", f"cannot read the repo skills via scripts/skills_sync.py: {e}")]
    out = []
    for n in names:
        dst = skills_dir / n
        state = ss.classify(n, root / "skills", skills_dir)
        if state not in ("installed-is-link-to-repo", "identical"):
            out.append((f"skill {n}", "FAIL", f"{dst}: {state}"))
            continue
        problems = ss.check_skill_md(dst / "SKILL.md")
        out.append((f"skill {n}", "FAIL" if problems else "PASS", "; ".join(problems) or state))
    return out


def check_sf() -> list[Check]:
    sf = shutil.which("sf")
    if not sf:
        return [("sf command", "FAIL", "`sf` is not on PATH")]
    r = _run([sf, "--help"])
    if isinstance(r, Exception) or r.returncode != 0:
        return [("sf command", "FAIL", f"{sf} --help: {_fail_detail(r)}")]
    if "Software Factory" not in r.stdout:
        return [("sf command", "FAIL", f"{sf} is on PATH but is not the factory CLI (a different `sf`?)")]
    return [("sf command", "PASS", sf)]


def _hook_commands(settings: dict) -> dict[str, str]:
    found = {}
    for entries in (settings.get("hooks") or {}).values():
        for e in entries if isinstance(entries, list) else []:
            for h in e.get("hooks", []) if isinstance(e, dict) else []:
                c = h.get("command") if isinstance(h, dict) else None
                for hid in HOOK_REGISTRATION:
                    if isinstance(c, str) and c.endswith(f"-m factory.hooks {hid}"):
                        found.setdefault(hid, c)
    return found


def _exec_hook(cmd: str, payload: dict, cwd: str):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "FACTORY_PROFILE")}
    return _run(cmd, shell=True, input=json.dumps({**payload, "cwd": cwd}), cwd=cwd, env=env, timeout=90)


def check_hooks(proj: Path, settings: dict, manifest: dict | None) -> list[Check]:
    if manifest is not None and not manifest["options"]["hooks"]:
        return [("hooks registered", "SKIP", "installed with --no-hooks")]
    needed = sorted({h for r in load_roles().values() for h in r.hooks}, key=list(HOOK_REGISTRATION).index)
    cmds = _hook_commands(settings)
    missing = [h for h in needed if h not in cmds]
    out: list[Check] = [("hooks registered", "FAIL" if missing else "PASS",
                         f"missing: {', '.join(missing)}" if missing else f"{len(needed)} hooks")]
    prof = proj / PROFILE
    with tempfile.TemporaryDirectory(prefix="sf-doctor-") as tmp:  # hooks may write ledgers; keep it off the project
        if prof.is_file():
            (Path(tmp) / ".factory").mkdir()
            shutil.copy(prof, Path(tmp) / ".factory" / "profile.yaml")
        denied = None
        for hid in needed:
            if hid not in cmds:
                continue
            event = HOOK_REGISTRATION[hid][0]
            if hid == "stop_gate":
                event = "SubagentStop"
            payload = BENIGN if event == "PreToolUse" else _EVENT_PAYLOAD.get(event, {"hook_event_name": event})
            r = _exec_hook(cmds[hid], payload, tmp)
            rc = None if isinstance(r, Exception) else r.returncode
            want = (0,) if event == "PreToolUse" else (0, 2)
            ok = rc in want
            out.append((f"hook {hid} run", "PASS" if ok else "FAIL",
                        f"benign {event} payload exited {rc}" if ok else
                        f"{cmds[hid]!r} did not run cleanly: {_fail_detail(r)}"))
            if hid == "bash_guard":
                d = _exec_hook(cmds[hid], DENY, tmp)
                drc = None if isinstance(d, Exception) else d.returncode
                denied = drc == 2
                out.append(("hook bash_guard deny", "PASS" if denied else "FAIL",
                            "`git add -A` as role implement exited 2" if denied else
                            f"deny payload expected exit 2, got {drc if drc is not None else _fail_detail(d)}"))
        if "bash_guard" in needed and "bash_guard" not in cmds:
            out.append(("hook bash_guard deny", "FAIL", "bash_guard is not registered"))
    return out


def check_agents(proj: Path, manifest: dict | None, allowed: set[str]) -> list[Check]:
    if manifest is not None and not manifest["options"]["agents"]:
        return [("agents", "SKIP", "installed with --no-agents")]
    out = []
    for role in load_roles():
        p = proj / ".claude" / "agents" / f"{role}.md"
        if not p.is_file():
            out.append((f"agent {role}", "FAIL", f"{p} is missing"))
            continue
        try:
            model = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1]).get("model")
        except Exception as e:  # noqa: BLE001
            out.append((f"agent {role}", "FAIL", f"frontmatter unreadable: {e}"))
            continue
        ok = model in allowed
        out.append((f"agent {role}", "PASS" if ok else "FAIL",
                    f"model {model}" if ok else f"model {model!r} is not allowed (allowed: {sorted(allowed)}; use --allow-model)"))
    return out


def check_project(proj: Path, allowed: set[str]) -> tuple[list[Check], dict | None]:
    out: list[Check] = []
    manifest = None
    mp = proj / MANIFEST
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        out.append(("manifest", "FAIL", f"{mp} unreadable ({e}); run `python -m factory.install install`"))
    try:
        settings = json.loads((proj / SETTINGS).read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            raise ValueError("not a JSON object")
        out.append(("settings json", "PASS", str(proj / SETTINGS)))
    except (OSError, ValueError) as e:
        return out + [("settings json", "FAIL", f"{proj / SETTINGS}: {e}")], manifest
    m = settings.get("model")
    out.append(("model pin", "PASS" if m == MODEL else "FAIL", f"model={m!r}" if m == MODEL else f"model is {m!r}, expected {MODEL!r}"))
    env = settings.get("env") or {}
    bad = {k: env.get(k) for k, v in ENV_PIN.items() if env.get(k) != v}
    out.append(("env pin", "FAIL" if bad else "PASS", f"wrong or missing: {bad}" if bad else "subagent model forced to sonnet"))
    out += check_hooks(proj, settings, manifest)
    out += check_agents(proj, manifest, allowed)
    try:
        from factory.agents.profile import load_profile
        load_profile(proj / PROFILE)
        out.append(("profile", "PASS", str(proj / PROFILE)))
    except Exception as e:  # noqa: BLE001
        out.append(("profile", "FAIL", f"{proj / PROFILE}: {e}"))
    if manifest is not None:
        bad = []
        for it in manifest["items"]:
            p = proj / it["path"]
            if not it.get("tracked", True):
                continue
            if not p.is_file():
                bad.append(f"{it['path']} missing")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != it["sha256"]:
                bad.append(f"{it['path']} changed since install")
        out.append(("manifest hashes", "FAIL" if bad else "PASS", "; ".join(bad) or f"{len(manifest['items'])} items"))
    allow = (settings.get("permissions") or {}).get("allow") or []
    py = (manifest or {}).get("python", "")
    mine = [a for a in allow if isinstance(a, str) and ("factory." in a or (py and py in a))]
    out.append(("permissions", "FAIL" if mine else "PASS",
                f"allow entries that look installer-added: {mine}" if mine else "no installer-added permissions.allow"))
    return out, manifest


def run_doctor(a) -> int:
    proj = Path(a.project).absolute() if a.project else None
    manifest = None
    if proj and (proj / MANIFEST).is_file():
        try:
            manifest = json.loads((proj / MANIFEST).read_text(encoding="utf-8"))
        except ValueError:
            manifest = None
    root = Path(a.factory_root).resolve() if a.factory_root else Path(
        (manifest or {}).get("factory", {}).get("root") or Path(__file__).resolve().parents[2])
    py = os.path.abspath(a.python) if a.python else (manifest or {}).get("python") or str(root / ".venv/bin/python")
    skills = Path(a.skills_dir) if a.skills_dir else Path.home() / ".claude" / "skills"
    checks = check_tools(py, root) + check_skills(root, skills) + check_sf()
    if proj:
        pc, _ = check_project(proj, {MODEL, *a.allow_model})
        checks += pc
    failed = [c for c in checks if c[1] == "FAIL"]
    if a.json:
        print(json.dumps({"ok": not failed, "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks]}, indent=2))
    else:
        for n, s, d in checks:
            print(f"{s} {n}: {d}")
    return 1 if failed else 0
