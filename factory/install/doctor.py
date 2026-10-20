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
from factory.agents.roles import DEFAULT_DIR, ROLE_IDS, RoleError, load_roles

from .core import (
    ENV_PIN, EXTERNAL_PINS, EXTERNAL_SKILLS, MANIFEST, MODEL, PROFILE, SETTINGS, hook_command_prefix, sha,
)

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


BUILTIN_SKILLS = ("claude-api",)


def _plugin_dirs(plugin: str) -> list[Path]:
    """Installed locations of `plugin`: installed_plugins.json install paths plus the cache."""
    base = Path.home() / ".claude" / "plugins"
    dirs = []
    try:
        for key, entries in json.loads((base / "installed_plugins.json").read_text(encoding="utf-8"))["plugins"].items():
            if key.split("@")[0] == plugin:
                dirs += [Path(e["installPath"]) for e in entries if isinstance(e, dict) and e.get("installPath")]
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return []  # unreadable registry: the skill is unresolved, so the check fails
    dirs += sorted(base.glob(f"cache/*/{plugin}/*"))
    return dirs


def _skill_resolves(name: str, root: Path, skills_dir: Path) -> str | None:
    """Where `name` resolves, or None."""
    if name in BUILTIN_SKILLS:
        return "built-in"
    plugin, sep, skill = name.partition(":")
    if sep:
        for d in _plugin_dirs(plugin):
            for f in (d / "skills" / skill / "SKILL.md", d / "commands" / f"{skill}.md", d / "workflows" / f"{skill}.js"):
                if f.is_file():
                    return str(f)
        return None
    for d in (root / "skills", skills_dir):
        if (d / name / "SKILL.md").is_file():
            return str(d / name)
    return None


def _role_dir(root: Path) -> Path:
    rdir = root / "factory" / "agents" / "roles"
    return rdir if rdir.is_dir() else DEFAULT_DIR


def _load_for_checks(root: Path):
    """The role specs for the hook and agent checks, or a FAIL detail. Model problems are reported
    by check_roles, so they are not allowed to stop the other checks; any other invalid role is."""
    rdir = _role_dir(root)
    models = {"sonnet"}
    for f in rdir.glob("*.yaml"):
        try:
            models.add(yaml.safe_load(f.read_text(encoding="utf-8"))["model"])
        except Exception:  # noqa: BLE001  load_roles below reports the unreadable file
            pass
    try:
        return load_roles(rdir, allow_models=[m for m in models if isinstance(m, str)]), None
    except (RoleError, OSError, UnicodeDecodeError) as e:
        return None, f"roles in {rdir} cannot be loaded: {e}"


def check_roles(root: Path, skills_dir: Path, allowed: set[str]) -> list[Check]:
    """Per role: the model must be allowed and every skill it names must resolve. Reads the role
    files raw so one bad role does not hide the others."""
    rdir = _role_dir(root)
    out: list[Check] = []
    for rid in ROLE_IDS:
        try:
            data = yaml.safe_load((rdir / f"{rid}.yaml").read_text(encoding="utf-8"))
            model, skills = data["model"], data["skills"]
            if not isinstance(skills, list):
                raise TypeError("skills is not a list")
        except Exception as e:  # noqa: BLE001
            out.append((f"role {rid} file", "FAIL", f"{rdir / (rid + '.yaml')} unreadable: {e}"))
            continue
        ok = model in allowed
        out.append((f"role {rid} model", "PASS" if ok else "FAIL",
                    str(model) if ok else f"{model!r} is not allowed (allowed: {sorted(allowed)}; set allow_models or --allow-model)"))
        for sk in skills:
            where = _skill_resolves(sk, root, skills_dir) if isinstance(sk, str) else None
            out.append((f"role {rid} skill {sk}", "PASS" if where else "FAIL",
                        where or f"role {rid} names skill {sk!r} which resolves in no repo skills dir, user skills dir or installed plugin"))
    return out


def check_external(root: Path, skills_dir: Path) -> list[Check]:
    pf = root / EXTERNAL_PINS
    try:
        skills = json.loads(pf.read_text(encoding="utf-8"))["skills"]
        if not isinstance(skills, dict):
            raise TypeError("skills is not an object")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [("external pins", "FAIL", f"{pf} unreadable or malformed ({e}); run `sf install pin-external --yes`")]
    out: list[Check] = []
    for name in dict.fromkeys([*EXTERNAL_SKILLS, *skills]):
        f = skills_dir / name / "SKILL.md"
        pin = skills.get(name)
        pinned = pin.get("sha256") if isinstance(pin, dict) else None
        if not isinstance(pinned, str):
            out.append((f"external {name}", "FAIL", f"not pinned in {EXTERNAL_PINS}"))
        elif not f.is_file():
            out.append((f"external {name}", "FAIL", f"{f} is missing"))
        elif sha(f.read_bytes()) != pinned:
            out.append((f"external {name}", "WARN", f"changed since pinned ({f})"))
        else:
            out.append((f"external {name}", "PASS", "matches pin"))
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


def _factory_commands(settings: dict) -> list[str]:
    """Every registered command that names factory.hooks (the only ones doctor reports on)."""
    found = []
    for entries in (settings.get("hooks") or {}).values():
        for e in entries if isinstance(entries, list) else []:
            for h in e.get("hooks", []) if isinstance(e, dict) else []:
                c = h.get("command") if isinstance(h, dict) else None
                if isinstance(c, str) and "factory.hooks" in c:
                    found.append(c)
    return found


def _exec_hook(root: Path, py: str, hid: str, payload: dict, cwd: str):
    """Run exactly [python, -m, factory.hooks, id]: no shell, trusted interpreter and root."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "FACTORY_PROFILE")}
    env["PYTHONPATH"] = str(root)
    return _run([py, "-m", "factory.hooks", hid], input=json.dumps({**payload, "cwd": cwd}), cwd=cwd, env=env, timeout=90)


def check_hooks(proj: Path, settings: dict, manifest: dict | None, root: Path, py: str) -> list[Check]:
    """Only the command the installer would generate (from TRUSTED root and python, never from the
    project's manifest or settings) is run; anything else naming factory.hooks is a FAIL, not run."""
    if manifest is not None and not manifest["options"]["hooks"]:
        return [("hooks registered", "SKIP", "installed with --no-hooks")]
    roles, err = _load_for_checks(root)
    if roles is None:
        return [("hooks registered", "FAIL", err)]
    needed = sorted({h for r in roles.values() for h in r.hooks}, key=list(HOOK_REGISTRATION).index)
    prefix = hook_command_prefix(root, py)
    expected = {h: f"{prefix} -m factory.hooks {h}" for h in needed}
    registered = _factory_commands(settings)
    missing = [h for h in needed if expected[h] not in registered]
    out: list[Check] = [("hooks registered", "FAIL" if missing else "PASS",
                         f"no command exactly equal to the installer's for: {', '.join(missing)}" if missing
                         else f"{len(needed)} hooks")]
    for c in registered:
        if c not in expected.values():
            out.append(("hook command", "FAIL", f"{c!r} is not a command this installer generates for "
                        f"python {py} and root {root}; NOT run"))
    prof = proj / PROFILE
    with tempfile.TemporaryDirectory(prefix="sf-doctor-") as tmp:  # hooks may write ledgers; keep it off the project
        if prof.is_file():
            (Path(tmp) / ".factory").mkdir()
            shutil.copy(prof, Path(tmp) / ".factory" / "profile.yaml")
        for hid in needed:
            if hid in missing:
                out.append((f"hook {hid} run", "FAIL", f"registered command does not match {expected[hid]!r}; not run"))
                if hid == "bash_guard":
                    out.append(("hook bash_guard deny", "FAIL", "bash_guard command not verified; not run"))
                continue
            event = "SubagentStop" if hid == "stop_gate" else HOOK_REGISTRATION[hid][0]
            payload = BENIGN if event == "PreToolUse" else _EVENT_PAYLOAD.get(event, {"hook_event_name": event})
            r = _exec_hook(root, py, hid, payload, tmp)
            rc = None if isinstance(r, Exception) else r.returncode
            ok = rc in ((0,) if event == "PreToolUse" else (0, 2))
            out.append((f"hook {hid} run", "PASS" if ok else "FAIL",
                        f"benign {event} payload exited {rc}" if ok else
                        f"did not run cleanly: {_fail_detail(r)}"))
            if hid == "bash_guard":
                d = _exec_hook(root, py, hid, DENY, tmp)
                drc = None if isinstance(d, Exception) else d.returncode
                out.append(("hook bash_guard deny", "PASS" if drc == 2 else "FAIL",
                            "`git add -A` as role implement exited 2" if drc == 2 else
                            f"deny payload expected exit 2, got {drc if drc is not None else _fail_detail(d)}"))
    return out


def check_agents(proj: Path, manifest: dict | None, allowed: set[str], root: Path | None = None) -> list[Check]:
    if manifest is not None and not manifest["options"]["agents"]:
        return [("agents", "SKIP", "installed with --no-agents")]
    roles, err = _load_for_checks(root or Path(__file__).resolve().parents[2])
    if roles is None:
        return [("agents", "FAIL", err)]
    out = []
    for role in roles:
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


def check_project(proj: Path, allowed: set[str], root: Path, py: str) -> tuple[list[Check], dict | None]:
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
    out += check_hooks(proj, settings, manifest, root, py)
    out += check_agents(proj, manifest, allowed, root)
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
    mine = [a for a in allow if isinstance(a, str) and ("factory." in a or (py and py in a))]
    out.append(("permissions", "FAIL" if mine else "PASS",
                f"allow entries that look installer-added: {mine}" if mine else "no installer-added permissions.allow"))
    return out, manifest


def _safe(label: str, fn, *args) -> list[Check]:
    """A check that raises is a FAIL line, never a traceback."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        return [(label, "FAIL", f"check could not run: {type(e).__name__}: {e}")]


def run_doctor(a) -> int:
    proj = Path(a.project).absolute() if a.project else None
    # trusted inputs only: the arguments and this checkout, never the project's manifest or settings
    root = Path(a.factory_root).resolve() if a.factory_root else Path(__file__).resolve().parents[2]
    py = os.path.abspath(a.python) if a.python else str(root / ".venv" / "bin" / "python")
    skills = Path(a.skills_dir) if a.skills_dir else Path.home() / ".claude" / "skills"
    allowed = {MODEL, *a.allow_model}
    checks = (_safe("tools", check_tools, py, root) + _safe("skills", check_skills, root, skills)
              + _safe("roles", check_roles, root, skills, allowed)
              + _safe("external pins", check_external, root, skills) + _safe("sf command", check_sf))
    if allowed - {MODEL} and not a.json:
        print(f"extra allowed models: {', '.join(sorted(allowed - {MODEL}))}")
    if proj:
        checks += _safe("project", lambda: check_project(proj, allowed, root, py)[0])
    failed = [c for c in checks if c[1] == "FAIL"]
    if a.json:
        print(json.dumps({"ok": not failed, "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks]}, indent=2))
    else:
        for n, s, d in checks:
            print(f"{s} {n}: {d}")
    return 1 if failed else 0
