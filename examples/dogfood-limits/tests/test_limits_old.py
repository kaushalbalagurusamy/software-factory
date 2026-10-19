"""The old, plausible unit test: it passes on the bad patch too, which is the point of the demonstration."""
import importlib
import os


def load():
    return importlib.import_module("limits")


def test_inside_range():
    assert load().clamp(5, 0, 10) == 5


def test_below_lower_bound():
    assert load().clamp(-3, 0, 10) == 0
