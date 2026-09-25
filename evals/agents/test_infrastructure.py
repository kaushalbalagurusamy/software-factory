"""Self-check of the eval infrastructure: a blocked case resolves to blocked, not pass."""
import pytest

from evals.agents import lib  # noqa: F401  (import check)


@pytest.mark.case("INFRA-D-001", tier="diagnostic", tb="00", reqs=["R-21"])
def test_missing_implementation_is_blocked():
    """R-21 / methodology: a case written before its producer exists resolves to blocked, never pass."""
    lib.need("factory.does_not_exist_yet", "anything")
    pytest.fail("need() must skip when the module is missing")
