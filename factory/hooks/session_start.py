"""``session_start`` (SessionStart, TB-11): give a new session the current ticket's ledger summary.

``decide`` always allows. ``emit`` returns ``load_summary`` of the ledger of the ticket named by
``.factory/current_ticket``, or the single line ``No ticket is active.`` when there is no ticket
or no ledger file for it.
"""
from __future__ import annotations

from factory.hooks.core import Decision, HookError, Payload
from factory.ledger import LedgerError, current_ticket, load_summary

NO_TICKET = "No ticket is active."


def decide(payload: Payload, cfg) -> Decision:
    return Decision("allow")


def emit(payload: Payload, cfg) -> str:
    try:
        ticket = current_ticket(cfg.project_root)
        if ticket is None:
            return NO_TICKET + "\n"
        path = cfg.ledger_dir / f"{ticket}.md"
        if not path.is_file():
            return NO_TICKET + "\n"
        return load_summary(path) + "\n"
    except LedgerError as exc:
        raise HookError(str(exc)) from None
