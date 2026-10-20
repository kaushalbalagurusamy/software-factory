"""Open Source Vulnerabilities records. url: https://osv.dev/vulnerability/<ID> (GHSA, CVE, PYSEC ...)."""
import json
import re

from _base import result
import net  # noqa: E402  (path set by _base)


def fetch(source: dict) -> dict:
    m = re.search(r"/vulnerability/([^/?#]+)", source["url"])
    if not m:
        return result(source["url"], 0, None, "url is not an osv.dev vulnerability page")
    url = f"https://api.osv.dev/v1/vulns/{m.group(1)}"
    try:
        status, doc = net.get_json(url, timeout=30)
    except Exception as exc:
        return result(url, 0, None, f"fetch failed: {exc}")
    if doc is None:
        return result(url, status, None, f"HTTP {status} (an unknown id is a finding: the advisory may not exist)")
    text = "\n\n".join(str(x) for x in [doc.get("id"), doc.get("summary"), doc.get("details"), json.dumps(doc.get("affected", []))[:4000]] if x)
    return result(url, status, text)
