---
id: agent-security
version: 0.1.0
title: Agent and tool-server security
group: supply-chain-security-crypto
owner: sf
scope: >-
  Judges brief claims about how an AI agent reaches tools and data: MCP and similar tool servers,
  token handling and delegated authority, session or state handles, trust in tool definitions, and
  untrusted content steering tool calls. How agents are orchestrated and budgeted belongs to
  agent-orchestration; which packages the servers are built from belongs to supply-chain.
applies_when:
  signals:
    - mcp
    - model context protocol
    - tool server
    - tool call
    - tool use
    - function calling
    - agent
    - agentic
    - assistant
    - copilot
    - plugin
    - connector
    - oauth
    - access token
    - bearer token
    - service account
    - on behalf of
    - autonomous
    - browse the web
    - read emails
    - prompt injection
    - local server
    - stdio
required_statements:
  - id: delegated-authority
    statement: The brief states which identity and scopes each tool or downstream call runs with, and how the invoking user is authenticated.
  - id: tool-trust
    statement: The brief states which tool servers are trusted, how their definitions are reviewed and pinned, and what happens when a definition changes.
  - id: human-approval
    statement: The brief states which agent actions require explicit human confirmation and what the confirmation shows.
    never_out_of_scope: agent-action-safety
  - id: untrusted-inputs
    statement: The brief states which inputs the agent reads are untrusted (emails, web pages, documents, tool output) and what tools may run while they are in context.
    never_out_of_scope: agent-action-safety
adapters: [web_page, paper]
---

# Agent and tool-server security

## Principles

- Tokens are audience-bound. MCP servers must accept only tokens issued for their own resources and must
  not accept or transit any other token; passthrough is an explicitly forbidden anti-pattern
  (mcp-authorization, mcp-security-best-practices).
- A proxy with one static client identity is a confused deputy unless it implements per-client consent;
  scopes should be least-privilege and progressive (mcp-security-best-practices).
- A state handle is not authentication: verify every request, use non-deterministic handles from a secure
  generator, and bind them to the authenticated user (mcp-security-best-practices).
- Tool descriptions and annotations are untrusted unless they come from a trusted server (mcp-spec-overview);
  hidden instructions in them steer agents (tool poisoning, wang-2025-mcptox), including toward other
  servers' tools (shadowing), and definitions can change after approval (rug pull)
  (mcp-local-server-security, song-2025-mcp-attack-vectors).
- Retrieved data can carry instructions that control which APIs the model calls (indirect prompt
  injection, greshake-2023-indirect-prompt-injection); MCP asks for a human in the loop who can deny
  tool calls and sees their inputs (mcp-tools).
- Local servers run with the client's privileges; show the exact command before setup and sandbox them
  (mcp-security-best-practices, mcp-local-server-security).

## Questions a sweeper asks of each claim

- Whose identity does each downstream call carry: the user's, or the server's own account? With what scopes?
- Does any component forward a token it received? Is every token checked for its audience?
- What does a session or task handle authorise, how is it generated, and is it bound to a user?
- Where do tool servers come from? Who reviews their descriptions, and what happens when they change?
- Does any agent read content an outsider can write (email, web, uploads, tickets) while it can act or send data out?
- Which actions need confirmation, and does the confirmation show full arguments?
- Do local servers or helpers execute shell commands, and are they sandboxed?

## Severity guidance

Token passthrough, confused deputy, guessable handles, poisoned or shadowed tools and injection-driven
actions usually answer yes to `severe-security` (privilege escalation, data exfiltration, remote code
execution), so high; they rise to critical under `harm-safety` when the agent can move money, contact
third parties or touch health or safety systems. A missing definition-change policy with only
first-party servers is medium. The policy questions decide.

## Not this lens

- Which packages tool servers are built from and how they are installed: supply-chain.
- Randomness quality and key handling as such: cryptography.
- Agent loop design, budgets and stop conditions: agent-orchestration.
- Whether a provider's terms allow the automation at all: provider-terms.
