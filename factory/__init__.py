"""
Software Factory: Autonomous Engineering Substrate with Intrinsic Semantic Parity.
"""

from .governance import (
    GovernanceEngine,
    GovernanceReport,
    ArchitecturalRisk,
    DoorType,
    RiskCategory,
)
from .zero_trust import (
    ZeroTrustGate,
    ZeroTrustReport,
    BaselineHashGuard,
    BaselineVerificationResult,
)
from .cli import main

__all__ = [
    "GovernanceEngine",
    "GovernanceReport",
    "ArchitecturalRisk",
    "DoorType",
    "RiskCategory",
    "ZeroTrustGate",
    "ZeroTrustReport",
    "BaselineHashGuard",
    "BaselineVerificationResult",
    "main",
]
