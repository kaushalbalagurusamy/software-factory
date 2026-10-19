"""Failure signatures are stable under changed numbers, paths, ids and timestamps."""
from factory.qa.signature import normalize_error, signature


def test_stable_under_numbers_paths_and_timestamps():
    a = "2026-10-19T10:00:01Z /tmp/run-1/app/login.py:42 AssertionError: expected 401 got 500 (req 9f3a1c2d77)"
    b = "2026-10-20T23:59:59+00:00 /var/ci/xyz/app/login.py:97 AssertionError: expected 401 got 502 (req aa00bb11cc)"
    assert normalize_error(a) == normalize_error(b)
    assert signature("AC-1.1", a) == signature("AC-1.1", b)


def test_stable_under_uuid_and_address_and_windows_path():
    a = r"id 123e4567-e89b-12d3-a456-426614174000 at 0x7ffd1234 C:\Users\a\x\app.py"
    b = r"id 00000000-0000-0000-0000-000000000000 at 0x1 D:\work\q\app.py"
    assert signature("c", a) == signature("c", b)


def test_differs_by_case_or_message():
    base = signature("AC-1", "AssertionError: wrong status")
    assert signature("AC-2", "AssertionError: wrong status") != base
    assert signature("AC-1", "KeyError: 'user'") != base


def test_shape_is_short_hex():
    s = signature("AC-1", "boom")
    assert len(s) == 16 and int(s, 16) >= 0


def test_ordinary_words_with_slash_are_not_masked():
    assert "and/or" in normalize_error("expected and/or got nothing")
