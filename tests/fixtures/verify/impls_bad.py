"""Intentionally wrong implementations: each violates its contract."""


def clamp_off_by_one(x: int, lo: int, hi: int) -> int:
    if x <= lo:  # fine for x == lo ...
        return lo
    if x >= hi - 1:  # ... but off by one at the top: x == hi - 1 returns hi
        return hi
    return x


def clamp_wrong_comparison(x: int, lo: int, hi: int) -> int:
    if x > lo:  # should be x < lo
        return lo
    elif x > hi:
        return hi
    return x


def floor_div_no_guard(a: int, b: int) -> int:
    return a // b  # contract promises ZeroDivisionError only declared case; see tests


def add_two(x: int) -> int:
    return x + 2  # spec says x + 1: spec text equals impl text only in the buggy variant
