"""Experiment record check."""
import json

import pytest

from factory.intake.cli import main

ENUM = "# Candidate enumeration\n\nDate: 2026-10-01\n\n- alpha: the first\n- beta: the second\n"


def good():
    return {
        "question": "Which store is better?",
        "candidates": [
            {"name": "alpha", "enumeration": "enumeration-2026-10-01.md"},
            {"name": "beta", "enumeration": "enumeration-2026-10-01.md"},
        ],
        "metrics": [{"name": "latency_ms", "direction": "lower"}, {"name": "cost_usd", "direction": "lower"}],
        "decision_rule_preregistered": "Pick the lowest latency among candidates within 20 percent of the lowest cost.",
        "result": {"winner": "alpha", "basis": ["latency_ms", "cost_usd"],
                   "scores": {"alpha": {"latency_ms": 5, "cost_usd": 2}, "beta": {"latency_ms": 7, "cost_usd": 1}}},
        "as_of": "2026-10-02",
    }


@pytest.fixture
def exp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "experiments" / "e1"
    d.mkdir(parents=True)
    (d / "enumeration-2026-10-01.md").write_text(ENUM)
    return d


def write(d, data):
    (d / "results.json").write_text(json.dumps(data))


def run():
    return main(["experiments", "check"])


def test_valid_experiment_passes(exp):
    write(exp, good())
    assert run() == 0


def test_literal_candidate_list_is_rejected(exp, capsys):
    d = good(); d["candidates"] = ["alpha", "beta"]
    write(exp, d)
    assert run() == 1 and "enumeration" in capsys.readouterr().err


def test_candidate_pointing_at_missing_enumeration_is_rejected(exp, capsys):
    d = good(); d["candidates"][0]["enumeration"] = "gone.md"
    write(exp, d)
    assert run() == 1 and "gone.md" in capsys.readouterr().err


def test_enumeration_must_be_in_the_same_directory(exp, capsys):
    (exp.parent / "elsewhere.md").write_text(ENUM)
    d = good(); d["candidates"][0]["enumeration"] = "../elsewhere.md"
    write(exp, d)
    assert run() == 1 and "same directory" in capsys.readouterr().err


def test_undated_enumeration_is_rejected(exp, capsys):
    (exp / "enumeration-2026-10-01.md").write_text("- alpha\n- beta\n")
    write(exp, good())
    assert run() == 1 and "date" in capsys.readouterr().err


def test_candidate_missing_from_its_enumeration_is_rejected(exp, capsys):
    d = good(); d["candidates"].append({"name": "gamma", "enumeration": "enumeration-2026-10-01.md"})
    d["result"]["scores"]["gamma"] = {"latency_ms": 9, "cost_usd": 9}
    write(exp, d)
    assert run() == 1 and "gamma" in capsys.readouterr().err


def test_single_metric_is_rejected(exp, capsys):
    d = good(); d["metrics"] = d["metrics"][:1]; d["result"]["basis"] = ["latency_ms"]
    write(exp, d)
    assert run() == 1 and "at least two metrics" in capsys.readouterr().err


def test_missing_preregistered_rule_is_rejected(exp, capsys):
    d = good(); d.pop("decision_rule_preregistered")
    write(exp, d)
    assert run() == 1 and "decision_rule_preregistered" in capsys.readouterr().err


def test_preregistered_rule_as_path_must_exist(exp, capsys):
    d = good(); d["decision_rule_preregistered"] = "rule.md"
    write(exp, d)
    assert run() == 1 and "rule.md" in capsys.readouterr().err
    (exp / "rule.md").write_text("Rule text.\n")
    assert run() == 0


def test_single_metric_winner_is_rejected(exp, capsys):
    d = good(); d["result"]["basis"] = ["latency_ms"]
    write(exp, d)
    assert run() == 1 and "single-metric" in capsys.readouterr().err


def test_winner_must_be_a_candidate_and_scored_on_every_metric(exp, capsys):
    d = good(); d["result"]["winner"] = "zeta"
    write(exp, d)
    assert run() == 1 and "zeta" in capsys.readouterr().err
    d = good(); del d["result"]["scores"]["beta"]["cost_usd"]
    write(exp, d)
    assert run() == 1 and "cost_usd" in capsys.readouterr().err


def test_missing_as_of_or_question_fails(exp):
    d = good(); d.pop("as_of"); write(exp, d)
    assert run() == 1
    d = good(); d.pop("question"); write(exp, d)
    assert run() == 1


def test_explicit_no_winner_result_is_allowed(exp):
    d = good(); d["result"] = {"winner": None, "status": "no-winner", "basis": ["latency_ms", "cost_usd"],
                               "scores": good()["result"]["scores"]}
    write(exp, d)
    assert run() == 0


def test_dir_without_results_and_bad_json_fail(exp, capsys):
    assert run() == 1 and "results.json" in capsys.readouterr().err  # dir without results.json
    (exp / "results.json").write_text("{nope")
    assert run() == 1
