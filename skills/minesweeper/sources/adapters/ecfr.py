"""US Code of Federal Regulations via eCFR. url: an ecfr.gov section or part page, e.g.
https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.312
The renderer API returns the current text as HTML."""
import re

from _base import fetch_html, result


def fetch(source: dict) -> dict:
    url = source["url"]
    m = re.search(r"ecfr\.gov/current/(title-\d+.*)$", url)
    if not m:
        return fetch_html(url)
    api = f"https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/{m.group(1).split('/')[0].replace('title-', '')}"
    parts = dict(re.findall(r"(part|section|subpart)-([\w.]+)", m.group(1)))
    q = "&".join(f"{k}={v}" for k, v in parts.items())
    out = fetch_html(api + ("?" + q if q else ""))
    if out.get("text") is None:
        out = fetch_html(url)  # fall back to the public page
    return out if out.get("text") else result(url, out.get("status", 0), None, out.get("error"))
