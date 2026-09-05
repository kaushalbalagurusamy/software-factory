---
name: scaling-and-io-bottleneck-analyzer
description: >-
  Audits and eliminates I/O bottlenecks, N+1 query cascades, unindexed database scans,
  unbounded list endpoints, memory leaks, and serialization overhead before code is merged.
  Ensures code scale-readiness from local prototypes to production high-concurrency systems.
---

# Scaling & I/O Bottleneck Analyzer Protocol

## 1. Intent & Rationale
AI code generators frequently produce code that behaves perfectly on small local datasets (e.g., 5 items) but degrades catastrophically under production loads (e.g., 50,000+ users). Common AI antipatterns include:
* Iterating through ORM instances in a Python/JS loop and executing an individual SQL query per item ($N+1$ query cascade).
* Missing compound database indexes on columns used in `WHERE`, `ORDER BY`, or `JOIN ON` clauses.
* Querying entire database rows (including massive text/JSON blobs) when only one ID or status field is needed.
* Blocking async event loops with heavy CPU operations or synchronous I/O.

---

## 2. The 5-Pillar I/O Audit Matrix

```
1. Query Efficiency     ──▶  Eliminate N+1 loops, enforce batching and JOINs
2. Index Optimization    ──▶  Index foreign keys, filter predicates, and sort columns
3. Pagination & Bounding ──▶  Strict cursor/offset limits; reject unbounded SELECT *
4. Network & Payload     ──▶  Lean serialization, strip private fields, enable compression
5. Async Event Loop      ──▶  Zero blocking synchronous calls in async handlers
```

---

## 3. Heuristic Rules & Code Patterns

### A. Database Query Optimization ($N+1$ Elimination)
* **Antipattern (Loop Query):**
  ```python
  # BAD: 1 query for users + N queries for orders
  users = db.query(User).all()
  for user in users:
      orders = db.query(Order).filter(Order.user_id == user.id).all()
  ```
* **Best Practice (Eager Load / Batching):**
  ```python
  # GOOD: 1 joined query or batch prefetch
  users = db.query(User).options(joinedload(User.orders)).all()
  ```

### B. Bounded Data Ingestion & Streaming
* Endpoints returning list representations MUST enforce a `max_limit` parameter (e.g., maximum 100 items per request).
* For large export operations or file downloads, stream data in chunks rather than buffering the entire payload in memory.

### C. Concurrency & Async Protection
* In Node.js, Python (AsyncIO / FastAPI), and Rust (Tokio):
  * **Never** call synchronous disk I/O, heavy crypto hashing, or long sleeps directly on the main event loop.
  * Use dedicated worker pools (`run_in_executor`, `spawn_blocking`, or background task queues).

### D. Serialization & Field Selection
* Explicitly project only needed columns in database queries (e.g., `SELECT id, name, status FROM users` instead of `SELECT *`).
* Exclude sensitive credentials, binary streams, and internal debug stacks from API payloads.

---

## 4. Verification & Profiling Steps

1. **Static Analysis:** Inspect ORM queries, foreign key relationships, and loops in diffs.
2. **Query Plan Inspection (`EXPLAIN ANALYZE`):** Verify that high-traffic queries utilize index scans rather than sequential full-table scans.
3. **Load Simulation:** Test endpoints with concurrent requests to verify connection pool health and response latency percentiles ($p95 < 150\text{ms}$).
