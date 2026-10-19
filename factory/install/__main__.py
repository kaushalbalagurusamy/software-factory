"""python -m factory.install {install,uninstall,doctor}. Exit codes: 0 ok, 1 failure (install error,
refused uninstall, failed doctor check), 2 usage error."""
from __future__ import annotations

import argparse
import sys

from .core import InstallError, install, uninstall


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m factory.install", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--project", required=True)
    i.add_argument("--factory-root"); i.add_argument("--python"); i.add_argument("--profile")
    i.add_argument("--no-hooks", action="store_true"); i.add_argument("--no-agents", action="store_true")
    i.add_argument("--allow-model", action="append", default=[], metavar="NAME")
    i.add_argument("--dry-run", action="store_true")
    u = sub.add_parser("uninstall"); u.add_argument("--project", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--project"); d.add_argument("--skills-dir"); d.add_argument("--json", action="store_true")
    d.add_argument("--factory-root"); d.add_argument("--python")
    d.add_argument("--allow-model", action="append", default=[], metavar="NAME")
    return ap


def main(argv=None) -> int:
    try:
        a = build().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.cmd == "install":
            install(a.project, factory_root=a.factory_root, python=a.python, profile_src=a.profile,
                    hooks=not a.no_hooks, agents=not a.no_agents, allow_models=tuple(a.allow_model),
                    dry_run=a.dry_run)
            return 0
        if a.cmd == "uninstall":
            return 0 if uninstall(a.project) else 1
        from .doctor import run_doctor
        return run_doctor(a)
    except InstallError as e:
        print(f"install error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
