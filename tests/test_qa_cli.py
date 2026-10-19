"""CLI: feedback with leak check, regression proposals, verify-pass via the slices package, stats."""
import json
import shutil
from pathlib import Path

import pytest

from factory.qa.cli import main
from factory.slices.cli import main as slices_main

FIX = Path(__file__).resolve().parent / "fixtures"
OK, ERR, USAGE, LEAK, REFUSED = 0, 1, 2, 3, 4


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "evals").mkdir()
    shutil.copy(FIX / "qa" / "protected_eval.py", tmp_path / "evals" / "test_login.py")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text("paths:\n  eval: [evals/**]\n")
    shutil.copytree(FIX / "slices" / "docs" / "slices" / "demo-login", tmp_path / "docs" / "slices" / "demo-login")
    return tmp_path


def qa(proj, *args):
    return main(["--root", str(proj), "--slice", "demo-login", *args])


GOOD = ["feedback", "--criterion", "AC-1.1", "--observed", "HTTP 500 on wrong password",
        "--expected", "HTTP 401 with an invalid-credentials error",
        "--repro", "curl -s -X POST localhost:3000/login -d user=ada -d password=bad"]


def test_feedback_written_in_contract_terms(proj):
    assert qa(proj, "init", "--criteria", "AC-1", "AC-2") == OK
    assert qa(proj, "record", "--status", "fail", "--case", "AC-1.1", "--error", "boom", "--tier", "sonnet") == OK
    assert qa(proj, "record", "--status", "fail", "--case", "AC-1.1", "--error", "boom", "--tier", "sonnet", "--rerun") == OK
    assert qa(proj, *GOOD) == OK
    text = (proj / ".sf/slices/demo-login/qa-feedback/1.md").read_text()
    assert "AC-1.1" in text and "Attempt 1" in text and "Changed since the last attempt" in text


def test_feedback_built_from_protected_assertion_is_rejected_and_not_written(proj, capsys):
    qa(proj, "init", "--criteria", "AC-1")
    bad = ["feedback", "--criterion", "AC-1.1", "--repro", "curl localhost:3000/login",
           "--observed", "500", "--expected",
           'assert response.status_code == 401 and response.json()["error"] == "invalid_credentials"']
    assert qa(proj, *bad) == LEAK
    assert "refusing to write" in capsys.readouterr().err
    assert not (proj / ".sf/slices/demo-login/qa-feedback").exists()


def test_feedback_refuses_without_any_protected_paths(tmp_path):
    main(["--root", str(tmp_path), "--slice", "s", "init", "--criteria", "AC-1"])
    rc = main(["--root", str(tmp_path), "--slice", "s", *GOOD])
    assert rc == USAGE


def test_regression_proposals_are_append_only_and_never_touch_evals(proj):
    qa(proj, "init", "--criteria", "AC-1")
    before = (proj / "evals/test_login.py").read_text()
    args = ["regression-propose", "--signature", "abc123", "--criterion", "AC-1", "--input-class",
            "wrong password for existing user", "--expected", "401 invalid-credentials", "--recurred", "attempts 2 and 3"]
    assert qa(proj, *args) == OK and qa(proj, *args) == OK
    p = proj / ".sf/slices/demo-login/regression-proposals/abc123.md"
    assert p.read_text().count("## Proposal at") == 2 and p.read_text().startswith("# Regression")
    assert (proj / "evals/test_login.py").read_text() == before
    assert json.loads((proj / ".sf/slices/demo-login/state.json").read_text())["proposals"]["abc123"]


def test_verify_pass_goes_through_slices_chain_and_is_refused_when_unticked(proj):
    qa(proj, "init", "--criteria", "AC-1")
    sl = str(proj / "docs" / "slices" / "demo-login")
    args = ["verify-pass", "1.1", "--evidence", "browser check ok", "--commit", "abc1234", "--criteria", "AC-1"]
    assert qa(proj, *args) == REFUSED  # not ticked by the implementer yet
    assert not (Path(sl) / "verification.json").exists()
    assert slices_main(["tick", sl, "1.1", "--role", "implementer"]) == OK
    assert qa(proj, *args) == OK
    assert len(json.loads((Path(sl) / "verification.json").read_text())) >= 1


def test_stats_and_next_and_audit(proj, capsys):
    qa(proj, "init", "--criteria", "AC-1")
    qa(proj, "record", "--status", "pass", "--tier", "opus", "--duration", "12")
    capsys.readouterr()
    assert qa(proj, "stats") == OK
    assert json.loads(capsys.readouterr().out)["opus"]["success_rate"] == 1.0
    assert qa(proj, "next") == OK and json.loads(capsys.readouterr().out)["action"] == "accept"
    f = proj / ".sf/slices/demo-login/attempts.jsonl"
    f.write_text(f.read_text().replace("opus", "haiku"))
    assert qa(proj, "audit") == ERR
    assert qa(proj, "next") == ERR


def test_policy_command(proj, capsys):
    assert qa(proj, "policy") == OK
    assert json.loads(capsys.readouterr().out)["attempts_per_signature"] == 4


# --- written-file hardening: signature validation and full-content leak check -------------------------

SECRET = "the-protected-marker-line-number-one-for-leak-tests"


@pytest.fixture
def prot(proj):
    (proj / "evals" / "marker.txt").write_text(SECRET + "\n")
    qa(proj, "init", "--criteria", "AC-1")
    return proj


def reg(proj, **over):
    a = {"signature": "abc123", "criterion": "AC-1", "input-class": "wrong password",
         "expected": "401 invalid-credentials", "recurred": "attempts 2 and 3"}
    a.update(over)
    args = ["regression-propose"]
    for k, v in a.items():
        args += [f"--{k}", v]
    return qa(proj, *args)


def fb(proj, **over):
    a = {"criterion": "AC-1", "observed": "HTTP 500", "expected": "HTTP 401", "repro": "curl localhost:3000/login"}
    a.update(over)
    args = ["feedback"]
    for k, v in a.items():
        args += [f"--{k}", v]
    return qa(proj, *args)


@pytest.mark.parametrize("sig", ["a/b", "..", "../x", "a\nb", "a" * 65, "", "a b", "a.md"])
def test_bad_signature_rejected_for_proposals_and_feedback(prot, sig, capsys):
    assert reg(prot, signature=sig) == USAGE
    assert "signature" in capsys.readouterr().err
    assert fb(prot, signature=sig) == USAGE
    assert not (prot / ".sf/slices/demo-login/regression-proposals").exists()
    assert not (prot / ".sf/slices/demo-login/qa-feedback").exists()
    assert not list(prot.rglob("*.md.md")) and not (prot / ".sf/slices/x.md").exists()


def test_good_signature_accepted(prot):
    assert reg(prot, signature="Ab_9-" + "c" * 59) == OK


@pytest.mark.parametrize("field", ["criterion", "input-class", "expected", "recurred"])
def test_protected_material_in_any_proposal_field_rejected(prot, field):
    assert reg(prot, **{field: f"see {SECRET}"}) == LEAK
    assert not (prot / ".sf/slices/demo-login/regression-proposals").exists()


@pytest.mark.parametrize("field", ["criterion", "observed", "expected", "repro"])
def test_protected_material_in_any_feedback_field_rejected(prot, field):
    assert fb(prot, **{field: f"see {SECRET}"}) == LEAK
    assert not (prot / ".sf/slices/demo-login/qa-feedback").exists()


def test_protected_material_in_header_position_rejected(prot):
    # the file header is built from the signature; the whole file content is checked, and so is a title-like field
    assert reg(prot, criterion=f"# {SECRET}") == LEAK


def test_clean_criterion_level_report_passes(prot):
    assert reg(prot) == OK and fb(prot) == OK


def test_reviewer_note_is_leak_checked_and_signature_validated(prot):
    base = ["reviewer-verdict", "--verdict", "unresolved"]
    assert qa(prot, *base, "--signature", "abc123", "--note", f"x {SECRET}") == LEAK
    assert qa(prot, *base, "--signature", "../x", "--note", "ok") == USAGE
    assert qa(prot, *base, "--signature", "abc123", "--note", "AC-1 contract ambiguous") == OK
