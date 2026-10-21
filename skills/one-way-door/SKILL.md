---
name: one-way-door
description: >-
  Use before any operation or decision that is hard or impossible to reverse: schema drops,
  destructive migrations, vector re-indexing or embedding-dimension choices, deleting cloud
  resources, changing a public API contract, authentication or encryption models. First checks
  the blast radius and designs a rollback path (a two-way door stops there, quickly). Only for a
  true one-way door does it run a Socratic trade-off debate with the human and author an
  Architecture Decision Record (ADR) before anything is committed.
---

# One-way door: blast-radius check, then decision record

Software changes vary in reversibility:
* **Two-way doors:** a broken helper or CSS rule is one `git revert` away. Move fast, no gate.
* **One-way doors:** dropping a table, changing a production vector dimension, deleting a bucket, or altering an external API contract causes data loss, client failure, or days of downtime.

Two phases, always in this order. Phase 1 is fast and runs every time. Phase 2 runs only when Phase 1 finds a one-way door.

```
Decision or risky operation encountered
        │
   Phase 1: door check (blast radius + rollback path)
        │
   Is reversing it cheap and isolated?
      /                    \
    Yes (two-way door)      No (one-way door)
     │                        │
  Proceed, autonomously     Phase 2: Socratic debate → ADR → implement against the ADR
```

---

## Phase 1: Door check

### Blast-radius classification

High blast radius (STOP and evaluate):
* SQL `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, or destructive migrations
* Re-indexing vector databases that require full corpus regeneration
* Deleting cloud storage buckets or primary database instances
* Removing or renaming fields in public API endpoints
* Changing cryptographic algorithms or secret encryption keys

### The 3-step check

**Step 1: Blast-radius calculation.** Answer before staging changes:
1. **Data impact:** is any existing data permanently destroyed or altered?
2. **Client impact:** will older mobile clients, external webhooks, or third-party integrations break?
3. **Recovery time objective (RTO):** if this fails in production, how long does recovery take?

**Step 2: Rollback strategy design.**
* **Expand-and-contract migration:** (1) Expand: add the new column or field beside the old one. (2) Dual write: write both, read the old. (3) Backfill existing data into the new field. (4) Switch reads to the new field. (5) Contract: deprecate and remove the old field after client adoption.
* **Soft deletion and snapshots:** use `deleted_at` timestamps or automated pre-migration snapshots before destructive operations.

**Step 3: Explicit human verification.** Present the blast radius and the drafted rollback plan to the human. Never run destructive CLI commands or migrations in unattended headless loops.

If the answers show the change is reversible and isolated, record that in one line and stop. The one line names the risk categories you checked and what each returned, because a two-way call is the one that skips the human. Autonomous calls with no ADR go in `docs/adr/AUTONOMY-LOG.md` only if the project has opted in; see `references/decision-trail.md`. Do not start a debate for a two-way door.

---

## Phase 2: Socratic debate and ADR (one-way doors only)

Agents know distributed systems, framework idioms and performance trade-offs, but lack invisible business context, risk tolerance and long-term organizational intent. Humans hold that context but can be swamped by implementation detail. So at a one-way door the agent pauses, presents concrete trade-offs, explores failure modes, and debates the choice before codifying it.

### Mandatory triggers
1. **Data modeling and storage:** creating or altering relational tables, foreign keys, document collections, partitioning strategies.
2. **Embedding and AI pipelines:** vector dimensionality, distance metric (cosine, dot product, L2), index strategy (HNSW, IVFFlat).
3. **Security and identity:** authentication mechanisms, session token lifecycles, permission trees, cryptographic storage.
4. **Interface contracts:** public HTTP/REST, gRPC or GraphQL endpoints that external clients will depend on.

Two-way examples that never need Phase 2: internal UI layout, a helper refactor, an ephemeral cache TTL tweak, localized styling.

### Step A: Trade-off analysis
Synthesize 2 to 3 viable paths. For each, analyze:
* **Behavior:** transactional guarantees (ACID vs BASE), consistency model, data lifecycle.
* **Scale and latency:** behavior at 10x and 100x current load; write amplification; index maintenance cost.
* **Failure modes:** timeout handling, partition tolerance, cascading failures.
* **Evolutionary cost:** difficulty of migrating 18 months from now.

### Step B: Interactive debate
Present the choices concisely, using the interactive question tool if available.
* **Frame the core conflict.** Name the specific tension, for example: single-table inheritance simplifies queries but risks wide sparse rows, while class-table inheritance gives strict typing but needs multi-table JOINs on reads.
* **Give a concrete recommendation** grounded in the codebase's trajectory, and say which constraints would favor the alternatives.
* **Take the human's input:** domain nuance, traffic projections, compliance requirements.

### Step C: Write the ADR
When consensus is reached, write `docs/adr/NNNN-<title>.md`:

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

### Step C2: Keep the decision trail
The ADR says what was decided. Section 6 of the ADR (the Decision Trail) says how: which steps an agent or tool took without pausing (`auto`), where the process paused for a human (`gate`), and when an earlier decision was reopened (`reopen`). Record each gate with what the human was shown, what you knew they might not weigh, their words verbatim, and what changed because of them. Append only: never edit or delete a row, and never rebuild a trail from memory for an ADR written before this section existed. Field list, rules, and a worked example: `references/decision-trail.md`.

### Step D: Handoff to implementation
With the ADR committed, proceed test-first. All later code edits must align with the accepted ADR.
