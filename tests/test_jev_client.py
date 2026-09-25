"""
Tests for the Jev routing client. Recorded responses only: no test makes a live call.
"""

import json
from pathlib import Path

import pytest

from factory.routing import jev_client
from factory.routing.jev_client import JevFault, build_request, load_policy, log_record, parse_answer, route

FIXTURES = Path(__file__).parent / "fixtures" / "jev"


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def recorded(name):
    """A transport that returns a recorded response and remembers what it was asked."""
    calls = []

    def transport(url, body, timeout_s):
        calls.append((url, body, timeout_s))
        return json.loads((FIXTURES / name).read_text())

    transport.calls = calls
    return transport


def failing(kind):
    def transport(url, body, timeout_s):
        raise JevFault(kind)

    return transport


def never_called(url, body, timeout_s):
    raise AssertionError("Jev must not be called when a deterministic rule decides")


TASK = {"task_summary": "add a route", "files_touched": 3, "has_tests": True, "prior_failed_attempts": 0}


def test_policy_is_pinned_and_well_formed(policy):
    assert policy["model"] == "typesafe/jev-1.13"
    assert "latest" not in policy["model"]
    assert policy["endpoint"].endswith("/api/alpha/decisions")
    assert policy["retries"] == 0
    for dec in policy["decisions"].values():
        assert "unknown" in dec["options"]
        assert set(dec["action"]) == set(dec["options"])


def test_request_offers_every_option_and_only_allowed_state(policy):
    body = build_request(policy, "model_tier", TASK)
    assert body["model"] == "typesafe/jev-1.13"
    assert set(body["questions"]["pick"]["criteria"]) == {"mechanical", "implementation", "specialist", "unknown"}
    assert body["state"] == TASK
    assert body["questions"]["pick"]["instructions"] == policy["decisions"]["model_tier"]["question"]
    assert "question" not in body["questions"]["pick"]  # the API requires "instructions"
    with pytest.raises(ValueError):
        build_request(policy, "model_tier", {**TASK, "api_key": "x"})


def test_rules_run_before_jev(policy):
    r = route("model_tier", {**TASK, "prior_failed_attempts": 3}, policy, never_called)
    assert (r.choice, r.action, r.source) == ("specialist", "opus_class", "rule")
    r = route("ci_failure_owner", {"failure_excerpt": "E   SyntaxError: invalid syntax"}, policy, never_called)
    assert (r.choice, r.action) == ("syntax_or_import", "haiku_class")
    r = route("ci_failure_owner", {"failure_excerpt": "TimeoutError after 30s"}, policy, never_called)
    assert r.choice == "race_or_timeout"
    r = route("milestone_readiness", {"tests_failed": 2, "tests_skipped": 0, "open_product_decisions": 0, "evidence_summary": ""}, policy, never_called)
    assert (r.choice, r.action) == ("incomplete_local_evidence", "return_to_implementer")
    r = route("milestone_readiness", {"tests_failed": 0, "tests_skipped": 1, "open_product_decisions": 0, "evidence_summary": ""}, policy, never_called)
    assert r.choice == "incomplete_local_evidence"
    r = route("milestone_readiness", {"tests_failed": 0, "tests_skipped": 0, "open_product_decisions": 1, "evidence_summary": ""}, policy, never_called)
    assert (r.choice, r.action) == ("blocked_on_product_decision", "human")


def test_confident_answer_acts(policy):
    t = recorded("model_tier_confident.json")
    r = route("model_tier", TASK, policy, t)
    assert (r.source, r.band, r.choice, r.action) == ("jev", "act", "implementation", "sonnet_class")
    assert r.top_prob == pytest.approx(0.96) and r.margin == pytest.approx(0.94)
    assert t.calls[0][0] == policy["endpoint"]
    assert t.calls[0][2] == pytest.approx(0.8)


def test_middling_answer_is_flagged_but_used(policy):
    r = route("model_tier", TASK, policy, recorded("model_tier_flag.json"))
    assert (r.source, r.band, r.choice) == ("jev", "flag", "implementation")


def test_uncertain_answer_goes_to_human(policy):
    r = route("model_tier", TASK, policy, recorded("model_tier_uncertain.json"))
    assert (r.source, r.band, r.choice, r.action) == ("fallback", "human", "unknown", "human")


def test_unknown_top_option_goes_to_human(policy):
    r = route("model_tier", TASK, policy, recorded("model_tier_unknown.json"))
    assert (r.source, r.choice, r.action) == ("fallback", "unknown", "human")


@pytest.mark.parametrize("kind", ["timeout", "http_or_decode_error", "transport_error"])
def test_faults_fall_back_without_raising(policy, kind):
    r = route("model_tier", TASK, policy, failing(kind))
    assert (r.source, r.band, r.fault, r.action) == ("fallback", "fault", kind, "human")


def test_answer_outside_offered_options_is_schema_invalid(policy):
    r = route("model_tier", TASK, policy, recorded("model_tier_outside_options.json"))
    assert (r.source, r.fault) == ("fallback", "schema_invalid")


def test_malformed_answers_are_rejected():
    opts = ["a", "b", "unknown"]
    for bad in ({}, {"answers": {}}, {"answers": {"pick": {"probabilities": {"a": 0.2, "b": 0.2}}}},
                {"answers": {"pick": {"probabilities": {"a": 1.5, "b": -0.5}}}}):
        with pytest.raises(JevFault):
            parse_answer(bad, opts)


def test_no_api_key_means_no_live_call(policy, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = route("model_tier", TASK, policy)  # default transport, no key: must fault before any network use
    assert (r.source, r.fault) == ("fallback", "no_api_key")


def test_log_record_is_content_free(policy):
    r = route("model_tier", {**TASK, "task_summary": "SECRET-TASK-TEXT"}, policy, recorded("model_tier_confident.json"))
    rec = log_record(r, state_digest="abc123")
    assert "SECRET-TASK-TEXT" not in json.dumps(rec)
    assert rec["policy_version"] == policy["policy_version"] and rec["state_digest"] == "abc123"
    assert set(rec["probabilities"]) == {"mechanical", "implementation", "specialist"}


def test_latency_uses_injected_clock(policy):
    ticks = iter([10.0, 10.25])
    r = route("model_tier", TASK, policy, recorded("model_tier_confident.json"), clock=lambda: next(ticks))
    assert r.latency_ms == pytest.approx(250.0)
