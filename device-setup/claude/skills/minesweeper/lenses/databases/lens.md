---
id: databases
version: 0.1.0
title: Databases, replication consistency and transactions
group: distributed-data
owner: sf
scope: >-
  Judges brief claims about stored data: replication consistency across regions (CAP, PACELC),
  transaction atomicity across stores (dual writes, outbox), isolation-level anomalies, key and
  partition design, and secondary-index freshness. Consensus protocols, fault models, locks and
  message ordering belong to the distributed-systems lens.
applies_when:
  signals:
    - database
    - postgres
    - mysql
    - sql
    - transaction
    - isolation
    - serializable
    - consistency
    - linearizab
    - replication
    - multi-region
    - cross-region
    - shard
    - partition key
    - primary key
    - secondary index
    - auto-increment
    - kafka
    - outbox
    - change data capture
    - cache
    - search index
    - read-after-write
    - eventual
    - ledger
    - double booking
    - double-booking
required_statements:
  - id: consistency-model
    statement: >-
      The brief states the consistency model required for each class of data (linearizable,
      read-your-writes, eventual with a staleness bound).
    never_out_of_scope: consensus-trust
  - id: partition-behaviour
    statement: >-
      The brief states what the system does when replicas or regions cannot reach each other: reject or
      queue writes, or accept divergent writes and how they are merged.
  - id: isolation-level
    statement: >-
      The brief states the transaction isolation level, or the mechanism that enforces each multi-row
      invariant under concurrent access.
  - id: cross-store-atomicity
    statement: >-
      Where one operation updates more than one store (database, broker, cache, index), the brief states
      how they are kept consistent (outbox, change data capture, saga) and the idempotency key consumers
      use.
adapters: [web_page, paper]
---

# Databases, replication consistency and transactions

## Principles

- Consistency, availability and partition tolerance trade off; all three cannot be had
  (`gilbert-lynch-2012`). Without a partition, a replicated system still trades latency against
  consistency (PACELC, `abadi-pacelc-blog`).
- A transaction is all-or-nothing within one database (`pg-transactions`); effects on another system
  need that system's cooperation (`kafka-semantics`). A handler that writes two stores is a dual write.
- Read Committed is PostgreSQL's default; Repeatable Read still allows serialization anomalies, results
  that match no serial order (`pg-isolation`). ANSI phenomena do not fully characterise isolation
  levels (`berenson-1995`).
- Monotonic keys on a range-partitioned store send all inserts to one server (`spanner-schema`).
- Global secondary indexes may be updated asynchronously and read only eventually consistently
  (`dynamodb-gsi`); check the chosen store's own documentation.

## Questions a sweeper asks of each claim

- For each data class: what consistency does the brief demand, across which regions, at what latency,
  and what must happen during a partition? Is the latency target below the round trip a synchronous
  quorum needs (route to physics arithmetic or an experiment)?
- Does any handler write the database and also a broker, cache, index or external API? What happens
  if the process dies between the two?
- Which invariants span multiple rows (balances, capacity, uniqueness, staffing)? What enforces them
  under concurrency, at which isolation level, and is there a retry on serialization failure?
- What is the primary key of each write-heavy table, and is the store range-partitioned?
- Does any correctness decision read through a secondary or global index right after a write?
- Does a vendor's consistency claim rest on its own documentation, and has an independent test
  (for example a published Jepsen analysis) found violations? Treat such reports as evidence about that
  specific version only.

## Severity guidance

- `production-failure` usually answers yes: concurrency, partitions and crashes are the brief's own
  production conditions.
- `material-exposure` answers yes when the anomaly moves money or inventory (overdrafts, double
  bookings, lost orders).
- `harm-safety` answers yes when the stored state drives clinical, safety or physical decisions.
- `principal-reject` fits hot-partition and index-freshness designs whose failure is degradation or
  confusing reads rather than corruption.
- Lower the tier for a single-node database with no replication, or a prototype with no concurrent
  writers, if the brief says so.

## Not this lens

- Consensus protocols, fault models, quorum sizing, locks, leases and fencing, clock ordering, delivery
  semantics: `distributed-systems`.
- Storage capacity, memory and bandwidth arithmetic: `performance`.
- Retention, deletion and personal-data duties of stored records: `privacy-regulated-data`.
- Floating-point money and numeric precision in schemas: `numeric-representation`.
