"""Scripted fake-implementer simulation of the whole supervisor loop (no model is called)."""
import pytest

from factory.qa.decide import decide_next
from factory.qa.policy import load_policy
from factory.qa.runs import record_run
from factory.qa.store import SliceStore


class FakeImplementer:
    """Stands in for the agent: a script of gate results, one per attempt."""

    def __init__(self, script):
        self.script = list(script)
        self.tiers_used = []

    def attempt(self, tier):
        self.tiers_used.append(tier)
        return self.script.pop(0)


def run_slice(store, pol, impl, max_steps=60):
    """Drive one slice until accept or mark_blocked. Returns the action trace."""
    trace, last_result = [], None
    for _ in range(max_steps):
        d = decide_next(store, pol, apply=True)
        trace.append(d["action"])
        a = d["action"]
        if a in ("accept", "mark_blocked"):
            return trace
        if a == "propose_regression":
            store.note_proposal(d["signature"], f"regression-proposals/{d['signature']}.md")
        elif a == "hand_to_reviewer":
            store.set_reviewer_verdict(d["signature"], "unresolved", "needs spec decision on AC-1")
        elif a == "environment_wait":
            result = impl.attempt("-")
            record_run(store, pol, status=result[0], case="AC-1", error=result[1], tier="sonnet")
        elif a == "rerun_for_flake":
            result = impl.attempt(d["tier"])
            record_run(store, pol, status=result[0], case="AC-1", error=result[1], tier=d["tier"], rerun=True)
        else:  # retry_same_tier / escalate_model
            result = impl.attempt(d["tier"])
            record_run(store, pol, status=result[0], case="AC-1", error=result[1], tier=d["tier"])
    raise AssertionError(f"no convergence: {trace}")


FAIL = ("fail", "AssertionError: expected 401 got 500")


def slice_(tmp_path, name, flake=0, ladder=None):
    if ladder:  # explicit opt-in for non-default models
        (tmp_path / ".sf").mkdir(exist_ok=True)
        extra = sorted(set(ladder) - {"sonnet"})
        (tmp_path / ".sf" / "policy.yaml").write_text(f"tiers: {ladder}\nallow_non_default_models: {extra}\n".replace("'", ""))
    st = SliceStore(tmp_path, name)
    st.init(["AC-1"])
    pol = load_policy(tmp_path)
    object.__setattr__(pol, "flake_reruns", flake)
    return st, pol


def test_failure_then_fix_passes(tmp_path):
    st, pol = slice_(tmp_path, "a")
    impl = FakeImplementer([FAIL, ("pass", "")])
    trace = run_slice(st, pol, impl)
    assert trace[-1] == "accept" and impl.tiers_used == ["sonnet", "sonnet"]
    assert st.audit() == []


def test_recurring_signature_triggers_regression_proposal(tmp_path):
    st, pol = slice_(tmp_path, "a")
    impl = FakeImplementer([FAIL, ("fail", "AssertionError: expected 401 got 502"), ("pass", "")])
    trace = run_slice(st, pol, impl)
    assert "propose_regression" in trace and trace[-1] == "accept"


def test_cap_escalates_then_reviewer_then_blocked_and_run_proceeds(tmp_path):
    a, pol = slice_(tmp_path, "stuck", ladder=["sonnet", "sonnet", "opus", "opus"])
    b, _ = slice_(tmp_path, "independent")
    impl_a = FakeImplementer([FAIL] * 4)
    trace_a = run_slice(a, pol, impl_a)
    assert impl_a.tiers_used == ["sonnet", "sonnet", "opus", "opus"]
    assert "escalate_model" in trace_a
    assert trace_a[-3:] == ["hand_to_reviewer", "mark_blocked"][-3:] or trace_a[-2:] == ["hand_to_reviewer", "mark_blocked"]
    assert a.state["status"] == "blocked" and "AC-1" in a.state["waits_on"]
    # the simulated run proceeds to the next independent slice
    trace_b = run_slice(b, pol, FakeImplementer([("pass", "")]))
    assert trace_b[-1] == "accept" and b.state["status"] != "blocked"


def test_flaky_failure_passes_on_rerun_and_is_not_counted(tmp_path):
    st, pol = slice_(tmp_path, "f", flake=1)
    impl = FakeImplementer([FAIL, ("pass", "")])
    trace = run_slice(st, pol, impl)
    assert trace == ["retry_same_tier", "rerun_for_flake", "accept"]
    assert st.facts()["counted"] == 0 and st.facts()["flakes"] == 1


def test_environment_crash_consumes_no_attempt_and_gate_stays_failed(tmp_path):
    st, pol = slice_(tmp_path, "e")
    impl = FakeImplementer([("fail", "ENOSPC: no space left on device"), ("fail", "Address already in use"),
                            ("pass", "")])
    trace = run_slice(st, pol, impl)
    assert trace == ["retry_same_tier", "environment_wait", "environment_wait", "accept"]
    f = st.facts()
    assert f["counted"] == 1 and f["env_runs"] == 2
    assert st.audit() == []
