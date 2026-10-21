"""Any HTML or plain-text page: terms of service, documentation, guidance, standards landing pages."""
from _base import fetch_html


def fetch(source: dict) -> dict:
    return fetch_html(source["url"])
