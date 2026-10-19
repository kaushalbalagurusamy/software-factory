"""``ledger_audit`` (SubagentStop, TB-11): record each sub-agent stop in the ticket's Audit Trail.

``decide`` always allows. ``record`` appends an entry (role ``orchestrator``) with the agent type,
the agent id and the first 200 characters of the last message, secret-shaped values removed first
(C-25), to the ledger of the ticket named by ``.factory/current_ticket``. With no current ticket
or no ledger file it does nothing (C-24).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from factory.hooks.core import Decision, HookError, Payload
from factory.ledger import LedgerError, append, current_ticket

MESSAGE_LIMIT = 200
REDACTED = "[REDACTED]"

_PATTERNS = tuple(re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----)?",
    r"sk-or-v1-[0-9a-fA-F]{20,}",
    r"sk-ant-[A-Za-z0-9_-]{20,}",
    r"sk-[A-Za-z0-9]{32,}",
    r"(?:ghp_|gho_|ghs_|github_pat_)[A-Za-z0-9_]{20,}",
    r"glpat-[A-Za-z0-9_-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"AIza[A-Za-z0-9_-]{35,}",
))
# a quoted value of 16+ characters assigned to a name containing api_key, apikey, secret, token or password
_ASSIGN = re.compile(
    r"""(?i)(\b[\w.-]*(?:api_key|apikey|secret|token|password)[\w.-]*["']?\s*[:=]\s*)(["'])[^"'\n]{16,}\2""")


def redact(text: str) -> str:
    """Replace secret-shaped values (the TB-07 shapes) with ``[REDACTED]``."""
    for pat in _PATTERNS:
        text = pat.sub(REDACTED, text)
    return _ASSIGN.sub(lambda m: m.group(1) + REDACTED, text)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def decide(payload: Payload, cfg) -> Decision:
    return Decision("allow")


def record(payload: Payload, cfg) -> None:
    try:
        ticket = current_ticket(cfg.project_root)
    except LedgerError as exc:
        raise HookError(str(exc)) from None
    if ticket is None:
        return
    path = cfg.ledger_dir / f"{ticket}.md"
    if not path.is_file():
        return
    message = redact(payload.last_assistant_message or "")[:MESSAGE_LIMIT]
    message = message.replace("\r", " ").replace("\n", " ")  # one line, so it cannot imitate ledger structure
    text = (f"agent_type: {payload.agent_type or 'unknown'}\n"
            f"agent_id: {payload.agent_id or 'unknown'}\n"
            f"last_message: {message}")
    try:
        append(path, "Audit Trail", "orchestrator", text, _now())
    except LedgerError as exc:
        raise HookError(str(exc)) from None
