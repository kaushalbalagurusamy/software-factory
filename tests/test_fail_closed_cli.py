"""Fail-closed governance: a missing or crashing required verifier must block.

These tests do not need Unity. They fake the verifier being unavailable or
raising by monkeypatching the governance module's flag and function, so they run
identically with or without a Unity checkout installed.
"""

from pathlib import Path

import pytest

import factory.governance as governance
from factory.cli import main
from factory.governance import (
    DoorType,
    GovernanceEngine,
    GovernanceReport,
    RiskCategory,
    VerifierStatus,
)

CODE = "def add(a, b):\n    return a + b\n"
CODE_V2 = "def add(a, b):\n    return b + a\n"


@pytest.fixture
def py_pair(tmp_path: Path):
    pre = tmp_path / "pre.py"
    post = tmp_path / "post.py"
    pre.write_text(CODE)
    post.write_text(CODE_V2)
    return pre, post


@pytest.fixture
def sql_pair(tmp_path: Path):
    pre = tmp_path / "v1.sql"
    post = tmp_path / "v2.sql"
    pre.write_text("CREATE TABLE t (id INT);")
    post.write_text("DROP TABLE accounts CASCADE;")
    return pre, post


@pytest.fixture
def verifier_unavailable(monkeypatch):
    monkeypatch.setattr(governance, "UNITY_AVAILABLE", False)


@pytest.fixture
def verifier_crashes(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(governance, "UNITY_AVAILABLE", True)
    monkeypatch.setattr(governance, "compute_semantic_delta", boom, raising=False)


def _no_harmless_classification(report: GovernanceReport) -> None:
    assert not any(
        r.door_type == DoorType.TWO_WAY and r.category == RiskCategory.LOCAL_REFACTOR and not r.requires_adr
        for r in report.risks
    )


# ---- CLI exit-code contract ----------------------------------------------

def test_cli_missing_verifier_exits_3(py_pair, verifier_unavailable, capsys):
    ret = main(["audit", "--pre", str(py_pair[0]), "--post", str(py_pair[1])])
    out = capsys.readouterr().out
    assert ret == 3
    assert "GATE FAILED" in out
    assert "unavailable" in out.lower()
    assert "Autonomous Execution Permitted" not in out
    assert "TWO-WAY DOOR" not in out


def test_cli_crashing_verifier_exits_3_even_with_strict(py_pair, verifier_crashes, capsys):
    ret = main(["audit", "--pre", str(py_pair[0]), "--post", str(py_pair[1]), "--strict"])
    out = capsys.readouterr().out
    assert ret == 3
    assert "GATE FAILED" in out
    assert "errored" in out.lower()
    assert "solver exploded" in out
    assert "Autonomous Execution Permitted" not in out


def test_cli_pattern_only_exits_4_by_default(py_pair, capsys):
    ret = main(["audit", "--pre", str(py_pair[0]), "--post", str(py_pair[1]), "--pattern-only"])
    out = capsys.readouterr().out
    assert ret == 4
    assert "UNVERIFIED" in out
    assert "Autonomous Execution Permitted" not in out


def test_cli_pattern_only_accepted_exits_0_but_stays_labelled(py_pair, capsys):
    ret = main(
        ["audit", "--pre", str(py_pair[0]), "--post", str(py_pair[1]), "--pattern-only", "--accept-unverified"]
    )
    out = capsys.readouterr().out
    assert ret == 0
    assert "UNVERIFIED" in out
    assert "Autonomous Execution Permitted" not in out


def test_cli_accept_unverified_without_pattern_only_does_not_hide_gate_failure(
    py_pair, verifier_unavailable, capsys
):
    ret = main(["audit", "--pre", str(py_pair[0]), "--post", str(py_pair[1]), "--accept-unverified"])
    assert ret == 3


def test_cli_sql_one_way_strict_still_exits_1(sql_pair, verifier_unavailable, capsys):
    ret = main(["audit", "--pre", str(sql_pair[0]), "--post", str(sql_pair[1]), "--strict"])
    assert ret == 1
    assert "ONE-WAY DOOR" in capsys.readouterr().out
