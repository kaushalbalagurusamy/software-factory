"""Deterministic checks a trap entry can name in its `checks` field.

Every check is read-only: it reads registry metadata or computes arithmetic, and never installs,
downloads or executes anything it is checking. Add a check by writing the function and listing it
here; lint fails on a trap that names a check missing from this table.
"""
from . import calc, licence, registry

CHECKS = {
    "registry.exists": registry.exists,
    "registry.age": registry.age,
    "registry.cross_registry": registry.cross_registry,
    "licence.family": licence.family,
    "licence.spdx": licence.spdx,
    "licence.package": licence.package,
    "licence.github": licence.github,
    "calc.memory": calc.memory,
    "calc.bandwidth": calc.bandwidth,
    "calc.fanout_tail": calc.fanout_tail,
    "calc.bft_quorum": calc.bft_quorum,
    "calc.bft_tolerates": calc.bft_tolerates,
    "calc.cft_quorum": calc.cft_quorum,
    "calc.egress_cost": calc.egress_cost,
    "calc.payload_mtu": calc.payload_mtu,
    "calc.birthday_collision": calc.birthday_collision,
}
