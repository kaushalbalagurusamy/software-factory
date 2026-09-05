---
name: spec-driven-tractability-testing
description: >-
  Designs contract-first, feature-oriented test suites emphasizing tractability, boundary
  verification, failure mode injection, and deterministic eval metrics before feature coding.
  Replaces ungrounded "vibe checks" with deterministic test harnesses and measurable benchmarks.
---

# Spec-Driven Tractability & Evals Protocol

## 1. Intent & Rationale
A common AI engineering failure is relying on "vibe checks"—generating a feature and glancing at a successful UI render or a single mock run. This produces fragile systems that break under unhandled edge cases, malformed payloads, or non-deterministic model outputs.

This skill establishes a **Contract-First & Deterministic Eval Protocol**:
1. **Contract Definition:** Formally define the inputs, outputs, and invariant rules using strongly-typed schemas (e.g., Pydantic V2, TypeScript Discriminated Unions, Rust structs).
2. **Failure-Mode Injection:** Author tests for error boundaries, network drops, and corrupted responses *before* implementing the happy path.
3. **Deterministic AI Evals:** Evaluate non-deterministic LLM pipelines against deterministic structural schemas, semantic bounds, and regression suites.

---

## 2. Test Architecture: The 4-Tier Verification Matrix

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Contract & Schema Validation (Pydantic / Zod / Type System)        │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Unit & Boundary Tests (Edge cases, nulls, max limits, unicode)     │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Failure Mode & Resilience Tests (Timeouts, dropped connections)     │
├────────────────────────────────────────────────────────────────────────┤
│ 4. Deterministic AI Evals (Structural validation, semantic thresholds) │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Practical Implementation Guidelines

### A. Contract-First Schema Design
Before writing business logic, define strict schemas:
```python
# Python Example with Pydantic V2
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, List

class AgentExecutionEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    status: Literal["pending", "running", "completed", "failed"]
    duration_ms: int = Field(ge=0)
    retry_count: int = Field(default=0, ge=0, le=5)
    metadata: dict = Field(default_factory=dict)
```

### B. Failure-Mode & Edge-Case Injection
Ensure the test suite explicitly covers:
* **Payload Extremes:** Empty strings, massive payloads (>10MB), unusual UTF-8/emoji characters, unexpected `null` or `undefined` keys.
* **Network & RPC Errors:** Simulated `503 Service Unavailable`, `429 Rate Limited` with exponential backoff verification, and partial socket disconnections.
* **State Machine Invariants:** Attempting invalid state transitions (e.g., transitioning an order from `cancelled` to `shipped`).

### C. Deterministic Evals for LLM Components
When testing an AI-powered component, avoid loose assertions like `assert len(response) > 0`. Instead, implement 3 deterministic checks:
1. **Structural Conformance:** Validate that the output parses cleanly into the target schema without missing keys.
2. **Deterministic Constraint Checks:** Verify that forbidden tokens or sensitive leakages never occur.
3. **Semantic Scoring:** Compare embeddings against ground-truth evaluation datasets with clear pass/fail cosine similarity thresholds (e.g., $\ge 0.85$).

---

## 4. Execution Workflow

1. **Step 1 (Spec & Contract):** Write the interface and schemas in the designated types/contracts module.
2. **Step 2 (Red Test Suite):** Write comprehensive unit and failure-mode tests in `tests/` and verify they fail for the intended reasons.
3. **Step 3 (Green Implementation):** Implement the core logic until all tests pass cleanly.
4. **Step 4 (Regression & Coverage):** Run the complete test runner (`pytest`, `cargo test`, `vitest`, etc.) and ensure zero regressions across the codebase.
