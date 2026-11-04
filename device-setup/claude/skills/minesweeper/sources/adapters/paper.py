"""Papers. arXiv abs pages are read directly; DOIs resolve through doi.org to the publisher page."""
from _base import fetch_html


def fetch(source: dict) -> dict:
    url = source["url"]
    if "arxiv.org/pdf/" in url:
        url = url.replace("/pdf/", "/abs/").removesuffix(".pdf")
    return fetch_html(url)
