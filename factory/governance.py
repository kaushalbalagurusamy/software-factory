"""
Invariant-Backed Governance Engine for Software Factory.
Codifies the Socratic Governance Matrix (One-Way vs. Two-Way Doors)
grounded in Unity-IR Semantic Deltas (ΔS), Systems Contracts, and AST analysis.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from compiler import (
        compute_semantic_delta,
        extract_uast,
        SemanticDelta,
        SymbolDelta,
        DeltaSeverity,
        VerificationStatus,
    )
    UNITY_AVAILABLE = True
except ImportError:
    UNITY_AVAILABLE = False


class DoorType(str, Enum):
    ONE_WAY = "ONE_WAY"  # Irreversible, high blast radius: requires Socratic debate and formal ADR
    TWO_WAY = "TWO_WAY"  # Reversible, local blast radius: autonomous high-velocity execution


class RiskCategory(str, Enum):
    CONCURRENCY_MUTATION = "CONCURRENCY_MUTATION"
    PURITY_DEGRADATION = "PURITY_DEGRADATION"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    PUBLIC_API_MUTATION = "PUBLIC_API_MUTATION"
    SCHEMA_MUTATION = "SCHEMA_MUTATION"
    SECURITY_AUTH_BOUNDARY = "SECURITY_AUTH_BOUNDARY"
    SYMBOL_REMOVAL = "SYMBOL_REMOVAL"
    LOCAL_REFACTOR = "LOCAL_REFACTOR"


@dataclass
class ArchitecturalRisk:
    """Represents an identified architectural risk or invariant modification."""
    door_type: DoorType
    category: RiskCategory
    symbol_id: Optional[str]
    description: str
    blast_radius: str
    requires_adr: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GovernanceReport:
    """Summary of governance audit across files or repositories."""
    door_type: DoorType
    risks: List[ArchitecturalRisk] = field(default_factory=list)
    semantic_delta: Optional[Any] = None
    adr_draft: Optional[str] = None

    @property
    def is_one_way_door(self) -> bool:
        return self.door_type == DoorType.ONE_WAY or any(r.door_type == DoorType.ONE_WAY for r in self.risks)

    def summary(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"GOVERNANCE AUDIT REPORT: [{'ONE-WAY DOOR' if self.is_one_way_door else 'TWO-WAY DOOR'}]")
        lines.append("=" * 60)
        for r in self.risks:
            prefix = "[!] ONE-WAY" if r.door_type == DoorType.ONE_WAY else "[*] TWO-WAY"
            lines.append(f"{prefix} [{r.category.value}] {r.symbol_id or 'global'}: {r.description}")
            lines.append(f"    Blast Radius: {r.blast_radius}")
        return "\n".join(lines)


class GovernanceEngine:
    """
    Audits source changes against the Socratic Governance Matrix.
    Uses Project Unity's SemanticDelta when available and complements with
    heuristic AST scans for schema, storage, and auth boundaries.
    """

    # Heuristics for non-code artifacts (SQL migrations, storage schemas, auth)
    SCHEMA_DESTRUCTIVE_PATTERNS = [
        re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
        re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
        re.compile(r"\bALTER\s+TABLE\s+.*\s+DROP\b", re.IGNORECASE),
    ]

    AUTH_BOUNDARY_PATTERNS = [
        re.compile(r"\b(jwt_secret|private_key|api_key|access_token)\b", re.IGNORECASE),
        re.compile(r"\b(password_hash|argon2|bcrypt|pbkdf2)\b", re.IGNORECASE),
        re.compile(r"\b(token_expiry|session_ttl|oauth_client_secret)\b", re.IGNORECASE),
    ]

    def __init__(self, templates_dir: Optional[Path] = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent.parent / "templates"
        self.templates_dir = templates_dir


    def audit_semantic_delta(self, delta: SemanticDelta) -> List[ArchitecturalRisk]:
        """Convert Unity SemanticDelta into classified architectural risks."""
        risks: List[ArchitecturalRisk] = []

        # 1. Check for removed symbols (Breaking Public API / Contract)
        for removed in delta.removed_symbols:
            risks.append(
                ArchitecturalRisk(
                    door_type=DoorType.ONE_WAY,
                    category=RiskCategory.SYMBOL_REMOVAL,
                    symbol_id=removed,
                    description=f"Symbol '{removed}' was removed, breaking potential external and inter-module dependencies.",
                    blast_radius="High: Upstream callers will encounter UnresolvedSymbol or AttributeError at runtime.",
                    requires_adr=True,
                    details={"removed_symbol": removed},
                )
            )

        # 2. Check each symbol delta
        for sym_id, sym_delta in delta.symbol_deltas.items():
            # Concurrency synchronization diff
            if sym_delta.concurrency_diff:
                old_c, new_c = sym_delta.concurrency_diff
                risks.append(
                    ArchitecturalRisk(
                        door_type=DoorType.ONE_WAY,
                        category=RiskCategory.CONCURRENCY_MUTATION,
                        symbol_id=sym_id,
                        description=f"Concurrency synchronization mutated from '{old_c}' to '{new_c}'.",
                        blast_radius="Critical: Potential race conditions, deadlocks, or unsynchronized shared-state corruption.",
                        requires_adr=True,
                        details={"old_concurrency": old_c, "new_concurrency": new_c},
                    )
                )

            # Purity degradation
            if sym_delta.purity_diff:
                old_p, new_p = sym_delta.purity_diff
                is_degradation = ("pure" in old_p and "impure" in new_p)
                door = DoorType.ONE_WAY if is_degradation else DoorType.TWO_WAY
                risks.append(
                    ArchitecturalRisk(
                        door_type=door,
                        category=RiskCategory.PURITY_DEGRADATION if is_degradation else RiskCategory.LOCAL_REFACTOR,
                        symbol_id=sym_id,
                        description=f"Function purity mutated from '{old_p}' to '{new_p}'.",
                        blast_radius="High: Introduces side-effects, state mutations, or I/O into previously deterministic code."
                        if is_degradation
                        else "Low: Local purity improvement.",
                        requires_adr=is_degradation,
                        details={"old_purity": old_p, "new_purity": new_p},
                    )
                )

            # Contract signature shifts
            if sym_delta.contract_diff:
                old_ct, new_ct = sym_delta.contract_diff
                risks.append(
                    ArchitecturalRisk(
                        door_type=DoorType.ONE_WAY,
                        category=RiskCategory.PUBLIC_API_MUTATION,
                        symbol_id=sym_id,
                        description=f"Contract signature altered: '{old_ct}' -> '{new_ct}'.",
                        blast_radius="Medium-High: Callers must update invocation parameters or return handling.",
                        requires_adr=True,
                        details={"old_contract": old_ct, "new_contract": new_ct},
                    )
                )

            # Precondition SMT counterexamples / failures
            for pre_diff in sym_delta.precondition_diffs:
                if not pre_diff.implication_holds:
                    risks.append(
                        ArchitecturalRisk(
                            door_type=DoorType.ONE_WAY,
                            category=RiskCategory.CONTRACT_VIOLATION,
                            symbol_id=sym_id,
                            description=(
                                f"Precondition contract weakened or regressed: '{pre_diff.old_expr}' "
                                f"does not imply '{pre_diff.new_expr}'."
                            ),
                            blast_radius="High: SMT solver synthesized counterexample or found invariant violation.",
                            requires_adr=True,
                            details={
                                "old_expr": pre_diff.old_expr,
                                "new_expr": pre_diff.new_expr,
                                "counterexample": pre_diff.counterexample,
                                "status": pre_diff.status.value,
                            },
                        )
                    )

            # Local execution step refactors (if no one-way door triggered on this symbol)
            if not sym_delta.is_one_way_door and sym_delta.execution_step_diffs:
                risks.append(
                    ArchitecturalRisk(
                        door_type=DoorType.TWO_WAY,
                        category=RiskCategory.LOCAL_REFACTOR,
                        symbol_id=sym_id,
                        description=f"Internal execution steps refactored ({len(sym_delta.execution_step_diffs)} changes).",
                        blast_radius="Low: Reversible local implementation refinement.",
                        requires_adr=False,
                    )
                )

        return risks

    def audit_source_pair(self, pre_path: Union[str, Path], post_path: Union[str, Path]) -> GovernanceReport:
        """Audit changes between two source files using Unity and pattern analysis."""
        pre_p = Path(pre_path)
        post_p = Path(post_path)

        risks: List[ArchitecturalRisk] = []
        semantic_delta = None

        if UNITY_AVAILABLE:
            try:
                semantic_delta = compute_semantic_delta(str(pre_p), str(post_p))
                risks.extend(self.audit_semantic_delta(semantic_delta))
            except Exception as e:
                risks.append(
                    ArchitecturalRisk(
                        door_type=DoorType.TWO_WAY,
                        category=RiskCategory.LOCAL_REFACTOR,
                        symbol_id=None,
                        description=f"Unity-IR lowering fallback: {e}",
                        blast_radius="Low: Analyzed via text heuristics.",
                        requires_adr=False,
                    )
                )

        # Non-AST heuristic scan on post content
        if post_p.exists():
            post_content = post_p.read_text(encoding="utf-8", errors="ignore")
            for pattern in self.SCHEMA_DESTRUCTIVE_PATTERNS:
                match = pattern.search(post_content)
                if match:
                    risks.append(
                        ArchitecturalRisk(
                            door_type=DoorType.ONE_WAY,
                            category=RiskCategory.SCHEMA_MUTATION,
                            symbol_id=None,
                            description=f"Destructive SQL migration detected: '{match.group(0)}'.",
                            blast_radius="Critical: Irreversible database state loss; requires table backup or expand-and-contract migration.",
                            requires_adr=True,
                        )
                    )

        door_type = DoorType.ONE_WAY if any(r.door_type == DoorType.ONE_WAY for r in risks) else DoorType.TWO_WAY
        adr_draft = None
        if door_type == DoorType.ONE_WAY:
            adr_draft = self.generate_adr_draft(
                risks=risks,
                title=f"Architectural Invariant Review: {post_p.name}",
                context=f"Automated scan detected {len([r for r in risks if r.door_type == DoorType.ONE_WAY])} One-Way Door invariant modifications.",
            )

        return GovernanceReport(
            door_type=door_type,
            risks=risks,
            semantic_delta=semantic_delta,
            adr_draft=adr_draft,
        )

    def generate_adr_draft(
        self,
        risks: List[ArchitecturalRisk],
        title: str = "Architectural Invariant Review",
        context: str = "",
    ) -> str:
        """Populate standardized ADR template for Socratic architectural debate."""
        one_way_risks = [r for r in risks if r.door_type == DoorType.ONE_WAY]
        drivers = [f"* Invariant Preservation: {r.description}" for r in one_way_risks]
        if not drivers:
            drivers = ["* General system stability and contract preservation."]

        adr_template_file = self.templates_dir / "adr-template.md"
        template_text = ""
        if adr_template_file.exists():
            template_text = adr_template_file.read_text(encoding="utf-8")
        else:
            template_text = (
                "# {title}\n\n* **Status:** Proposed\n\n## 1. Context and Problem Statement\n{context}\n\n"
                "## 2. Decision Drivers\n{drivers}\n\n## 3. Considered Options\n* **Option 1:** Proceed\n* **Option 2:** Rollback\n\n"
                "## 4. Decision Outcome\nPending Socratic debate."
            )

        # Interpolate
        rendered = template_text
        rendered = rendered.replace("[Short Title of Solved Problem and Chosen Decision]", title)
        rendered = rendered.replace("{title}", title)
        rendered = rendered.replace(
            "[Describe the context and problem to be solved. Explain why an architectural decision is necessary.]",
            context or "High-blast-radius invariant mutation detected by Software Factory Governance Engine.",
        )
        rendered = rendered.replace("{context}", context or "High-blast-radius invariant mutation detected by Software Factory Governance Engine.")
        driver_block = "\n".join(drivers)
        rendered = re.sub(r"\* \[Driver 1.*?\n\* \[Driver 3.*?\]", driver_block, rendered, flags=re.DOTALL)
        rendered = rendered.replace("{drivers}", driver_block)
        return rendered

    # API alias for clarity
    evaluate_delta = audit_source_pair


