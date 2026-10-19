"""Core: resolved, syntactic and unresolved call shapes in one module."""
from . import helpers
from .helpers import double as dbl
from .registry import REGISTRY, register
from .dyn import *

try:
    from .helpers import fast_path
except ImportError:
    from .fallback import fast_path

COUNTER = 0
CACHE = {}


def plain(x):
    return helpers.double(x)


def aliased(x):
    return dbl(x) + plain(x)


def untyped(obj):
    return obj.process(1)


def dynamic(obj, name):
    fn = getattr(obj, name)
    return fn(1)


def through_param(callback):
    return callback(3)


def star_user():
    return star_made()


def conditional(x):
    return fast_path(x)


def call_of_call():
    return plain(1)(2)


def subscript(table):
    return table["k"](1)


def bump():
    global COUNTER
    COUNTER += 1
    CACHE["k"] = 1
    REGISTRY.append(1)


@register
def decorated(x):
    return x


def uses_decorated():
    return decorated(1)


class Engine:
    mode = "idle"

    def __init__(self):
        self.count = 0
        self.items = []

    def step(self):
        self.count += 1
        return self._inner()

    def _inner(self):
        return plain(self.count)


class Sub(Engine):
    def step(self):
        return super().step()
