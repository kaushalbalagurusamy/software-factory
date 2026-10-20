"""Shared adapter helpers. An adapter is a module with fetch(source: dict) -> dict returning
{"url", "status", "text", "fetched", "sha256"}; on failure "text" is None and "error" says why."""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "checks"))
import net  # noqa: E402

SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "br", "pre", "blockquote", "dd", "dt"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def result(url: str, status: int, text: str | None, error: str | None = None) -> dict:
    out = {"url": url, "status": status, "text": text, "fetched": date.today().isoformat()}
    if text is not None:
        out["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    if error:
        out["error"] = error
    return out


def fetch_html(url: str) -> dict:
    try:
        status, body = net.get(url, timeout=30, accept="text/html,application/xhtml+xml,text/plain")
    except Exception as exc:
        return result(url, 0, None, f"fetch failed: {exc}")
    if status != 200:
        return result(url, status, None, f"HTTP {status}")
    raw = body.decode("utf-8", errors="replace")
    text = raw if raw.lstrip()[:1] not in ("<",) else html_to_text(raw)
    return result(url, status, text)
