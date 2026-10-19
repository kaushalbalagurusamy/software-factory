"""Shared pytest configuration.

Tests marked ``requires_unity`` need the Unity compiler and its ledger example.
When Unity is absent they FAIL with an explicit reason (never skip or xfail).
CI, which cannot see Unity, deselects them with ``-m "not requires_unity"``.
"""

import pytest

from unity_env import unity_problem


def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_unity") is not None:
        problem = unity_problem()
        if problem:
            pytest.fail(f"requires_unity test cannot run: {problem}", pytrace=False)
