"""Leak check: feedback must never carry protected test material."""
import subprocess
import sys
from pathlib import Path

import pytest

from factory.qa.leak import LeakError, assert_no_leak, leak_check

FIX = Path(__file__).resolve().parent / "fixtures" / "qa" / "protected_eval.py"


def test_verbatim_assertion_line_is_rejected():
    text = "The check says:\n    assert response.status_code == 401 and response.json()[\"error\"] == \"invalid_credentials\"\n"
    found = leak_check(text, [FIX])
    assert found and found[0].kind == "line"


def test_forty_char_window_is_rejected_even_when_reflowed():
    text = 'Observed: client.post("/login",   data={"user": "ada", "password": "wrong-horse-battery"}) failed'
    assert any(f.kind == "window" for f in leak_check(text, [FIX]))


def test_criterion_level_description_passes():
    text = ("AC-1.1 violated. Expected: signing in with a wrong password is refused with HTTP 401 and an "
            "invalid-credentials error. Observed: HTTP 500. Reproduce: curl -s -X POST localhost:3000/login "
            "-d user=ada -d password=bad")
    assert leak_check(text, [FIX]) == []
    assert_no_leak(text, [FIX])


def test_assert_no_leak_raises_without_echoing_protected_text():
    with pytest.raises(LeakError) as e:
        assert_no_leak("def test_login_rejects_wrong_password(client):", [FIX])
    assert "wrong_password" not in str(e.value) and "protected_eval.py" in str(e.value)


def test_protected_path_named_in_text_is_rejected():
    assert any(f.kind == "path" for f in leak_check("run pytest tests/fixtures/qa/protected_eval.py", [FIX]))


def test_directory_and_glob_protected(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "a.txt").write_text("the secret expected payload is 4f2a-9981-zz-unique-token\n")
    t = "the secret expected payload is 4f2a-9981-zz-unique-token"
    assert leak_check(t, [tmp_path / "evals"])
    assert leak_check(t, ["evals/**"], root=tmp_path)
    assert leak_check("nothing alike", ["evals/**"], root=tmp_path) == []


def test_short_trivial_lines_do_not_trigger(tmp_path):
    f = tmp_path / "p.py"
    f.write_text("import os\n}\nreturn x\n")
    assert leak_check("import os and return x", [f]) == []
