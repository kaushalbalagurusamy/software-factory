"""SPDX licence list entries. url: https://spdx.org/licenses/<ID>.html (the .json twin is read)."""
import json
import re

from _base import result
import net  # noqa: E402  (path set by _base)


def fetch(source: dict) -> dict:
    m = re.search(r"/licenses/([^/]+?)(?:\.html|\.json)?$", source["url"])
    if not m:
        return result(source["url"], 0, None, "url is not an SPDX licence page")
    url = f"https://spdx.org/licenses/{m.group(1)}.json"
    try:
        status, doc = net.get_json(url, timeout=30)
    except Exception as exc:
        return result(url, 0, None, f"fetch failed: {exc}")
    if doc is None:
        return result(url, status, None, f"HTTP {status}")
    head = f"{doc.get('name')} ({doc.get('licenseId')}); OSI approved: {doc.get('isOsiApproved')}\n\n"
    return result(url, status, head + (doc.get("licenseText") or ""))
