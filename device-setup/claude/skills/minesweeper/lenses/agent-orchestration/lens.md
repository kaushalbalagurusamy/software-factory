---
id: agent-orchestration
version: 0.2.0
title: Agent orchestration and agent action safety
group: agents-cyber-physical
owner: sf
scope: >-
  Judges briefs that let LLM agents loop, call tools, delegate to other agents or act on external
  systems: loop budgets and halting, irreversible actions and their approval or compensation path,
  idempotent retries, credential scope, delegation privilege and the audit trail of agent actions.
  Prompt-injection mechanics and model supply chain belong to agent-security; AI-specific law
  (for example human-oversight duties for high-risk systems) belongs to ai-regulation.
applies_when:
  signals:
    - ai agent
    - llm agent
    - autonomous agent
    - agentic
    - multi-agent
    - multiagent
    - sub-agent
    - subagent
    - planner agent
    - critic agent
    - agent loop
    - agents collaborate
    - swarm of agents
    - orchestrator agent
    - agent orchestration
    - tool call
    - tool use
    - function calling
    - mcp server
    - model context protocol
    - acts autonomously
    - autonomously
    - iterate until
    - self-healing
    - auto-remediat
    - on behalf of the user
    - computer use
    - browser agent
    - agent can
    - agent will
    - agent may
    - on its own
    - without human approval
    - without confirmation
required_statements:
  - id: loop-budget
    statement: The brief states each agent loop's iteration cap, token or cost ceiling and wall-clock limit, and the halting condition that stops the loop when the goal is not reached (with the hand-off that follows).
    never_out_of_scope: agent-action-safety
  - id: irreversible-actions
    statement: The brief lists which agent actions are irreversible or externally visible (payments, refunds, deletions, outbound messages, deploys, physical actuation) and, for each, the human approval gate and the compensation or idempotency path.
    never_out_of_scope: agent-action-safety
  - id: credential-scope
    statement: The brief states which credentials each agent and sub-agent holds, their scope and lifetime, and whose authority each action is executed under.
    never_out_of_scope: agent-action-safety
  - id: action-audit
    statement: The brief states that agent tool calls, their arguments, the acting identity and their outcomes are recorded in a log that operators can review.
adapters: [web_page]
---

# Agent orchestration and agent action safety

This lens applies to the sweep itself: the minesweeper loop has a pass cap, a wall-clock limit,
a routed-call cap and a repeat halt (policy.yaml `budget`). Hold briefs to the same standard.

## Principles

1. **Every loop needs a budget and a halting condition that does not depend on the goal being
   reached.** "Until the critic is satisfied" or "until tests pass" is a goal, not a stop rule. An
   LLM application that allows uncontrolled inference invites denial of service and economic loss;
   the mitigations are timeouts, throttling and caps on queued and total actions
   (owasp-llm10-unbounded-consumption; mcp-spec-tools "Implement timeouts for tool calls").
   Vendor guidance also recommends stopping conditions such as an iteration cap
   (anthropic-building-effective-agents, secondary).
2. **High-impact actions need a human gate outside the model.** Excessive Agency is damage done
   in response to unexpected, ambiguous or manipulated model output, whatever the cause; the
   mitigation is human approval of high-impact actions (owasp-llm06-excessive-agency). MCP says a
   human SHOULD be able to deny tool invocations and hosts must obtain consent before invoking
   tools (mcp-spec-tools, mcp-spec-overview).
3. **Retries of side-effecting calls must be idempotent.** A client should not automatically
   retry a non-idempotent request unless it knows the semantics are idempotent or can detect that
   the original was never applied (rfc9110-idempotent). Agents retry a lot.
4. **Least privilege, per user and per task.** An agent acting for one user must not hold a
   generic high-privileged identity; permissions are minimised and enforced downstream, not by
   the model (owasp-llm06-excessive-agency; mcp-spec-security-best-practices scope minimisation).
5. **Delegation does not pass authority wholesale.** A compromised peer agent is a named trigger
   of Excessive Agency; tokens are not passed through to services they were not issued for, and
   authorisation is complete mediation in the downstream system (owasp-llm06-excessive-agency;
   mcp-spec-security-best-practices token passthrough).
6. **Agent actions are logged with the acting identity.** Logging and monitoring limit damage;
   token passthrough and omnibus scopes destroy attribution (owasp-llm06-excessive-agency;
   mcp-spec-security-best-practices).

## Questions a sweeper asks of each claim

- What stops this loop if the goal is never met? Is there an iteration, token/cost and time cap,
  and is a repeated identical tool call treated as a halt?
- Which tool calls change the world outside the process (money, data deletion, messages, deploys,
  infrastructure, actuators)? For each: who approves, what undoes it, what makes a retry safe?
- Whose credential does each call use, what can it reach, and how long does it live?
- When agent A spawns agent B, what authority does B get, and who checks each action?
- Could an operator reconstruct, after an incident, which agent did what under which identity?
- Is the model itself deciding whether an action is permitted?

## Severity guidance

- Irreversible external actions (refunds, deletions, outbound messages, deploys, actuation)
  driven by model output with no gate: `harm-safety` or `severe-security` usually answer yes, so
  critical or high. Physical actuation through an agent raises it to critical and pulls in the
  cyber-physical lens.
- Unbounded loops: `material-exposure` (unbounded spend) or `production-failure`, so high.
- Broad standing credentials and delegation without narrowing: `severe-security` (privilege
  escalation, exfiltration), so high.
- Missing audit trail alone: `principal-reject`, so medium, raised when another trap here is
  present because it removes the ability to detect it.
- A read-only agent with no external side effects lowers most of these to medium or low.

## Not this lens

- Prompt injection techniques, tool-description poisoning, model and plugin supply chain:
  agent-security and supply-chain.
- Statutory human-oversight or logging duties for AI systems: ai-regulation.
- Agents that write to industrial controllers or safety systems: cyber-physical (both apply).
- Cost per token and unit economics of the product: market-reality and performance.
