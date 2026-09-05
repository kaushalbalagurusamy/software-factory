---
name: comprehension-debt-and-interface-auditor
description: >-
  Audits codebase modularity, enforces strict interface encapsulation (discriminated unions,
  abstract contracts), and prunes AI-generated PR bloat to ensure code remains human-auditable.
  Prevents comprehension debt and maintains institutional architecture knowledge over time.
---

# Comprehension Debt & Interface Auditor Protocol

## 1. Intent & Rationale
When AI models generate large volumes of code, human review bandwidth becomes the ultimate bottleneck. This leads to **Comprehension Debt**—a state where software runs, but no engineer on the team fully understands its internal logic, hidden assumptions, or state edge cases.

To eliminate comprehension debt without slowing execution velocity:
1. **Interface Encapsulation:** Expose lean, strongly-typed public interfaces (e.g., TypeScript Discriminated Unions, Rust Enums with Data, Pydantic schemas) while treating internal implementation as encapsulated modules.
2. **PR Bloat Pruning:** Reject unprompted whole-file rewrites and unnecessary architectural sprawl in favor of atomic, surgical changes.
3. **Intent Grounding:** Embed concise architectural docstrings explaining *why* a particular design was chosen, preserving context for future AI turns and human maintainers.

---

## 2. Core Interface Patterns

### A. Discriminated Unions for Complex State
Avoid loose boolean flags (e.g., `isLoading`, `isError`, `isSuccess`, `hasData`) that allow impossible states. Instead, use explicit discriminated unions:

```typescript
// TypeScript Example
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T; timestamp: number }
  | { status: 'error'; error: Error; retryCount: number };

function renderUI<T>(state: AsyncState<T>) {
  switch (state.status) {
    case 'idle': return <PromptPlaceholder />;
    case 'loading': return <LoadingSpinner />;
    case 'success': return <DataView data={state.data} />;
    case 'error': return <ErrorBanner error={state.error} />;
  }
}
```

### B. Minimal Public Surface Area
* Keep module internals private/unexported unless explicitly needed by external callers.
* Avoid leaky abstractions where database models or internal ORM entities are directly exposed to the HTTP presentation layer.

---

## 3. PR Bloat & Diff Minimization Rules

```
Diff Quality Checklist:
├── 1. Surgical Precision: Only lines related to the target feature/bug are touched.
├── 2. No Formatting Thrash: Linter/prettier settings do not reformat unrelated files.
├── 3. No Zombie Code: Dead code and obsolete commented-out blocks are deleted.
└── 4. Atomic Commits: The commit message clearly describes the intent and mechanism.
```

---

## 4. Architectural Docstring Standard
Every major module or service header should contain a concise intent block:
```python
"""
Module: VectorIndexer (src/indexer/pipeline.py)
Architectural Intent:
  Batches incoming text chunks, generates 1536-dim embeddings via text-embedding-3-small,
  and performs upserts into PostgreSQL pgvector using HNSW indexing.
Trade-offs:
  - Chooses bulk upserts (batch_size=100) to balance memory footprint vs network roundtrips.
  - See ADR 0004 for vector dimensionality and storage rationale.
"""
```
