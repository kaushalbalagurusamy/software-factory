#!/usr/bin/env python3
"""Package registry metadata for npm and PyPI. Reads metadata only; never installs or downloads code.

Answers the questions a supply-chain trap needs: does the name exist (hallucinated or slopsquatted
names do not, or exist only as a fresh upload), how old is it, how many maintainers, what licence
does it declare, and does the same name exist on the other registry.

A failed read is reported as `None` with an `error`, never as zero or "does not exist": only a
404 from the registry means the package is absent.

CLI: python3 tools/checks/registry.py npm left-pad
     python3 tools/checks/registry.py pypi requests
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import datetime, timezone

try:
    from . import net
except ImportError:  # run as a script
    import net  # type: ignore

NPM = "https://registry.npmjs.org/"
NPM_DL = "https://api.npmjs.org/downloads/point/last-week/"
PYPI = "https://pypi.org/pypi/{}/json"


def _age_days(iso: str | None):
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def npm(name: str) -> dict:
    out = {"ecosystem": "npm", "name": name}
    try:
        status, doc = net.get_json(NPM + urllib.parse.quote(name, safe="@"))
    except Exception as exc:
        return {**out, "exists": None, "error": f"lookup failed: {exc}"}
    if status == 404:
        return {**out, "exists": False}
    if doc is None:
        return {**out, "exists": None, "error": f"HTTP {status}"}
    t = doc.get("time", {})
    latest = doc.get("dist-tags", {}).get("latest")
    lic = doc.get("license")
    if isinstance(lic, dict):
        lic = lic.get("type")
    repo = doc.get("repository")
    out.update({
        "exists": True,
        "created": t.get("created"),
        "age_days": _age_days(t.get("created")),
        "modified": t.get("modified"),
        "latest": latest,
        "versions": len(doc.get("versions", {})),
        "maintainers": len(doc.get("maintainers", []) or []),
        "license": lic,
        "repository": repo.get("url") if isinstance(repo, dict) else repo,
        "deprecated": bool((doc.get("versions", {}).get(latest) or {}).get("deprecated")) if latest else None,
    })
    try:
        s, dl = net.get_json(NPM_DL + urllib.parse.quote(name, safe="@"))
        out["weekly_downloads"] = dl.get("downloads") if dl else None
    except Exception:
        out["weekly_downloads"] = None
    return out


def pypi(name: str) -> dict:
    out = {"ecosystem": "pypi", "name": name}
    try:
        status, doc = net.get_json(PYPI.format(urllib.parse.quote(name)))
    except Exception as exc:
        return {**out, "exists": None, "error": f"lookup failed: {exc}"}
    if status == 404:
        return {**out, "exists": False}
    if doc is None:
        return {**out, "exists": None, "error": f"HTTP {status}"}
    info = doc.get("info", {})
    uploads = [f.get("upload_time_iso_8601") for files in doc.get("releases", {}).values() for f in files if f.get("upload_time_iso_8601")]
    first = min(uploads) if uploads else None
    out.update({
        "exists": True,
        "created": first,
        "age_days": _age_days(first),
        "latest": info.get("version"),
        "versions": len(doc.get("releases", {})),
        "license": info.get("license_expression") or info.get("license") or None,
        "classifiers_licence": [c for c in info.get("classifiers", []) if c.startswith("License ::")],
        "repository": (info.get("project_urls") or {}).get("Source") or info.get("home_page"),
        "yanked_latest": any(f.get("yanked") for f in doc.get("releases", {}).get(info.get("version"), [])),
    })
    return out


def lookup(ecosystem: str, name: str) -> dict:
    if ecosystem == "npm":
        return npm(name)
    if ecosystem in ("pypi", "pip", "python"):
        return pypi(name)
    raise ValueError("ecosystem must be npm or pypi")


def exists(ecosystem: str, name: str) -> dict:
    r = lookup(ecosystem, name)
    return {k: r.get(k) for k in ("ecosystem", "name", "exists", "error") if k in r}


def age(ecosystem: str, name: str) -> dict:
    r = lookup(ecosystem, name)
    return {k: r.get(k) for k in ("ecosystem", "name", "exists", "created", "age_days", "maintainers", "weekly_downloads", "error") if k in r}


def cross_registry(ecosystem: str, name: str) -> dict:
    """The same name on the other registry: a common confusion and squatting vector."""
    other = "pypi" if ecosystem == "npm" else "npm"
    return {"asked": lookup(ecosystem, name), "other": lookup(other, name)}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-2:], file=sys.stderr)
        return 2
    eco, name = argv[0], argv[1]
    mode = argv[2] if len(argv) > 2 else "lookup"
    fn = {"lookup": lookup, "exists": exists, "age": age, "cross": cross_registry}[mode]
    print(json.dumps(fn(eco, name), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
