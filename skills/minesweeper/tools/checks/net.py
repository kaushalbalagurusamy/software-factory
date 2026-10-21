"""Minimal read-only HTTP for checks and adapters. GET/POST JSON or text; never downloads packages."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

UA = "minesweeper-skill/0.1 (read-only metadata check)"


def get(url: str, timeout: float = 20.0, accept: str = "*/*") -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


def get_json(url: str, timeout: float = 20.0):
    status, body = get(url, timeout, "application/json")
    if status != 200:
        return status, None
    return status, json.loads(body)


def post_json(url: str, payload: dict, timeout: float = 20.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
