# Changelog

## 0.2.0 - 2026-10-15
- Widen applies_when with phrasings of autonomous agent action ("agent can", "agent will", "agent may", "on its own", "without human approval", "without confirmation"). The clinic-intake-assistant integration case described an agent refunding on its own with an admin key and the planner skipped this lens.

## 0.1.0 - 2026-10-14
- Initial lens: agent loops, irreversible agent actions, retries, credential scope, delegation and audit.
- Traps (6): unbounded-agent-loop (AGT-01), irreversible-action-without-gate (AGT-02), non-idempotent-retry,
  standing-broad-credentials, delegation-without-least-privilege, no-action-audit-trail.
- All 6 verified on 2026-10-14 against OWASP Top 10 for LLM Applications 2025 (LLM06, LLM10), the MCP
  specification (tools, overview, security best practices) and RFC 9110 section 9.2.2.
- Required statements: loop-budget, irreversible-actions, credential-scope (never_out_of_scope
  agent-action-safety), action-audit.
- Cases: a planted and clean twin per trap, one omission case per required statement, one complete clean brief.
- The report's EU AI Act linkage for AGT-02 is left to ai-regulation and not asserted here.
