"""The pure `decide` function and the state transitions that feed it."""
import copy

import pytest

from factory.qa.decide import decide, decide_next
from factory.qa.policy import load_policy
from factory.qa.runs import record_run
from factory.qa.store import SliceStore


@pytest.fixture
def env(tmp_path):
    st = SliceStore(tmp_path, "s1")
    st.init(["AC-1"])
    return st, load_policy(tmp_path)


def fail(st, pol, err="AssertionError: wrong status 500", **kw):
    kw.setdefault("tier", "sonnet")
    return record_run(st, pol, status="fail", case="AC-1", error=err, **kw)


def nxt(st, pol, **kw):
    return decide_next(st, pol, **kw)


def test_first_attempt_is_retry_same_tier(env):
    st, pol = env
    d = nxt(st, pol)
    assert d["action"] == "retry_same_tier" and d["tier"] == "sonnet"


def test_pass_accepts_when_all_criteria_verified(env):
    st, pol = env
    record_run(st, pol, status="pass", tier="sonnet")
    assert nxt(st, pol)["action"] == "accept"


def test_partial_verification_does_not_accept(env):
    st, pol = env
    st.init(["AC-1", "AC-2"], force=True)
    record_run(st, pol, status="pass", tier="sonnet", verified=["AC-1"])
    d = nxt(st, pol)
    assert d["action"] == "retry_same_tier" and "AC-2" in d["reason"]


def test_failure_then_retry_same_tier_then_escalate_then_reviewer(env):
    st, pol = env
    fail(st, pol, rerun=False)          # suspect
    assert nxt(st, pol)["action"] == "rerun_for_flake"
    fail(st, pol, rerun=True)           # confirmed attempt 1
    d = nxt(st, pol)
    assert d["action"] == "propose_regression" if False else True
    assert d["action"] == "retry_same_tier" and d["tier"] == "sonnet"
    for _ in range(2):  # attempts 2 and 3 (each needs its confirming rerun)
        fail(st, pol); fail(st, pol, rerun=True)
        d = nxt(st, pol)
        if d["action"] == "propose_regression":
            st.note_proposal(d["signature"], "regression-proposals/x.md")
            d = nxt(st, pol)
    assert d["action"] == "escalate_model" and d["tier"] == "opus"
    fail(st, pol, tier="opus"); fail(st, pol, tier="opus", rerun=True)
    d = nxt(st, pol)
    assert d["action"] == "hand_to_reviewer"


def test_same_signature_recurring_proposes_regression_once(env):
    st, pol = env
    pol = load_policy(st.root)
    object.__setattr__(pol, "flake_reruns", 0)
    fail(st, pol, err="AssertionError: wrong status 500 at /tmp/a/x.py:10")
    assert nxt(st, pol)["action"] == "retry_same_tier"
    fail(st, pol, err="AssertionError: wrong status 503 at /var/b/x.py:99")
    d = nxt(st, pol)
    assert d["action"] == "propose_regression" and d["criterion"] == "AC-1"
    st.note_proposal(d["signature"], "p.md")
    assert nxt(st, pol)["action"] in ("retry_same_tier", "escalate_model")


def test_reviewer_unresolved_then_blocked_with_waits_on(env):
    st, pol = env
    object.__setattr__(pol, "flake_reruns", 0)
    for _ in range(4):
        d = nxt(st, pol)
        if d["action"] == "propose_regression":
            st.note_proposal(d["signature"], "p.md")
        fail(st, pol)
    d = nxt(st, pol)
    assert d["action"] == "hand_to_reviewer"
    st.set_reviewer_verdict(d["signature"], "unresolved", "AC-1 contract ambiguous")
    d = nxt(st, pol, apply=True)
    assert d["action"] == "mark_blocked" and "AC-1 contract ambiguous" in d["waits_on"]
    assert st.state["status"] == "blocked" and "AC-1 contract ambiguous" in st.state["waits_on"]
    assert nxt(st, pol)["action"] == "mark_blocked"


def test_reviewer_amendment_grants_fresh_budget_but_keeps_history(env):
    st, pol = env
    object.__setattr__(pol, "flake_reruns", 0)
    for _ in range(4):
        d = nxt(st, pol)
        if d["action"] == "propose_regression":
            st.note_proposal(d["signature"], "p.md")
        fail(st, pol)
    sig = nxt(st, pol)["signature"]
    st.set_reviewer_verdict(sig, "amended", "added AC-1.3")
    assert nxt(st, pol)["action"] in ("retry_same_tier", "escalate_model")
    assert len((st.dir / "attempts.jsonl").read_text().splitlines()) == 4


def test_environment_run_waits_and_does_not_consume_attempt(env):
    st, pol = env
    line = record_run(st, pol, status="fail", case="AC-1", error="OSError: ENOSPC no space left on device", tier="sonnet")
    assert line["outcome"] == "environment"
    d = nxt(st, pol)
    assert d["action"] == "environment_wait"
    assert st.facts()["counted"] == 0 and st.facts()["gate"] == "failed"
    record_run(st, pol, status="pass", tier="sonnet")
    assert st.facts()["gate"] == "passed" and nxt(st, pol)["action"] == "accept"


def test_environment_wait_bounded_then_blocked(env):
    st, pol = env
    for _ in range(pol.env_wait_max + 1):
        record_run(st, pol, status="fail", case="AC-1", error="Killed by signal 9", tier="sonnet")
    d = nxt(st, pol)
    assert d["action"] == "mark_blocked" and "environment" in d["waits_on"]


def test_flake_passes_on_rerun_and_is_not_an_attempt(env):
    st, pol = env
    s = fail(st, pol)
    assert s["outcome"] == "suspect"
    assert nxt(st, pol)["action"] == "rerun_for_flake"
    p = record_run(st, pol, status="pass", tier="sonnet", rerun=True)
    assert p["outcome"] == "flake"
    f = st.facts()
    assert f["counted"] == 0 and f["flakes"] == 1
    assert nxt(st, pol)["action"] == "accept"


def test_rerun_without_pending_suspect_rejected(env):
    st, pol = env
    with pytest.raises(ValueError):
        record_run(st, pol, status="pass", tier="sonnet", rerun=True)


def test_slice_cap_and_budget_hand_to_reviewer(env):
    st, pol = env
    object.__setattr__(pol, "flake_reruns", 0)
    object.__setattr__(pol, "budget_tokens", 100)
    fail(st, pol, tokens=150)
    d = nxt(st, pol)
    assert d["action"] == "hand_to_reviewer" and "budget" in d["reason"]


def test_decide_is_pure_and_deterministic(env):
    st, pol = env
    fail(st, pol); fail(st, pol, rerun=True)
    facts, state = st.facts(), st.state
    f0, s0 = copy.deepcopy(facts), copy.deepcopy(state)
    a = decide(facts, state, pol, {})
    b = decide(facts, state, pol, {})
    assert a == b and facts == f0 and state == s0


def test_measured_escalation_early_when_tier_performs_badly(env):
    st, pol = env
    object.__setattr__(pol, "flake_reruns", 0)
    fail(st, pol)
    bad = {"sonnet": {"attempts": 10, "successes": 0, "success_rate": 0.0}}
    d = decide(st.facts(), st.state, pol, bad)
    assert d["action"] == "escalate_model" and d["tier"] == "opus" and "0/10" in d["reason"]
    good = {"sonnet": {"attempts": 10, "successes": 9, "success_rate": 0.9}}
    for _ in range(2):
        fail(st, pol)
    d = decide(st.facts(), st.state, pol, good)
    assert d["action"] == "retry_same_tier" and d["tier"] == "sonnet"
    assert decide(st.facts(), st.state, pol, {})["action"] == "escalate_model"
