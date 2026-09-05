---
name: architectural-debate-and-decision-records
description: >-
  Facilitates a collaborative, Socratic architectural debate between the agent and the human
  for one-way doors (database schemas, auth models, API contracts, vector store dimensions).
  Balances execution intelligence with deep alignment, analyzing trade-offs, and authoring
  formal Architecture Decision Records (ADRs) before committing to high-blast-radius decisions.
---

# Architectural Debate & Decision Records (ADR) Protocol

## 1. Philosophy: Alignment Without Bureaucracy

Autonomous AI agents possess vast technical knowledge across distributed systems, framework idioms, and performance trade-offs, but **lack invisible business context, risk tolerance boundaries, and long-term organizational intent**. Conversely, human engineers understand domain constraints but can be overwhelmed by implementation details.

This skill creates a **high-leverage collaborative bridge**:
* **Autonomous on Two-Way Doors:** The agent is empowered to move fast, implement localized logic, and iterate without needless permission gates.
* **Socratic on One-Way Doors:** When an irreversible architectural fork is reached, the agent pauses to present concrete trade-offs, explore failure modes, and debate the decision with the human before codifying it into an ADR.

---

## 2. Trigger Heuristics: One-Way vs. Two-Way Doors

```
                   Decision Point Encountered
                               │
            Is reversing this decision cheap and isolated?
                     /                  \
                   Yes                   No (One-Way Door)
                   /                      \
        [Two-Way Door]             [Activate This Skill]
  - Internal UI component layout    - Database schema & normalization
  - Helper utility function refactor - Vector embedding dimension (e.g. 768 vs 1536)
  - Ephemeral cache TTL tweak       - Authentication / RBAC security model
  - Localized CSS / styling         - Public / cross-service API contracts
  ──▶ Execute Autonomously          ──▶ Trigger Socratic Debate
```

### Mandatory Activation Triggers:
1. **Data Modeling & Storage:** Creating or altering relational tables, foreign key constraints, document collections, or partitioning strategies.
2. **Embedding & AI Pipelines:** Selecting vector dimensionality, distance metrics (Cosine vs. Dot Product vs. L2), or index strategies (HNSW vs. IVFFlat).
3. **Security & Identity:** Implementing authentication mechanisms, session token lifecycles, permission trees, or cryptographic storage.
4. **Interface Contracts:** Defining public HTTP/REST, gRPC, or GraphQL endpoints that external clients will depend on.

---

## 3. The 4-Phase Socratic Debate Workflow

### Phase 1: Trade-Off Analysis & Option Generation
When encountering a one-way door, synthesize 2–3 viable architectural paths. For each path, analyze:
* **Behavior:** Transactional guarantees (ACID vs. BASE), consistency models, data lifecycle.
* **Scale & Latency:** Behavior under $10\times$ and $100\times$ current load; write amplification; index maintenance cost.
* **Failure Modes:** Timeout handling, partition tolerance, cascading failures.
* **Evolutionary Cost:** Difficulty of migration 18 months from now.

### Phase 2: Interactive Socratic Debate
Present the choices concisely using the interactive `ask_question` tool or structured modal:
* **Frame the Core Conflict:** Avoid generic descriptions. Highlight the specific architectural tension (e.g., *"Single-table inheritance simplifies queries but risks wide sparse rows vs. Class-table inheritance gives strict typing but requires multi-table JOINs on reads."*).
* **Provide Concrete Recommendations:** State a recommended default grounded in the current codebase's trajectory, but explain what constraints would favor the alternatives.
* **Incorporate User Directives:** Allow the human to supply domain nuance, traffic projections, or compliance requirements.

### Phase 3: ADR Generation
Once consensus is reached, generate an Architecture Decision Record in `docs/adr/NNNN-<title>.md`:

```markdown
# NNNN. Selection of PostgreSQL with pgvector for Document Search

## Status
Accepted

## Context
We require semantic search across 100,000+ technical articles with sub-50ms query latency while maintaining strict relational foreign-key integrity to user organization models.

## Decision Drivers
* Need for transactional consistency between document metadata and embedding vectors.
* Team expertise in PostgreSQL operations; avoidance of standalone vector DB infrastructure overhead.
* Embedding model outputs fixed 1536-dimensional vectors (text-embedding-3-small).

## Considered Options
1. PostgreSQL with `pgvector` (HNSW indexing)
2. Dedicated Pinecone / Qdrant cluster + Postgres metadata sync
3. Elasticsearch with Dense Vector field

## Decision Outcome
Chosen Option: Option 1 (PostgreSQL with `pgvector`).
Eliminates distributed dual-write synchronization bugs between separate datastores while providing sufficient HNSW query throughput for current and medium-term volume.

## Consequences & Trade-offs
* Positive: Single backup/restore pipeline, unified ACID transactions, zero extra SaaS cost.
* Negative: Requires tuning PostgreSQL `shared_buffers` and `maintenance_work_mem` for HNSW build operations.
```

### Phase 4: Downstream Execution Handoff
With the ADR committed, proceed to test-driven implementation. All subsequent code edits MUST align with the constraints articulated in the accepted ADR.
