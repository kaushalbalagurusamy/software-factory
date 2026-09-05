# Master Engineering Curriculum
### Backend Security + System Design — Blended Track
**All examples in TypeScript · Updated April 16, 2026**

---

## How to Use This Document

This is the single source of truth for the learning track. Topics marked ⬜ are pending. Work through sections in order — each one builds on the last.

---

## Progress Overview

| # | Topic | Status | Section |
|---|-------|--------|---------|
| 1 | Authentication & Identity | ⬜ Pending | Security |
| 2 | Authorization | ⬜ Pending | Security |
| 3 | Middleware Guards | ⬜ Pending | Security |
| 4 | SQL — Normalization | ⬜ Pending | Databases |
| 5 | SQL — Subqueries & CTEs | ⬜ Pending | Databases |
| 6 | SQL — Indexes & Performance | ⬜ Pending | Databases |
| 7 | SQL — Views & Stored Procedures | ⬜ Pending | Databases |
| 8 | SQL — Connection Pooling | ⬜ Pending | Databases |
| 9 | PostgreSQL Specific Features | ⬜ Pending | Databases |
| 10 | Document Databases — MongoDB | ⬜ Pending | Databases |
| 11 | Key-Value Databases — Redis & DynamoDB | ⬜ Pending | Databases |
| 12 | Column-Wide Databases — Cassandra | ⬜ Pending | Databases |
| 13 | Search — Elasticsearch & Vector Databases | ⬜ Pending | Databases |
| 14 | CAP Theorem & Consistency Models | ⬜ Pending | System Design |
| 15 | CORS | ⬜ Pending | Security / API |
| 16 | Rate Limiting | ⬜ Pending | Security / API |
| 17 | API Key Management | ⬜ Pending | Security / API |
| 18 | HTTPS / TLS Enforcement | ⬜ Pending | Security / API |
| 19 | Data Protection | ⬜ Pending | Security |
| 20 | Input Validation & Injection Attacks | ⬜ Pending | Security |
| 21 | Infrastructure & Hardening | ⬜ Pending | Security |
| 22 | OWASP Top 10 | ⬜ Pending | Security |
| 23 | Scalability — Vertical vs Horizontal | ⬜ Pending | System Design |
| 24 | Latency vs Throughput | ⬜ Pending | System Design |
| 25 | Reliability, Fault Tolerance & SPOF | ⬜ Pending | System Design |
| 26 | Network Protocols — HTTP, TCP/UDP, WebSockets, gRPC | ⬜ Pending | System Design |
| 27 | Load Balancers — Nginx, HAProxy, L4/L7 | ⬜ Pending | System Design |
| 28 | CDN — Content Delivery Networks | ⬜ Pending | System Design |
| 29 | Database Sharding & Replication | ⬜ Pending | Databases |
| 30 | Message Queues — Kafka & RabbitMQ | ⬜ Pending | System Design |
| 31 | Microservices vs Monolithic Architecture | ⬜ Pending | System Design |
| 32 | Event-Driven Architecture | ⬜ Pending | System Design |
| 33 | API Design — RESTful & GraphQL | ⬜ Pending | System Design |
| 34 | Object-Oriented Design & UML | ⬜ Pending | Design |
| 35 | Case Study — URL Shortener | ⬜ Pending | Case Studies |
| 36 | Case Study — Social Network Feed | ⬜ Pending | Case Studies |
| 37 | Case Study — Video Streaming | ⬜ Pending | Case Studies |
| 38 | Case Study — Chat System | ⬜ Pending | Case Studies |
| 39 | Case Study — Ride Sharing | ⬜ Pending | Case Studies |

---

## Section 1 — Backend Security

### 1. Authentication & Identity

**Core idea:** Authentication answers "Who are you?" before the server does anything else.

**What's covered:**
- JWT — header.payload.signature, signed not encrypted, never store sensitive data in payload
- Session Management — server-side state, HttpOnly cookies, Redis store
- JWT vs Sessions — sessions better for sensitive data (instant revocation), JWT better for scale
- JWT + Redis blacklist — store userId with TTL matching token expiry, Redis auto-cleans
- OAuth 2.0 / OpenID Connect — Google token used ONCE to verify identity, your own JWT takes over
- ID token vs access token — ID proves identity, access token calls Google APIs, discard unless needed
- MFA — TOTP, 6-digit codes via authenticator app, verify against stored secret

**Key insights:**
- 401 = unauthenticated (who are you), 403 = unauthorized (you can't do this)
- HttpOnly cookie — JS cannot read it, blocks XSS theft entirely
- Google's access token never leaves your server
- Short-lived JWT (15min) + long-lived refresh token = best of both worlds

---

### 2. Authorization

**Core idea:** Authorization answers "What are you allowed to do?" — separate from authentication.

**The four layers:**
1. Route level — can they reach this endpoint at all?
2. Permission level — can they perform this specific action?
3. Resource ownership — do they own this specific record?
4. Field level — what parts of the data can they see or write?

**Key concepts:**
- RBAC — permissions defined as action strings: `patient:read`, `task:write`
- IDOR — Insecure Direct Object Reference, user guesses another user's resource ID
- 404 not 403 when resource exists but user has no rights — never confirm existence to attacker
- Strip sensitive fields server-side — never rely on frontend to hide data
- Middleware factory — `requirePermission('task:write')` returns a configured middleware

---

### 3. Middleware Guards

**Core idea:** Functions that sit between the request and route handler. Can inspect, modify, stop, or pass along the request.

**How next() works:**
- `next()` — passes control and shared req object to the next function in the chain
- Sending a response without calling `next()` stops the chain entirely
- Never leave a code path that neither calls `next()` nor sends a response — request hangs forever
- req object is shared across the entire chain — attach data early, read it downstream

**Beyond auth — other middleware uses:**
- Rate limiting — throttle abusive requests, different limits per route
- Request validation — Zod schema validation before handler runs
- Audit logging — attach only to write routes, skip reads
- Context loading — fetch workspace and user once, attach to req, no repeat DB hits

**Typical chain:**
```
extractUser → requireAuth → requirePermission → validateBody → checkOwnership → auditLog → handler
```

---

### 4. CORS

**Core idea:** Browsers block cross-origin JavaScript requests by default. CORS lets servers selectively allow them.

**Key concepts:**
- Same Origin Policy — browser blocks requests to different protocol, domain, or port
- Origin = protocol + domain + port — all three must match
- Preflight — browser sends OPTIONS request before complex requests to ask permission
- Credentials — must be explicit on both server (`credentials: true`) and client (`withCredentials: true`)
- Wildcard `*` + credentials — does not work, must use specific origin
- CORS is browser-only — curl, Postman, server-to-server requests bypass it entirely

**Common mistakes:**
- Using `*` in production — any website can call your API via a user's browser
- Reflecting the Origin header back blindly — defeats the purpose
- Forgetting OPTIONS preflight handling — POST fails even when GET works
- `*` with credentials — browser blocks it, breaks silently

---

### 5. Rate Limiting

**Core idea:** Prevent abuse by limiting how many requests a client can make in a time window.

**Multiple levels:**
- Infrastructure level — Cloudflare, load balancer, blocks floods before hitting your server
- Application level — Express middleware, fine-grained per route per user
- Database level — connection pool limits

**Patterns:**
- Sliding window — sorted set with timestamps, window slides continuously
- Fixed window — counter with TTL, resets on schedule, good for token budgets
- Per-IP — for public unauthenticated routes
- Per-user — for authenticated routes, key off userId not IP
- Tiered — free vs pro vs enterprise get different limits

**Key details:**
- Redis backing required for multiple servers — otherwise each server has its own counter
- 429 Too Many Requests — not 403
- Always return Retry-After header so clients know when to retry
- Login and password reset routes get much stricter limits — prevent brute force

---

### 6. API Key Management

Not yet covered.

---

### 7. HTTPS / TLS Enforcement

Not yet covered.

---

### 8. Data Protection

- Password hashing — bcrypt, argon2, salt rounds, never store plaintext
- Encryption at rest vs in transit — AES, TLS, what each protects
- Secrets management — environment variables, vaults, rotation strategies

---

### 9. Input Validation & Injection Attacks

- SQL injection — parameterized queries, ORMs
- NoSQL injection — MongoDB operator injection
- XSS & CSRF — tokens, sanitization, SameSite cookies
- Input sanitization — Zod, class-validator, schema validation

---

### 10. Infrastructure & Hardening

- Helmet.js — HTTP security headers
- Dependency auditing — npm audit, Snyk
- Logging & anomaly detection
- Least privilege principle

---

### 11. OWASP Top 10

- Broken access control
- Cryptographic failures
- Injection
- Insecure design
- Security misconfiguration
- Vulnerable components
- Authentication failures
- Integrity failures
- Logging failures
- SSRF

---

## Section 2 — Databases

### 12. SQL — Normalization

**Normal forms:**
- 1NF — every cell holds exactly one value
- 2NF — every column depends on the whole primary key
- 3NF — every column depends directly on the key, not another non-key column

**Three anomalies normalization fixes:** update, deletion, insertion

**Denormalization** — intentional, only for proven performance reasons, usually reporting tables

---

### 13. SQL — Subqueries & CTEs

- Subquery — anonymous inline query, used in WHERE, FROM, or SELECT clause
- CTE — named with WITH keyword, reusable, chainable, dramatically more readable
- Recursive CTE — references itself, used for hierarchical data like org charts
- Subquery in SELECT clause — runs once per row, causes N+1 if not careful

---

### 14. SQL — Indexes & Performance

- B-Tree index — O(log n) vs full table scan O(n)
- Composite index — column order matters, leading column must be in WHERE clause
- EXPLAIN ANALYZE — Index Scan good, Seq Scan means missing index
- CONCURRENTLY — builds index without locking table, always use on production
- N+1 problem — one query per row, fix with batch fetch and lookup map

**Practical rules:**
- Always index foreign keys
- Index WHERE and ORDER BY columns
- Measure with EXPLAIN ANALYZE, never guess

---

### 15. SQL — Views & Stored Procedures

- Regular view — saved query, always fresh, no storage, no performance benefit
- Materialized view — stored result, instant reads, must refresh on schedule
- REFRESH CONCURRENTLY — keeps old data visible during refresh
- Stored procedure — logic inside DB, fewer round trips, harder to test and maintain

---

### 16. SQL — Connection Pooling

- Opening a connection costs 20-50ms — pooling reuses open connections
- Pool size — roughly 2x database CPU cores
- Pool exhaustion — pool too small or slow queries holding connections
- Connection leak — always release in finally block
- PgBouncer — connection pooler for multiple app servers

---

### 17. PostgreSQL Specific Features

- Table Partitioning — split massive tables, partition pruning, instant DROP of old partitions
- Row Level Security — database-enforced data isolation, multi-tenant safety net
- JSONB — JSON as binary, fully indexable, hybrid pattern with structured columns
- Listen/Notify — built-in pub/sub, combine with triggers for automatic events

---

### 18. Document Databases — MongoDB

- Self-contained JSON documents, flexible schema, no joins
- Schema flexibility is a double-edged sword — nothing enforces consistency
- Joins problem — bad at relational data, application-level joins = N+1
- MongoDB vs PostgreSQL JSONB — JSONB wins unless entire model is documents

---

### 19. Key-Value Databases

**Redis data structures:** String, Hash, List, Set, Sorted Set

**Key patterns:**
- Rate limiting — sliding window (sorted set) or fixed window (counter)
- Distributed lock — NX flag, atomic, one server gets it, others back off
- Redis + PostgreSQL — Redis guards the door, PostgreSQL keeps the books

**DynamoDB** — disk-based, fully managed, infinite scale, single table design, partition + sort key

---

### 20. Column-Wide Databases — Cassandra

- Design tables around queries, not data structure
- Partition key — which machine, must be in every WHERE clause
- CAP Theorem — Cassandra chooses availability + partition tolerance
- Eventual consistency — data propagates within milliseconds, brief stale window
- Tunable consistency — ONE, QUORUM, ALL
- Pre-aggregation — background jobs compute summaries, never scan raw events
- Never query without partition key — full cluster scan destroys performance

---

### 21. Search Databases

**Elasticsearch:**
- Inverted index — keyword matching, full text search, relevance scoring, aggregations
- Always paired with PostgreSQL as source of truth
- ELK stack — industry standard logging

**Vector Databases:**
- Embeddings — numerical representations of meaning, not just words
- Use for — semantic search, RAG, recommendations, image similarity
- pgvector — zero extra infrastructure, works up to ~10M vectors
- Purpose-built — Pinecone, Qdrant, Weaviate for massive scale

---

### 22. Database Sharding & Replication

- Sharding — horizontal partitioning across multiple database servers
- Replication — primary/replica pattern, read scaling, failover
- Sharding strategies — range, hash, directory-based
- Replication lag — consistency implications

---

## Section 3 — System Design

### 23. CAP Theorem & Consistency Models

- Strong consistency — every read gets the most recent write
- Eventual consistency — data propagates over time, brief stale window acceptable
- Weak consistency — no guarantees, fire and forget
- CAP — pick two of: Consistency, Availability, Partition Tolerance

---

### 24. Scalability — Vertical vs Horizontal

- Vertical scaling — bigger machine, more RAM/CPU, has a ceiling
- Horizontal scaling — more machines, requires stateless design
- Stateless services — required for horizontal scaling, session state in Redis not in memory
- Auto-scaling — spin up/down based on load

---

### 25. Latency vs Throughput

- Latency — time for one request to complete
- Throughput — number of requests handled per second
- Optimizing one can hurt the other
- P50, P95, P99 latency — why averages lie

---

### 26. Reliability, Fault Tolerance & SPOF

- SPOF — Single Point of Failure, any component whose failure takes down the system
- Redundancy — multiple instances of critical components
- Fault tolerance — system continues operating when components fail
- Health checks and circuit breakers

---

### 27. Network Protocols

- HTTP/HTTPS — request/response, stateless
- TCP vs UDP — reliability vs speed tradeoff
- WebSockets — persistent bidirectional connection, real-time use cases
- gRPC — binary protocol, faster than REST, used in microservices
- Long polling vs Server-Sent Events vs WebSockets

---

### 28. Load Balancers

- L4 load balancing — TCP level, routes by IP and port
- L7 load balancing — HTTP level, routes by URL, headers, content
- Algorithms — round robin, least connections, IP hash
- Nginx, HAProxy — common implementations
- Health checks — remove unhealthy servers automatically
- Sticky sessions — when and why to avoid them

---

### 29. CDN — Content Delivery Networks

- Edge nodes — servers geographically close to users
- Cache static assets globally — JS, CSS, images, video
- Cache invalidation strategies — TTL, versioned URLs, manual purge
- CDN for API responses — when it makes sense and when it doesn't

---

### 30. Message Queues — Kafka & RabbitMQ

- Asynchronous processing — decouple producers from consumers
- Kafka — distributed log, high throughput, replay events, event sourcing
- RabbitMQ — traditional message broker, routing, dead letter queues
- When to use queues vs synchronous calls
- At-least-once vs exactly-once delivery
- Consumer groups and partitions

---

### 31. Microservices vs Monolithic Architecture

- Monolith — single deployable unit, simpler to start, harder to scale independently
- Microservices — independently deployable services, complex but scalable
- When to split — bounded contexts, team ownership, independent scaling needs
- Service communication — REST, gRPC, message queues
- Service discovery, API gateways

---

### 32. Event-Driven Architecture

- Events as the source of truth
- Event sourcing — store events not state
- CQRS — Command Query Responsibility Segregation
- Pub/sub patterns
- Saga pattern — distributed transactions across services

---

### 33. API Design — RESTful & GraphQL

**REST:**
- Resource-based URLs, HTTP verbs, stateless
- Versioning strategies — URL vs header
- Pagination — cursor vs offset
- HATEOAS

**GraphQL:**
- Single endpoint, client specifies shape of response
- N+1 problem in GraphQL — dataloader pattern
- When GraphQL beats REST and when it doesn't

---

### 34. Object-Oriented Design & UML

- SOLID principles
- Design patterns — Factory, Singleton, Observer, Strategy, Repository
- UML — class diagrams, sequence diagrams
- Domain-driven design basics

---

## Section 4 — Case Studies

### 35. URL Shortener

Key problems: high read volume, unique ID generation, redirect speed
Databases involved: Redis for hot URLs, PostgreSQL for storage
Concepts: hashing, base62 encoding, caching strategy

---

### 36. Social Network Feed

Key problems: fan-out on write vs fan-out on read, timeline generation
Databases involved: Redis for feeds, Cassandra for posts, PostgreSQL for social graph
Concepts: pub/sub, denormalization for speed, celebrity problem

---

### 37. Video Streaming

Key problems: large file serving, adaptive bitrate, global delivery
Databases involved: CDN for video chunks, PostgreSQL for metadata
Concepts: video chunking, HLS/DASH protocols, CDN strategy

---

### 38. Chat System

Key problems: real-time delivery, message ordering, presence
Databases involved: Cassandra for messages, Redis for presence, WebSockets
Concepts: persistent connections, fan-out, message queues

---

### 39. Ride Sharing

Key problems: geospatial queries, real-time location, matching
Databases involved: Redis GeoSearch for nearby drivers, PostgreSQL for trips
Concepts: Quadtree, GeoHash, WebSockets for location updates

---

## Key Terms Master Reference

| Term | Definition |
|------|-----------|
| JWT | JSON Web Token — signed token carrying user data |
| HttpOnly Cookie | Cookie JS cannot read — blocks XSS token theft |
| TOTP | Time-based One-Time Password — 6-digit MFA codes |
| OAuth 2.0 | Authorization framework for third-party login |
| OIDC | OpenID Connect — identity layer on top of OAuth |
| RBAC | Role-Based Access Control |
| IDOR | Insecure Direct Object Reference |
| Middleware | Function between request and route handler |
| Context Loading | Fetch shared data once early, attach to req |
| CORS | Cross-Origin Resource Sharing |
| Same Origin Policy | Browser blocks cross-origin JS requests by default |
| Preflight | OPTIONS request browser sends before complex requests |
| 429 | HTTP status — Too Many Requests |
| Rate Limiting | Throttle requests per time window |
| Distributed Lock | Redis NX flag — ensures only one server runs an operation |
| 1NF / 2NF / 3NF | First, Second, Third Normal Form |
| CTE | Common Table Expression — named subquery with WITH |
| N+1 Problem | One query per row instead of one query for all rows |
| EXPLAIN ANALYZE | PostgreSQL command showing query execution details |
| Seq Scan | Full table scan — usually means missing index |
| Index Scan | Used an index — fast |
| CONCURRENTLY | Build index or refresh view without locking |
| Materialized View | Stored query result — fast reads, needs refresh |
| Connection Pool | Reused open DB connections — avoids 20-50ms open cost |
| PgBouncer | Connection pooler for multiple app servers |
| Table Partitioning | Split massive table into physical chunks |
| Partition Pruning | Query only touches relevant partition |
| Row Level Security | Database-enforced data isolation per row |
| JSONB | PostgreSQL binary JSON with full index support |
| CAP Theorem | Pick two: Consistency, Availability, Partition Tolerance |
| Eventual Consistency | Data propagates over time, brief stale window |
| Distributed Lock | Atomic Redis operation preventing double processing |
| Embedding | Numerical vector representing meaning of data |
| Semantic Search | Find by meaning, not just keyword matching |
| pgvector | PostgreSQL extension adding vector search |
| Sharding | Horizontal partitioning across multiple DB servers |
| Replication | Primary/replica copies for read scaling and failover |
| SPOF | Single Point of Failure |
| Latency | Time for one request to complete |
| Throughput | Requests handled per second |
| WebSocket | Persistent bidirectional browser-server connection |
| gRPC | Binary protocol, faster than REST, microservices |
| CDN | Content Delivery Network — edge nodes close to users |
| Kafka | Distributed event log — high throughput, replayable |
| CQRS | Command Query Responsibility Segregation |
| Event Sourcing | Store events not state — full history always available |
| Fan-out | One event triggers writes to many recipients |

---
