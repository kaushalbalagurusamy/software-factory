"""Pytest plugin for the agent-layer evals: case marker, blocked accounting, results file."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

RESULTS = Path(__file__).parent / "results" / "latest.json"
_records: list[dict] = []


def pytest_configure(config):
    config.addinivalue_line("markers", "case(id, tier, tb, reqs): identify an eval case")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    marker = item.get_closest_marker("case")
    if marker is None or rep.when not in ("setup", "call"):
        return
    if rep.when == "setup" and rep.outcome != "skipped" and rep.outcome != "failed":
        return
    if rep.when == "call" and rep.outcome == "skipped" and any(r["nodeid"] == item.nodeid for r in _records):
        return
    if rep.outcome == "skipped":
        reason = str(rep.longrepr[2]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        status = "blocked" if "BLOCKED" in reason else "invalid_skip"
    else:
        status = rep.outcome  # passed or failed
    kw = marker.kwargs
    cid = marker.args[0] if marker.args else kw.get("id")
    _records.append({"nodeid": item.nodeid, "id": cid, "tier": kw.get("tier"), "tb": kw.get("tb"),
                     "reqs": kw.get("reqs", []), "status": status})


def pytest_sessionfinish(session, exitstatus):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(_records, indent=1))
