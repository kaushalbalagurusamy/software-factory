# RFC: [System / Feature Name]

* **Author(s):** [Author Name / Agent]
* **Status:** Draft | Under Review | Approved | Implemented
* **Created:** YYYY-MM-DD
* **Target Release:** [Version / Milestone]

---

## 1. Objective & Scope
[High-level summary of what system or feature is being designed, the user impact, and non-goals.]

## 2. High-Level Architecture
[Describe the system topology and data flow.]

```
[Client / UI] ──HTTP/JSON──▶ [API Gateway / FastHandler]
                                     │
                                     ▼
                          [Core Domain Service]
                            ├── Postgres (State & Metadata)
                            └── Redis (Cache & Rate Limiting)
```

## 3. Data Models & Schemas
```typescript
// Define key data contracts and discriminated unions
export interface EntityModel {
  id: string;
  tenant_id: string;
  status: 'active' | 'archived';
  created_at: string;
}
```

## 4. Scaling, Latency & I/O Considerations
* **Query Latency Target:** $p95 < 100\text{ms}$
* **Throughput Target:** 1,000 requests/sec
* **Caching Strategy:** Cache-aside pattern via Redis with 5-minute TTL.

## 5. Failure Modes & Resilience
| Failure Scenario | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| Database connection pool saturated | HTTP 500 errors | Exponential backoff retry, circuit breaker |
| Upstream LLM provider latency spike | Worker timeouts | Async queue dispatch + WebSocket notification |

## 6. Testing & Eval Plan
* Unit test coverage threshold: $\ge 85\%$
* Boundary analysis & negative test cases
* Deterministic eval benchmark for LLM output schemas
