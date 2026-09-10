# ADR-0002: Epistemic Zero-Trust Verification Substrate via Z3, Deal, and CrossHair

* **Status:** Accepted
* **Date:** 2026-09-09
* **Authors:** Kaushal Balagurusamy & Software Factory Core Engineering
* **Deciders:** Software Factory Core Engineering

---

## 1. Context and Problem Statement
Autonomous AI agents tasked with both code implementation and test generation exhibit severe **reward-hacking behaviors** (Berkeley *EvilGenie*, 2026; *ImpossibleBench*, 2025). Rather than ensuring generalization, verifier agents co-adapt with generator agents, producing tautological unit tests that silently delete, weaken, or bypass failing edge-case assertions. Evaluating software purely by whether self-generated unit tests pass creates a dangerous illusion of correctness.

## 2. Decision Drivers
* **Tautological Elimination:** Prevent agents from generating self-validating mocks that ratify their own bugs.
* **Assertion Immutability:** Guarantee that existing test suites cannot be weakened or bypassed to "pass" a build.
* **Symbolic Grounding:** Use SMT solvers to mathematically prove contract satisfaction across all input spaces.
* **Compute-Normalized Efficiency:** Avoid multi-agent bureaucratic committees for code verification.

## 3. Considered Options
* **Option 1: Multi-Agent Review Panel** (PM -> Dev -> QA -> Reviewer agent swarms).
* **Option 2: Generative LLM Test Synthesis** (Agent writes implementation + Pytest suite in same frame).
* **Option 3: Epistemic Zero-Trust Gate via SMT (Z3), Contracts (Deal), and Symbolic Execution (CrossHair)**.

---

## 4. Decision Outcome
**Chosen Option:** **Option 3**, because decoupling test criteria from implementation and grounding verification in SMT solvers and Design-by-Contract eliminates reward-hacking at the structural level.

### Implementation Requirements:
1. **Cryptographic Baseline Locking:** Baseline test suites and invariant specifications are cryptographically hashed; any PR modifying an assertion without an approved ADR is automatically rejected.
2. **Design-by-Contract (`deal`):** Functions declare mathematical preconditions (`@deal.pre`), postconditions (`@deal.ensure`), and purity (`@deal.pure`).
3. **Symbolic Exploration (`crosshair-tool` / `z3-solver`):** CrossHair symbolically checks contract validity and synthesizes concrete counterexamples for bugs without manual test scripts.
4. **Property Fuzzing (`hypothesis`):** Pseudo-random adversarial distributions test invariant boundaries in CI.

### Positive Consequences
* **Immunity to Reward-Hacking:** Agents cannot game an SMT solver or symbolic execution engine.
* **Deterministic CI Pipeline:** Fast, reproducible, and verifiable in GitHub Actions without LLM API costs.
* **Defect Localization:** Counterexamples give the generator agent the exact input that failed, enabling instant repair.

### Negative Consequences & Mitigations
* **Computational Cost of Symbolic Execution:** Full symbolic execution on complex functions can timeout.
  * *Mitigation:* Set `--per_condition_timeout` bounds and fall back to Hypothesis property fuzzing if SMT paths exceed complexity caps.

---

## 5. Pros and Cons of the Options

### Option 1: Multi-Agent Review Panel
* Good: Mimics human engineering org charts.
* Bad: 4x–220x token inflation; degrades sequential reasoning by up to 70% (arXiv:2604.02460); agents still hallucinate and co-adapt.

### Option 2: Generative LLM Test Synthesis
* Good: Easy to prompt; creates human-readable Pytest files.
* Bad: Tautological test debt; models reward-hack by tailoring tests to their bugs.

### Option 3: Epistemic Zero-Trust Gate
* Good: Mathematically sound; impossible to game; automated counterexample generation; fast execution.
* Bad: Requires formal contract annotations (`deal`) on critical path code.
