import pytest

from factory.verify.contracts import ContractError, check_ids, load_contract_text, parse_contract
from test_verify_support import make, clamp_contract

GOOD_YAML = """
contract_id: C-CLAMP-001
requirement_ids: [REQ-12, REQ-13]
symbol: "impls_good:clamp"
state_scope: pure
semantics: math_int
check_method: solver
concurrency: none
frame: nothing
params: {x: int, lo: int, hi: int}
returns: int
assumptions: ["callers pass ints"]
route: {default: test}
intended:
  preconditions: ["lo <= hi"]
  postconditions:
    - "result >= lo"
    - {id: upper, expr: "result <= hi"}
  errors: []
observed:
  notes: ["current code happens to return hi for x == hi"]
"""


def test_load_yaml_contract():
    c = load_contract_text(GOOD_YAML)
    assert c.contract_id == "C-CLAMP-001"
    assert [p.id for p in c.postconditions] == ["post-1", "upper"]
    assert c.module_name == "impls_good" and c.qualname == "clamp"
    assert c.concurrency == "none" and c.frame == []
    assert c.observed["notes"]


def test_observed_never_affects_hash_or_obligations():
    a = load_contract_text(GOOD_YAML)
    b = load_contract_text(GOOD_YAML.replace("current code happens", "something else entirely"))
    assert a.content_hash() == b.content_hash()
    assert len(a.postconditions) == len(b.postconditions)


@pytest.mark.parametrize("missing", ["requirement_ids", "contract_id", "concurrency", "frame", "semantics",
                                      "check_method", "returns", "params", "symbol", "state_scope"])
def test_required_keys(missing):
    import yaml
    doc = yaml.safe_load(GOOD_YAML)
    del doc[missing]
    with pytest.raises(ContractError, match="missing required"):
        parse_contract(doc)


def test_unknown_top_level_key_rejected():
    with pytest.raises(ContractError, match="unknown keys"):
        load_contract_text(GOOD_YAML + "\nfoo: 1\n")


def test_concurrency_must_be_explicit():
    with pytest.raises(ContractError, match="concurrency"):
        make(concurrency="")


@pytest.mark.parametrize("expr", [
    "result >= lo", "x // 2 == result or x % 3 == 0", "abs(result) <= max(abs(x), 1)",
    "result == (x if x > 0 else -x)", "not (x < 0) and old(x) == x", "min(x, lo, hi) <= result",
    "lo <= x < hi",
])
def test_predicate_language_accepts(expr):
    make(post=[expr])


@pytest.mark.parametrize("expr,why", [
    ("len(x) > 0", "len"),
    ("x ** 2 >= 0", "Pow"),
    ("x / 2 == result", "Div"),
    ("[x for x in lo]", "comprehensions"),
    ("x.real == 1", "attribute"),
    ("foo(x)", "foo"),
    ("x is None", "Is"),
    ("result == 1.5", "floating"),
    ("x & 1 == 0", "BitAnd"),
    ("undefined_name > 0", "undefined_name"),
    ("old(1)", "old"),
    ("x +", "syntax"),
    ("x + lo", "boolean"),
])
def test_predicate_language_rejects_with_reason(expr, why):
    with pytest.raises(ContractError) as ei:
        make(post=[expr])
    assert why.lower() in str(ei.value).lower()


def test_result_not_allowed_in_precondition_or_error_condition():
    with pytest.raises(ContractError, match="result"):
        make(pre=["result > 0"], post=["result > 0"])
    with pytest.raises(ContractError, match="result"):
        make(post=["result > 0"], errors=[{"exception": "ValueError", "when": "result < 0"}])


def test_contract_without_obligations_rejected():
    with pytest.raises(ContractError, match="no obligations"):
        make()


def test_check_method_vocabulary():
    for m in ("solver", "property", "test", "integration", "e2e", "telemetry"):
        make(post=["result >= lo"], method=m)
    with pytest.raises(ContractError):
        make(post=["result >= lo"], method="vibes")


def test_semantics_vocabulary():
    with pytest.raises(ContractError, match="semantics"):
        make(post=["result >= lo"], semantics="float64")


def test_route_must_be_non_solver_and_name_real_obligations():
    make(post=["result >= lo"], route={"post-1": "test", "default": "integration"})
    with pytest.raises(ContractError, match="non-solver"):
        make(post=["result >= lo"], route={"post-1": "solver"})
    with pytest.raises(ContractError, match="unknown obligation"):
        make(post=["result >= lo"], route={"nope": "test"})


def test_approved_change_needs_reason():
    with pytest.raises(ContractError, match="reason"):
        make(post=["result >= lo"], approved_change={"scope": ["preconditions"]})


def test_pure_contract_cannot_declare_mutable_frame():
    with pytest.raises(ContractError, match="frame"):
        make(post=["result >= lo"], frame=["balances"])


def test_contract_ids_unique_and_never_reused(tmp_path):
    a, b = clamp_contract(cid="C-A-001"), clamp_contract(cid="C-A-001")
    assert check_ids([a, b])
    assert check_ids([clamp_contract(cid="C-A-002")], retired_ids=["C-A-002"])
    assert not check_ids([clamp_contract(cid="C-A-003")], retired_ids=["C-A-002"])


def test_bad_contract_id():
    with pytest.raises(ContractError, match="contract_id"):
        make(post=["result >= lo"], cid="nodash")
