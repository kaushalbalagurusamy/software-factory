"""Helpers: the call targets used by core."""


def double(x):
    return x * 2


def fast_path(x):
    return x + 1


class Worker:
    def process(self, n):
        return n + 1
