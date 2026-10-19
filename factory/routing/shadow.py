"""Shadow routing log (TB-14, R-19): record what Jev would have chosen next to the actual choice.

Shadow only: the record is written for calibration and never read back to decide anything. The
line is the content-free :func:`factory.routing.jev_client.log_record` plus ``actual_choice`` and
``agrees``. ``result`` is duck-typed (C-33). Nothing here ever raises into the caller (C-27).
Documentation: ``docs/hooks/e2e.md``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from factory.routing.jev_client import log_record

LOG_NAME = "routing.jsonl"


def record(result: Any, actual_choice: Any, ledger_dir: Any, state_digest: str = "") -> None:
    """Append one JSON line to ``<ledger_dir>/routing.jsonl``; creates ``ledger_dir`` if missing."""
    try:
        line = {**log_record(result, state_digest), "actual_choice": actual_choice,
                "agrees": bool(result.choice == actual_choice)}
        text = json.dumps(line, allow_nan=False) + "\n"  # strict JSON, or the line is dropped
        directory = Path(ledger_dir)
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / LOG_NAME, "a", encoding="utf-8") as fh:
            fh.write(text)
    except Exception as exc:  # noqa: BLE001 - shadow logging must never affect the caller
        try:
            sys.stderr.write(f"shadow.record: not logged ({type(exc).__name__})\n")
        except Exception:  # noqa: BLE001
            pass
