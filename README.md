# Software Factory 🏭

[![CI](https://github.com/kaushalbalagurusamy/software-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/kaushalbalagurusamy/software-factory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A robust, modular framework of **Antigravity Skills, Architecture Decision Protocols, and Deterministic Testing Standards** engineered to transform AI coding assistants from ungrounded "vibe-coders" into high-judgment software co-architects.

---

## The Software Factory Manifesto

In the modern AI development loop, code velocity is no longer the bottleneck. When LLMs generate code without architectural grounding, they introduce compounding technical debt:
1. **1.7x Pull Request Defect Rate** through unhandled logic edge cases.
2. **2.74x Security Vulnerability Rate** due to missing sanitization, permissive RBAC, and unverified token lifetimes.
3. **8x I/O & Latency Bottlenecks** via naive $N+1$ ORM queries and unindexed table scans.
4. **Comprehension Debt** where codebases become unmaintainable black boxes.

### The Core Balance: Execution Freedom vs. Socratic Alignment

> **The Guiding Principle:**  
> Avoid hyper-rigid micro-rules that stifle the model's creative problem-solving on **two-way doors** (localized functions, UI styling, helper refactors).  
> Enforce deep, Socratic collaboration on **one-way doors** (schemas, security boundaries, vector dimensions, and public API contracts).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TWO-WAY DOORS                                    │
│  • Local UI components & styling                                            │
│  • Internal helper functions                                                │
│  • Ephemeral cache TTLs                                                     │
│  ──▶ Autonomous High-Velocity Execution                                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ONE-WAY DOORS                                    │
│  • Database schemas & storage paradigms (SQL vs NoSQL vs Graph)             │
│  • Vector dimensions & embedding models (e.g. 768 vs 1536)                   │
│  • Authentication, sessions & cryptographic boundaries                      │
│  • Public & cross-service API contracts                                     │
│  ──▶ Mandatory Socratic Architectural Debate + Formal ADR Ratification      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Skills Catalog

| Skill Name | Path | Primary Purpose |
| :--- | :--- | :--- |
| **`architectural-debate-and-decision-records`** | [`skills/architectural-debate-and-decision-records/SKILL.md`](skills/architectural-debate-and-decision-records/SKILL.md) | Socratic trade-off debate on one-way doors; authors formal Architecture Decision Records (ADRs). |
| **`spec-driven-tractability-testing`** | [`skills/spec-driven-tractability-testing/SKILL.md`](skills/spec-driven-tractability-testing/SKILL.md) | Contract-first schema design, failure-mode injection, and deterministic eval harnesses. |
| **`scaling-and-io-bottleneck-analyzer`** | [`skills/scaling-and-io-bottleneck-analyzer/SKILL.md`](skills/scaling-and-io-bottleneck-analyzer/SKILL.md) | Audits $O(N)$ query loops, unindexed scans, connection pooling, and payload bloat. |
| **`one-way-door-guard`** | [`skills/one-way-door-guard/SKILL.md`](skills/one-way-door-guard/SKILL.md) | Pre-flight safety check, blast-radius calculation, and rollback strategy design. |
| **`comprehension-debt-and-interface-auditor`** | [`skills/comprehension-debt-and-interface-auditor/SKILL.md`](skills/comprehension-debt-and-interface-auditor/SKILL.md) | Enforces discriminated unions, minimal public surface area, and prunes PR bloat. |

---

## Reusable Templates

* [`templates/adr-template.md`](templates/adr-template.md): Standardized format for recording Architecture Decision Records in `docs/adr/`.
* [`templates/system-design-rfc-template.md`](templates/system-design-rfc-template.md): High-level system design RFC template for complex systems.
* [`templates/deterministic-eval-template.py`](templates/deterministic-eval-template.py): Deterministic Pytest eval harness for structured LLM outputs.

---

## How to Mount in Antigravity CLI (AGY)

To mount these skills into your Antigravity environment:

### Option A: Global Installation
Copy the skills directory into your global Antigravity config:
```bash
cp -r skills/* ~/.gemini/config/skills/
```

### Option B: Project-Specific Installation
Symlink or copy the skills folder into your project's `.agents/skills/` directory:
```bash
mkdir -p .agents/skills
cp -r /path/to/software-factory/skills/* .agents/skills/
```

---

## License

[MIT License](LICENSE) © 2026 Kaushal Balagurusamy
