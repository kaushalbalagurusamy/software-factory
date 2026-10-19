"""(7) Edge honesty: nothing is `resolved` unless Python really reaches that symbol; unknowns carry reasons."""
import pytest

from shelp import edges_from, scan

FIX = {
    "pkg/__init__.py": "",
    "pkg/a.py": (
        "import functools\n"
        "from pkg import c as calias\n"
        "from pkg.c import helper as h1\n"
        "\n"
        "h2 = h1\n"
        "\n"
        "try:\n    from pkg.fast import speed\nexcept ImportError:\n    from pkg.slow import speed\n"
        "\n"
        "if functools:\n    from pkg.fast import only_if\n"
        "\n\n"
        "def local_helper():\n    return 1\n\n\n"
        "def wrap(fn):\n    @functools.wraps(fn)\n    def inner(*a):\n        return fn(*a)\n    return inner\n\n\n"
        "@wrap\ndef wrapped():\n    return 3\n\n\n"
        "class Base:\n    def step(self):\n        return 1\n\n\n"
        "class Other:\n    def step(self):\n        return 3\n\n\n"
        "def caller(obj, name, cb):\n"
        "    getattr(obj, name)()\n"
        "    obj.step()\n"
        "    h2()\n"
        "    calias.helper()\n"
        "    speed()\n"
        "    only_if()\n"
        "    wrapped()\n"
        "    local_helper()\n"
        "    cb()\n"
        "    eval('1')\n"
        "    {'k': local_helper}['k']()\n"
        "    (lambda: 1)()\n"
        "    return obj.missing()\n"
    ),
    "pkg/star_user.py": "from pkg.b import *\n\n\ndef use():\n    return from_star()\n",
    "pkg/b.py": "def from_star():\n    return 1\n\n\ndef shadowed():\n    return 'b'\n",
    "pkg/c.py": "def helper():\n    return 1\n\n\ndef run():\n    return helper()\n",
    "pkg/fast.py": "def speed():\n    return 1\n\n\ndef only_if():\n    return 1\n",
    "pkg/slow.py": "def speed():\n    return 0\n",
}

UNRESOLVED = {
    "getattr(obj, name)": None,
    "getattr": "dynamic_attribute",
    "h2": "call_through_variable",
    "speed": "conditional_import",
    "only_if": "conditional_import",
    "wrapped": "decorator_wrapped",
    "cb": "call_through_variable",
    "eval": "dynamic_code",
    "{'k': local_helper}['k']": "subscript_call",
    "lambda: 1": "lambda_call",
}


@pytest.fixture(scope="module")
def ex(tmp_path_factory):
    return scan(tmp_path_factory.mktemp("edges"), FIX)


@pytest.mark.parametrize("text", sorted(UNRESOLVED))
def test_dynamic_or_ambiguous_calls_are_unresolved_with_reason(ex, text):
    for e in edges_from(ex, "pkg.a:caller", text):
        assert e["kind"] == "unresolved" and e["target"] is None and e["reason"], e
        if UNRESOLVED[text]:
            assert e["reason_code"] == UNRESOLVED[text], e


def test_candidates_are_not_claims(ex):
    (e,) = edges_from(ex, "pkg.a:caller", "obj.step")
    assert e["kind"] == "syntactic" and e["target"] is None
    assert set(e["candidates"]) == {"pkg.a:Base.step", "pkg.a:Other.step"}


def test_true_static_calls_resolve(ex):
    assert edges_from(ex, "pkg.a:caller", "calias.helper")[0]["target"] == "pkg.c:helper"
    assert edges_from(ex, "pkg.a:caller", "local_helper")[0]["target"] == "pkg.a:local_helper"
    assert edges_from(ex, "pkg.c:run", "helper")[0]["kind"] == "resolved"


def test_star_import_is_unresolved(ex):
    (e,) = edges_from(ex, "pkg.star_user:use", "from_star")
    assert e["kind"] == "unresolved" and e["reason_code"] == "star_import"


def test_limits_never_claim_a_complete_graph(ex):
    lim = ex["limits"]
    assert lim["complete_call_graph"] is False
    assert lim["unresolved_edges"] == sum(1 for e in ex["edges"] if e["kind"] == "unresolved")
    assert sum(lim["unresolved_by_reason"].values()) == lim["unresolved_edges"]


def test_scope_lists_every_unresolved_edge_with_reason(ex):
    from factory.structure.scope import scope
    sc = scope(ex, ["pkg.a:caller"], depth=1)
    assert sc["limits"]["complete_call_graph"] is False
    nf = {(n["text"], n["kind"]) for n in sc["not_followed"]}
    for text in UNRESOLVED:
        assert (text, "unresolved") in nf, text
    assert all(n["reason"] for n in sc["not_followed"])
    assert sc["limits"]["unresolved_in_scope"] >= len(UNRESOLVED)


# ------------------------------------------------- calls that Python does NOT route to the "resolved" target
def _assert_not_falsely_resolved(ex, caller, text, wrong_target, why):
    for e in edges_from(ex, caller, text):
        assert not (e["kind"] == "resolved" and e["target"] == wrong_target), f"{why}: {e}"


def test_user_decorator_named_like_a_transparent_one(tmp_path):
    """A repo function called `cache` replaces the function; its name must not make it transparent."""
    ex = scan(tmp_path, {"m.py": "def cache(fn):\n    return lambda *a: 0\n\n\n@cache\ndef target():\n    return 2\n\n\n"
                                 "def use():\n    return target()\n"})
    _assert_not_falsely_resolved(ex, "m:use", "target", "m:target", "wrapped by a repo-defined decorator named 'cache'")


def test_star_import_after_def_rebinds_the_name(tmp_path):
    ex = scan(tmp_path, {"pkg/__init__.py": "", "pkg/b.py": "def shadowed():\n    return 'b'\n",
                         "pkg/late.py": "def shadowed():\n    return 'late'\n\n\nfrom pkg.b import *\n\n\ndef use():\n    return shadowed()\n"})
    _assert_not_falsely_resolved(ex, "pkg.late:use", "shadowed", "pkg.late:shadowed",
                                 "a later `from pkg.b import *` rebinds shadowed to pkg.b:shadowed")


def test_instance_attribute_shadows_method(tmp_path):
    ex = scan(tmp_path, {"m.py": "def other():\n    return 1\n\n\nclass Inst:\n    def __init__(self):\n        self.go = other\n\n"
                                 "    def go(self):\n        return 0\n\n    def use(self):\n        return self.go()\n"})
    _assert_not_falsely_resolved(ex, "m:Inst.use", "self.go", "m:Inst.go", "self.go is rebound to `other` in __init__")


def test_monkeypatched_module_attribute(tmp_path):
    ex = scan(tmp_path, {"pkg/__init__.py": "", "pkg/c.py": "def helper():\n    return 1\n\n\ndef run():\n    return helper()\n",
                         "pkg/patcher.py": "import pkg.c\n\n\ndef fake():\n    return 99\n\n\npkg.c.helper = fake\n"})
    _assert_not_falsely_resolved(ex, "pkg.c:run", "helper", "pkg.c:helper", "pkg/patcher.py rebinds pkg.c.helper")


def test_self_call_with_override_in_repo(tmp_path):
    """Base.run's self.step() reaches Sub.step for Sub instances; the repo shows the override."""
    ex = scan(tmp_path, {"m.py": "class Base:\n    def run(self):\n        return self.step()\n\n    def step(self):\n        return 1\n\n\n"
                                 "class Sub(Base):\n    def step(self):\n        return 2\n"})
    (e,) = edges_from(ex, "m:Base.run", "self.step")
    assert e["kind"] != "resolved" or "m:Sub.step" in e["candidates"], \
        f"resolved to Base.step only, although m:Sub.step overrides it: {e}"


def test_aliases_of_aliases(tmp_path):
    ex = scan(tmp_path, {"pkg/__init__.py": "", "pkg/c.py": "def helper():\n    return 1\n",
                         "pkg/r.py": "from pkg.c import helper\n",
                         "pkg/u.py": "from pkg.r import helper as h\n\nalias = h\n\n\ndef use():\n    h()\n    return alias()\n"})
    (direct,) = edges_from(ex, "pkg.u:use", "h")
    assert direct["kind"] == "resolved" and direct["target"] == "pkg.c:helper"  # re-export is a true static path
    (via_var,) = edges_from(ex, "pkg.u:use", "alias")
    assert via_var["kind"] == "unresolved"


def test_same_method_name_on_two_classes_via_parameter(tmp_path):
    ex = scan(tmp_path, {"m.py": "class A:\n    def save(self):\n        return 1\n\n\nclass B:\n    def save(self):\n        return 2\n\n\n"
                                 "def persist(x):\n    return x.save()\n"})
    (e,) = edges_from(ex, "m:persist", "x.save")
    assert e["kind"] == "syntactic" and e["target"] is None and set(e["candidates"]) == {"m:A.save", "m:B.save"}
