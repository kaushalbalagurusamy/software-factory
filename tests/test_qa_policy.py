import pytest

from factory.qa.policy import PolicyError, load_policy


def test_defaults(tmp_path):
    p = load_policy(tmp_path)
    assert p.attempts_per_signature == 4
    assert p.tiers == ("sonnet",) * 4
    assert p.flake_reruns == 1
    assert p.slice_attempt_cap == 10
    assert p.budget_tokens is None and p.budget_cost_usd is None


@pytest.mark.parametrize("text", [
    "ENOSPC: no space left on device", "Out of memory: Killed process 12", "Process killed by signal 9",
    "Command timed out after 120s", "OSError: [Errno 98] Address already in use",
    "bash: playwright: command not found",
])
def test_environment_patterns(tmp_path, text):
    assert load_policy(tmp_path).is_environment(text)


def test_ordinary_assertion_is_not_environment(tmp_path):
    assert not load_policy(tmp_path).is_environment("AssertionError: expected 401 got 500")


def test_overrides_from_file(tmp_path):
    (tmp_path / ".sf").mkdir()
    (tmp_path / ".sf" / "policy.yaml").write_text(
        "attempts_per_signature: 3\ntiers: [haiku, sonnet, opus]\nallow_non_default_models: [haiku, opus]\nflake_reruns: 2\n"
        "budget: {tokens: 1000, cost_usd: 1.5}\n")
    p = load_policy(tmp_path)
    assert (p.attempts_per_signature, p.tiers, p.flake_reruns) == (3, ("haiku", "sonnet", "opus"), 2)
    assert (p.budget_tokens, p.budget_cost_usd) == (1000, 1.5)


@pytest.mark.parametrize("text", ["attempts_per_signature: 0\n", "tiers: []\n", "bogus: 1\n",
                                   "flake_reruns: -1\n", "environment: {patterns: ['(']}\n"])
def test_invalid_policy_rejected(tmp_path, text):
    (tmp_path / ".sf").mkdir()
    (tmp_path / ".sf" / "policy.yaml").write_text(text)
    with pytest.raises(PolicyError):
        load_policy(tmp_path)


def test_undeclared_non_sonnet_model_rejected_with_clear_error(tmp_path):
    (tmp_path / ".sf").mkdir()
    (tmp_path / ".sf" / "policy.yaml").write_text("tiers: [sonnet, opus]\n")
    with pytest.raises(PolicyError, match="opus.*explicit opt-in.*allow_non_default_models"):
        load_policy(tmp_path)
    (tmp_path / ".sf" / "policy.yaml").write_text("tiers: [sonnet, opus]\nallow_non_default_models: [haiku]\n")
    with pytest.raises(PolicyError, match="opus"):
        load_policy(tmp_path)


def test_opt_in_works_and_is_flagged(tmp_path):
    (tmp_path / ".sf").mkdir()
    (tmp_path / ".sf" / "policy.yaml").write_text("tiers: [sonnet, opus]\nallow_non_default_models: [opus]\n")
    p = load_policy(tmp_path)
    assert p.tiers == ("sonnet", "opus")
    assert p.as_dict()["tiers_flagged"] == ["sonnet", "opus (opt-in)"]
    assert load_policy(tmp_path / "none").as_dict()["tiers_flagged"] == ["sonnet"] * 4
