"""Runtime telemetry: 'as of now', never part of a snapshot, never changes with the commit selector.

Every figure is ``{"measured": true, "value", "source", "as_of", "label"}`` or ``{"measured": false, "reason",
"label": "unavailable"}``. Labels: live (fetched during this run), static (read from a file or config),
unavailable. Nothing is invented: absent config yields measured:false with the reason.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCHEMA = 1
FETCH_TIMEOUT = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def measured(value, source: str, label: str, as_of: str | None = None) -> dict:
    return {"measured": True, "value": value, "source": source, "as_of": as_of or now_iso(), "label": label}


def not_measured(reason: str) -> dict:
    return {"measured": False, "reason": reason, "label": "unavailable"}


def _fetch(url: str) -> tuple[int, float, bytes]:
    if not re.match(r"https?://", url):
        raise ValueError("only http(s) URLs are fetched")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:  # noqa: S310 - scheme checked above
            body = r.read(1_000_000)
            return r.status, (time.monotonic() - t0) * 1000, body
    except urllib.error.HTTPError as e:
        return e.code, (time.monotonic() - t0) * 1000, e.read(1_000_000)


def _dig(obj, path: str):
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def health(cfg: dict) -> dict:
    url = cfg.get("health_url")
    if not url:
        return not_measured("no health_url in config")
    try:
        code, ms, _ = _fetch(url)
    except Exception as e:  # unreachable is a measurement of failure, reported as such, with the reason
        return not_measured(f"health check could not reach {_origin(url)}: {type(e).__name__}")
    return measured({"http_status": code, "ok": 200 <= code < 400, "latency_ms": round(ms, 1)}, _origin(url), "live")


def _origin(url: str) -> str:
    """scheme://host[:port] only: never the path, query or userinfo, which may carry a secret."""
    m = re.match(r"(https?)://(?:[^/?#@]*@)?([^/?#]*)", url)
    return f"{m.group(1)}://{m.group(2)}" if m else "url"


def _version(spec, base: Path, what: str) -> dict:
    if not spec:
        return not_measured(f"no {what} in config")
    try:
        if "url" in spec:
            _, _, body = _fetch(spec["url"])
            data = json.loads(body)
            val = _dig(data, spec.get("json_path", "commit")) if spec.get("json_path", "commit") else data
            return measured(str(val)[:80], _origin(spec["url"]), "live")
        if "file" in spec:
            f = (base / spec["file"]).resolve()
            txt = f.read_text(encoding="utf-8").strip()
            val = _dig(json.loads(txt), spec["json_path"]) if spec.get("json_path") else txt.splitlines()[0]
            as_of = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            return measured(str(val)[:80], spec["file"], "static", as_of)
    except Exception as e:
        return not_measured(f"{what} unreadable: {type(e).__name__}")
    return not_measured(f"{what} needs a url or file")


def ci(cfg: dict) -> dict:
    spec = cfg.get("ci")
    if not spec:
        return not_measured("no ci in config")
    if not shutil.which("gh"):
        return not_measured("gh is not installed")
    cmd = ["gh", "run", "list", "--limit", "1", "--json", "status,conclusion,headSha,workflowName,createdAt,url"]
    if isinstance(spec, dict) and spec.get("repo"):
        cmd += ["--repo", spec["repo"]]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except Exception as e:
        return not_measured(f"gh run list failed: {type(e).__name__}")
    if p.returncode != 0:
        return not_measured("gh run list failed (not authenticated, or no repository)")
    try:
        runs = json.loads(p.stdout)
    except json.JSONDecodeError:
        return not_measured("gh run list returned unparseable output")
    if not runs:
        return not_measured("gh reports no CI runs")
    r = runs[0]
    return measured({k: r.get(k) for k in ("status", "conclusion", "headSha", "workflowName", "createdAt", "url")},
                    "gh run list", "live")


def test_summary(cfg: dict, base: Path) -> dict:
    spec = cfg.get("test_summary_file")
    if not spec:
        return not_measured("no test_summary_file in config")
    f = (base / spec).resolve()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        return not_measured(f"{spec} unreadable: {type(e).__name__}")
    as_of = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    return measured(data, spec, "static", as_of)


def langfuse(cfg: dict) -> dict:
    spec = cfg.get("langfuse") or {}
    if not spec.get("llm_features"):
        return {"applicable": False, "reason": "not applicable: the config declares no LLM features", "label": "unavailable"}
    host = spec.get("host")
    fig = measured({"configured": bool(host), "host": host}, "config", "static") if host else \
        not_measured("LLM features declared but no langfuse.host in config")
    return {"applicable": True, "configured": fig, "traces": not_measured("trace ingestion is not checked by this collector")}


def collect_runtime(config_path: Path | None) -> dict:
    cfg, base, note = {}, Path("."), None
    if config_path is not None and Path(config_path).exists():
        try:
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
            base = Path(config_path).parent.parent if Path(config_path).parent.name == "ops" else Path(config_path).parent
        except json.JSONDecodeError as e:
            note = f"config unreadable: {e}"
    else:
        note = "no config file; nothing is configured to measure"
    figs = {
        "app_health": health(cfg),
        "deployed_version": _version(cfg.get("deployed_version"), base, "deployed_version"),
        "expected_version": _version(cfg.get("expected_version"), base, "expected_version"),
        "ci_latest_run": ci(cfg),
        "last_test_summary": test_summary(cfg, base),
    }
    d, e = figs["deployed_version"], figs["expected_version"]
    figs["version_match"] = (
        measured(d["value"] == e["value"], "deployed_version vs expected_version", "live" if "live" in (d["label"], e["label"]) else "static")
        if d["measured"] and e["measured"] else not_measured("needs both deployed_version and expected_version"))
    return {"schema": SCHEMA, "kind": "runtime", "as_of": now_iso(), "note": note, "figures": figs,
            "langfuse": langfuse(cfg), "not_tied_to_commit": True}


def write_runtime(config_path: Path | None, out_path: Path) -> dict:
    data = collect_runtime(config_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, out_path)
    return data


# ---- serve ------------------------------------------------------------------------------------------------

def make_server(root: Path, host: str, port: int) -> ThreadingHTTPServer:
    """Static, read-only: GET/HEAD only, no directory listings, no endpoint runs a command."""
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def _root_redirect(self) -> bool:
            if self.path in ("", "/"):
                self.send_response(302)
                self.send_header("Location", "/shell/index.html")
                self.end_headers()
                return True
            return False

        def do_GET(self):
            if not self._root_redirect():
                super().do_GET()

        def do_HEAD(self):
            if not self._root_redirect():
                super().do_HEAD()

        def list_directory(self, path):
            self.send_error(404, "no directory listing")
            return None

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer((host, port), H)


def serve(root: Path, config_path: Path | None, host: str = "127.0.0.1", port: int = 8765, refresh_seconds: float = 30):
    out = root / "runtime.json"
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                write_runtime(config_path, out)
            except Exception as e:  # keep serving; the stale as_of tells the reader
                print(f"runtime refresh failed: {type(e).__name__}", flush=True)
            stop.wait(refresh_seconds)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    srv = make_server(root, host, port)
    print(f"serving {root} on http://{host}:{srv.server_address[1]}/ (runtime refresh {refresh_seconds}s)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        srv.server_close()
