"""Module-level mutable state and a decorator that may wrap its argument."""

REGISTRY = []
LIMIT = 10


def register(fn):
    REGISTRY.append(fn)
    return fn
