"""QA supervisor loop: runtime state, feedback handoff, bounded retry and escalation.

This package never calls a model. It records outcomes, decides the next step and writes
contract-level feedback; the orchestrator launches the agents. See docs/qa-loop.md.
"""
