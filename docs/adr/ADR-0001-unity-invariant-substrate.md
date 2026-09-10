# ADR-0001: Dual-Plane Architecture & Invariant-First Intermediate Representation (Unity-IR)

* **Status:** Accepted
* **Date:** 2026-09-09
* **Authors:** Kaushal Balagurusamy & Project Unity Working Group
* **Deciders:** Software Factory Core Engineering

---

## 1. Context and Problem Statement
Autonomous code generation across large, multi-file codebases suffers from severe attention dilution and context degradation when models ingest raw polyglot source code. Traditional mitigations rely on "extrinsic panopticon surveillance"—wrapping models in synthetic test generators, runtime eBPF sandboxes, and multi-agent review boards. As demonstrated by 2025–2026 empirical studies (SWE-bench Verified saturation, Berkeley *EvilGenie* on reward-hacking), this produces tautological test debt, multi-agent coordination collapse (4x–220x token inflation), and reviewer exhaustion over massive syntax diffs.

## 2. Decision Drivers
* **Intrinsic Correctness:** Eliminate reward-hacking and tautological mock tests by shifting to algebraic invariant preservation.
* **Token Efficiency & Recall:** Reduce context token consumption by 40%–60% over multi-file repositories.
* **Polyglot Parity:** Eliminate performance disparities across dynamic languages (Python) and systems languages (Go, Rust).
* **Reviewer Efficiency:** Enable sub-second human review via Canonical Semantic Deltas ($\Delta \mathcal{S}$).

## 3. Considered Options
* **Option 1: Raw Source Ingestion + Vector RAG / Repo Maps** (Standard Aider/Cursor approach).
* **Option 2: Code Property Graph (CPG) Databases** (Graph RAG / Neo4j / Joern).
* **Option 3: Dual-Plane Architecture with Canonical Invariant-First IR (Unity-IR)**.

---

## 4. Decision Outcome
**Chosen Option:** **Option 3**, because Unity-IR decouples cognitive reasoning from lexical syntax via a deterministic 3-layer schema (Systems Contracts, Algorithmic Logic, and Causal Topology). High-order planning and review occur on the Cognitive Plane, while code execution occurs on the Substrate Plane.

### Positive Consequences
* **Deterministic Semantic Grounding:** Correctness becomes an algebraic property of pre/post conditions and concurrency scopes.
* **Reviewer Asymmetry Solved:** Reviewers audit $\Delta \mathcal{S}$ state mutations rather than hundreds of lines of syntactic boilerplate.
* **Zero Translation Hallucination:** Lowering is performed strictly by deterministic compiler passes (Tree-sitter), never by probabilistic LLMs.

### Negative Consequences & Mitigations
* **Compiler Frontend Overhead:** Requires building and maintaining Tree-sitter lowering frontends for supported languages.
  * *Mitigation:* Focus initial proof strictly on a dual-anchor wedge (Python + Go) before expanding to Rust and C++.

---

## 5. Pros and Cons of the Options

### Option 1: Raw Source Ingestion + Vector RAG
* Good: Zero upfront compiler engineering; uses existing text-based tools.
* Bad: Suffers from lost-in-the-middle attention dilution; high token costs; language distribution skew.

### Option 2: Code Property Graph Databases
* Good: Precise AST/CFG/PDG graph traversals.
* Bad: 2–10s query latency per hop; brittle Cypher generation; expensive database re-indexing on rapid commits.

### Option 3: Dual-Plane Architecture (Unity-IR)
* Good: Fast (<100ms) deterministic lowering; 40%+ token reduction; language-agnostic invariant parity; mathematically verifiable via SMT solvers (Z3).
* Bad: Requires initial compiler engineering and formal grammar specification.
