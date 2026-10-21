#!/usr/bin/env python3
"""Licence family for an SPDX id, a package, or a GitHub repository, read at sweep time.

Lenses name licence families, never vendors, because vendors relicense (a project's licence in
recall is not its licence today). The family decides the trap:

  permissive          MIT, BSD, Apache-2.0, ISC ...
  weak-copyleft       LGPL, MPL, EPL: file- or library-scoped reciprocity
  strong-copyleft     GPL: reciprocity on distribution
  network-copyleft    AGPL: reciprocity on network interaction with modified versions (AGPLv3 s.13)
  source-available    SSPL, BUSL, Elastic, FSL, Commons Clause: use restrictions, not open source
  non-commercial      CC-BY-NC*, PolyForm Noncommercial
  responsible-ai      OpenRAIL / model licences with use restrictions
  public-domain       CC0, Unlicense
  unknown             anything not mapped; treat as a finding to check by hand

CLI: python3 tools/checks/licence.py spdx AGPL-3.0-only
     python3 tools/checks/licence.py npm some-package
     python3 tools/checks/licence.py github owner/repo
"""
from __future__ import annotations

import json
import re
import sys

try:
    from . import net, registry
except ImportError:
    import net  # type: ignore
    import registry  # type: ignore

# Ordered: first matching prefix wins (AGPL before GPL, LGPL before GPL).
FAMILIES = [
    (r"^AGPL", "network-copyleft"),
    (r"^(LGPL|MPL|EPL|CDDL|EUPL|OSL|CPL)", "weak-copyleft"),
    (r"^GPL", "strong-copyleft"),
    (r"^(SSPL|BUSL|BSL-1\.1|Elastic|FSL|Commons-Clause|Confluent)", "source-available"),
    (r"^(CC-BY-NC|PolyForm-Noncommercial|CC-BY-NC-SA|CC-BY-NC-ND)", "non-commercial"),
    (r"(OpenRAIL|RAIL|Llama|Gemma)", "responsible-ai"),
    (r"^(CC0|Unlicense|0BSD|WTFPL)", "public-domain"),
    (r"^(MIT|BSD|Apache|ISC|Zlib|BSL-1\.0|PSF|Python|CC-BY-4|CC-BY-3|UPL|Artistic|PostgreSQL|NCSA|X11)", "permissive"),
]

ALIASES = {
    "apache 2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "mit license": "MIT", "bsd": "BSD-3-Clause", "gplv3": "GPL-3.0", "gplv2": "GPL-2.0",
    "agplv3": "AGPL-3.0", "lgplv3": "LGPL-3.0", "server side public license": "SSPL-1.0",
    "business source license 1.1": "BUSL-1.1",
}


def family(spdx: str | None) -> dict:
    if not spdx:
        return {"spdx": spdx, "family": "unknown", "note": "no licence declared: all rights reserved by default"}
    norm = ALIASES.get(spdx.strip().lower(), spdx.strip())
    parts = re.split(r"\s+(?:OR|AND|WITH)\s+", norm.strip("() "))
    fams = []
    for p in parts:
        for pat, fam in FAMILIES:
            if re.search(pat, p, re.IGNORECASE):
                fams.append(fam)
                break
        else:
            fams.append("unknown")
    out = {"spdx": norm, "family": fams[0] if len(set(fams)) == 1 else "mixed", "parts": dict(zip(parts, fams))}
    if " OR " in norm:
        out["note"] = "dual-licensed: the user may choose; record which option the project takes"
    return out


def spdx(identifier: str) -> dict:
    out = family(identifier)
    try:
        status, doc = net.get_json(f"https://spdx.org/licenses/{identifier}.json")
        out["spdx_listed"] = status == 200 if status in (200, 404) else None
        if doc:
            out["osi_approved"] = doc.get("isOsiApproved")
            out["deprecated"] = doc.get("isDeprecatedLicenseId")
    except Exception as exc:
        out["spdx_listed"], out["error"] = None, f"SPDX lookup failed: {exc}"
    return out


def package(ecosystem: str, name: str) -> dict:
    meta = registry.lookup(ecosystem, name)
    return {"package": f"{ecosystem}:{name}", "exists": meta.get("exists"), "declared": meta.get("license"), **family(meta.get("license"))}


def github(repo: str) -> dict:
    try:
        status, doc = net.get_json(f"https://api.github.com/repos/{repo}/license")
    except Exception as exc:
        return {"repo": repo, "family": None, "error": str(exc)}
    if status == 404:
        return {"repo": repo, **family(None), "note": "no LICENSE file detected by GitHub"}
    if doc is None:
        return {"repo": repo, "family": None, "error": f"HTTP {status}"}
    sid = (doc.get("license") or {}).get("spdx_id")
    if sid in (None, "NOASSERTION"):
        return {"repo": repo, "declared": sid, "spdx": None, "family": "unknown",
                "note": "a licence file exists but GitHub could not classify it (often multi-licence); read "
                        + (doc.get("html_url") or "the LICENSE file") + " by hand"}
    return {"repo": repo, "declared": sid, **family(sid)}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: licence.py spdx|npm|pypi|github <id>", file=sys.stderr)
        return 2
    kind, ident = argv[0], argv[1]
    if kind == "spdx":
        r = spdx(ident)
    elif kind in ("npm", "pypi"):
        r = package(kind, ident)
    elif kind == "github":
        r = github(ident)
    else:
        print("kind must be spdx, npm, pypi or github", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
