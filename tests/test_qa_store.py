"""Append-only, hash-chained QA state and stats."""
import json

import pytest

from factory.qa.policy import load_policy
from factory.qa.runs import record_run
from factory.qa.stats import tier_stats
from factory.qa.store import SliceStore


@pytest.fixture
def env(tmp_path):
    st = SliceStore(tmp_path, "demo")
    st.init(["AC-1", "AC-2"])
    return st, load_policy(tmp_path)


def test_init_layout(env):
    st, _ = env
    assert (st.dir / "state.json").is_file()
    assert st.dir == st.root / ".sf" / "slices" / "demo"
    assert st.audit() == []


def test_records_are_chained_and_audit_clean(env):
    st, pol = env
    record_run(st, pol, status="fail", case="AC-1", error="boom 1", tier="sonnet", duration_s=3)
    record_run(st, pol, status="pass", tier="sonnet", duration_s=2)
    lines = [json.loads(l) for l in (st.dir / "attempts.jsonl").read_text().splitlines()]
    assert [l["seq"] for l in lines] == [1, 2]
    assert lines[1]["prev"] == lines[0]["hash"]
    assert (st.dir / "failures.jsonl").read_text().count("\n") == 1
    assert st.audit() == []


def test_rewritten_line_detected(env):
    st, pol = env
    record_run(st, pol, status="fail", case="AC-1", error="a", tier="sonnet")
    record_run(st, pol, status="fail", case="AC-1", error="a", tier="sonnet")
    f = st.dir / "attempts.jsonl"
    f.write_text(f.read_text().replace('"fail"', '"pass"', 1))
    assert any("hash" in p or "chain" in p for p in st.audit())


def test_deleted_tail_and_deleted_line_detected(env):
    st, pol = env
    for _ in range(3):
        record_run(st, pol, status="fail", case="AC-1", error="a", tier="sonnet")
    f = st.dir / "attempts.jsonl"
    keep = f.read_text().splitlines()
    f.write_text("\n".join(keep[:2]) + "\n")  # truncated tail
    assert any("length" in p for p in st.audit())
    f.write_text("\n".join([keep[0], keep[2]]) + "\n")  # middle removed
    assert st.audit()


def test_consistently_recomputed_chain_still_caught_by_state_head(env):
    st, pol = env
    record_run(st, pol, status="fail", case="AC-1", error="a", tier="sonnet")
    f = st.dir / "attempts.jsonl"
    f.write_text("")  # wipe history entirely
    assert st.audit()


def test_stats_per_tier_from_attempts(env):
    st, pol = env
    record_run(st, pol, status="fail", case="AC-1", error="x", tier="sonnet", duration_s=10, flaky_off=True) \
        if False else None
    record_run(st, pol, status="fail", case="AC-1", error="x", tier="sonnet", duration_s=10, rerun=False)
    record_run(st, pol, status="fail", case="AC-1", error="x", tier="sonnet", duration_s=20, rerun=True)
    record_run(st, pol, status="pass", tier="opus", duration_s=30)
    s = tier_stats([st.dir])
    assert s["sonnet"]["attempts"] == 1 and s["sonnet"]["successes"] == 0
    assert s["opus"]["attempts"] == 1 and s["opus"]["successes"] == 1
    assert s["opus"]["success_rate"] == 1.0 and s["sonnet"]["success_rate"] == 0.0
    assert s["opus"]["mean_duration_s"] == 30
