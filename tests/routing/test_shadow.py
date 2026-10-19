"""Unit coverage for the shadow routing log (TB-14). Not the acceptance gate."""
from __future__ import annotations

import json
from types import SimpleNamespace

from factory.routing import shadow
from factory.routing.jev_client import Routing, log_record


def routing(choice="opus", **kw):
    base = dict(decision="model_tier", choice=choice, action="use_opus", source="jev", band="act",
                policy_version="v1", top_prob=0.9, margin=0.5,
                probabilities={"opus": 0.9, "sonnet": 0.1}, latency_ms=12.0)
    base.update(kw)
    return Routing(**base)


def lines(d):
    return [json.loads(x) for x in (d / "routing.jsonl").read_text().splitlines()]


def test_appends_content_free_record_plus_agreement(tmp_path):
    r = routing()
    assert shadow.record(r, "opus", tmp_path, state_digest="abc") is None
    assert shadow.record(r, "sonnet", tmp_path) is None
    got = lines(tmp_path)
    assert got[0] == {**log_record(r, "abc"), "actual_choice": "opus", "agrees": True}
    assert got[1] == {**log_record(r, ""), "actual_choice": "sonnet", "agrees": False}


def test_creates_missing_ledger_dir(tmp_path):
    d = tmp_path / "a" / "b"
    shadow.record(routing(), "opus", d)
    assert len(lines(d)) == 1


def test_fault_result_is_logged(tmp_path):
    r = routing(choice="unknown", source="fallback", band="fault", top_prob=None, margin=None,
                probabilities={}, fault="timeout")
    shadow.record(r, "sonnet", str(tmp_path))
    assert lines(tmp_path)[0]["fault"] == "timeout"
    assert lines(tmp_path)[0]["agrees"] is False


def test_duck_typed_result(tmp_path):
    r = SimpleNamespace(**{f: getattr(routing(), f) for f in (
        "decision", "choice", "action", "source", "band", "policy_version", "top_prob", "margin",
        "probabilities", "fault", "latency_ms")})
    shadow.record(r, "opus", tmp_path)
    assert lines(tmp_path)[0]["agrees"] is True


def test_never_raises(tmp_path):
    shadow.record(object(), "opus", tmp_path)            # missing attributes
    shadow.record(None, "opus", tmp_path)
    shadow.record(routing(top_prob=float("nan")), "opus", tmp_path)  # not valid JSON
    blocker = tmp_path / "file"
    blocker.write_text("")
    shadow.record(routing(), "opus", blocker)            # ledger_dir is a file
    shadow.record(routing(), "opus", None)
    assert not (tmp_path / "routing.jsonl").exists()


def test_record_does_not_change_the_result(tmp_path):
    r = routing()
    before = (r.choice, r.action)
    shadow.record(r, "sonnet", tmp_path)
    assert (r.choice, r.action) == before
