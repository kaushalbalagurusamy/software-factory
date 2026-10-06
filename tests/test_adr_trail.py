"""The ADR Decision Trail: template, seeding by the draft generator, and the fallback template."""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from factory.governance import (
    TRAIL_PLACEHOLDER_ROW,
    ArchitecturalRisk,
    DoorType,
    GovernanceEngine,
    RiskCategory,
)

ROOT = Path(__file__).resolve().parent.parent
FIXED = datetime.datetime(2026, 10, 6, 12, 0, tzinfo=datetime.timezone.utc)


def one_way(category: RiskCategory, symbol: str | None, description: str) -> ArchitecturalRisk:
    return ArchitecturalRisk(
        door_type=DoorType.ONE_WAY,
        category=category,
        symbol_id=symbol,
        description=description,
        blast_radius="High",
        requires_adr=True,
    )


def columns(row: str) -> int:
    """Count cells in a markdown table row, ignoring escaped pipes."""
    return len(re.split(r"(?<!\\)\|", row.strip())) - 2


def test_template_has_trail_section_matching_the_code():
    text = (ROOT / "templates" / "adr-template.md").read_text(encoding="utf-8")
    assert "## 6. Decision Trail" in text
    assert "### Gate Records" in text
    assert TRAIL_PLACEHOLDER_ROW in text


def test_draft_seeds_one_auto_row_per_one_way_risk():
    risks = [
        one_way(RiskCategory.CONCURRENCY_MUTATION, "ledger.Ledger.transfer", "Lock changed from exclusive to none."),
        one_way(RiskCategory.SYMBOL_REMOVAL, None, "Symbol removed.\nCallers break | badly."),
    ]
    draft = GovernanceEngine().generate_adr_draft(risks, title="Ledger review", context="ctx", now=FIXED)

    assert TRAIL_PLACEHOLDER_ROW not in draft
    rows = [line for line in draft.splitlines() if line.startswith("| ") and "| auto |" in line]
    assert len(rows) == 2
    assert rows[0].startswith("| 1 | 2026-10-06 12:00 | auto | governance audit | tool: sf audit | ")
    assert "CONCURRENCY_MUTATION on ledger.Ledger.transfer" in rows[0]
    assert "SYMBOL_REMOVAL on global" in rows[1]
    assert "badly" in rows[1] and "\\|" in rows[1]
    assert "\n" not in rows[1]
    header = next(line for line in draft.splitlines() if line.startswith("| # |"))
    assert all(columns(r) == columns(header) for r in rows)


def test_draft_keeps_the_gate_record_block_for_the_human_step():
    draft = GovernanceEngine().generate_adr_draft(
        [one_way(RiskCategory.PUBLIC_API_MUTATION, "api.create", "Signature changed.")], now=FIXED
    )
    assert "### Gate Records" in draft
    assert "**Feedback (verbatim):**" in draft


def test_only_one_way_risks_are_recorded():
    two_way = ArchitecturalRisk(
        door_type=DoorType.TWO_WAY,
        category=RiskCategory.LOCAL_REFACTOR,
        symbol_id="x.y",
        description="Local refactor.",
        blast_radius="Low",
        requires_adr=False,
    )
    draft = GovernanceEngine().generate_adr_draft(
        [two_way, one_way(RiskCategory.SCHEMA_MUTATION, None, "DROP TABLE.")], now=FIXED
    )
    rows = [line for line in draft.splitlines() if "| auto |" in line and line.startswith("| ") and "governance audit" in line]
    assert len(rows) == 1
    assert "LOCAL_REFACTOR" not in draft.split("## 6. Decision Trail")[1]


def test_no_one_way_risks_leaves_the_placeholder_for_the_author():
    draft = GovernanceEngine().generate_adr_draft([], now=FIXED)
    assert TRAIL_PLACEHOLDER_ROW in draft


def test_fallback_template_also_carries_the_trail(tmp_path):
    engine = GovernanceEngine(templates_dir=tmp_path)  # no adr-template.md here
    draft = engine.generate_adr_draft(
        [one_way(RiskCategory.CONTRACT_VIOLATION, "m.f", "Precondition weakened.")], now=FIXED
    )
    assert "Decision Trail" in draft
    assert "| 1 | 2026-10-06 12:00 | auto | governance audit |" in draft
    assert TRAIL_PLACEHOLDER_ROW not in draft
