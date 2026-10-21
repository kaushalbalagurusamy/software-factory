---
id: distributed-systems
version: 0.1.0
title: Distributed systems, consensus and fault models
group: distributed-data
owner: sf
scope: >-
  Judges brief claims about agreement, coordination, locking, ordering and delivery among networked
  nodes: fault and trust models (crash versus Byzantine), quorum sizing, impossibility results (FLP,
  common knowledge / two generals), leases and fencing, clock-based ordering, and delivery semantics.
  Data-store consistency, isolation and partitioning claims belong to the databases lens.
applies_when:
  signals:
    - consensus
    - raft
    - paxos
    - zookeeper
    - etcd
    - quorum
    - leader election
    - replica
    - byzantine
    - distributed lock
    - lease
    - fencing
    - split-brain
    - failover
    - heartbeat
    - gateway
    - relay
    - edge node
    - peer-to-peer
    - exactly once
    - exactly-once
    - at-least-once
    - idempotenc
    - message broker
    - message queue
    - last-write-wins
    - last write wins
    - offline-first
    - clock
    - simultaneous
required_statements:
  - id: fault-model
    statement: >-
      The brief states the fault model: whether participants may only crash or may behave arbitrarily
      (Byzantine), and how many simultaneous faults f must be tolerated.
    never_out_of_scope: byzantine-faults
  - id: trust-boundary
    statement: >-
      The brief states which nodes, relays and operators are trusted, and how messages and membership
      are authenticated.
    never_out_of_scope: consensus-trust
  - id: delivery-semantics
    statement: >-
      The brief states message delivery and retry semantics (at-most-once or at-least-once) and the
      idempotency key that makes retries safe.
  - id: ordering-guarantees
    statement: >-
      The brief states what ordering is guaranteed (per key, per source, total, causal) and what assigns
      it (a log sequence, logical clocks), rather than relying on wall-clock time.
adapters: [web_page, paper]
---

# Distributed systems, consensus and fault models

## Principles

- Crash-fault-tolerant consensus (Raft, Paxos) keeps consistency only under non-Byzantine faults and
  progresses while a majority is up: n >= 2f+1 (`raft-site`, `lamport-pubs`).
- A faulty node that sends inconsistent information defeats any three-processor algorithm; in general
  3f+1 processors are needed to tolerate f faults, and 2f+1 with unforgeable signatures under synchrony
  (`lamport-pubs`). For asynchronous networks 3f+1 is optimal (`pbft-osdi99`), and BFT assumes
  independent failures and authenticated messages (`pbft-osdi99-model`).
- Deterministic consensus cannot guarantee termination in an asynchronous system with one crash;
  liveness needs a timing assumption (`flp-1985`, restated in `pbft-osdi99`).
- Over a lossy channel, common knowledge cannot be attained, so "both sides certain, then act together"
  is unachievable by any number of acks (`halpern-moses`, `lamport-pubs`).
- A lock holder's delayed request can arrive after the lock passed to another holder; the resource must
  check a sequencer / fencing token (`chubby-osdi06`).
- Events are only partially ordered by causality; physical timestamps from different clocks do not
  define that order (`lamport-pubs`).
- Exactly-once outside one system's boundary requires the destination's cooperation; the default is
  at-least-once (`kafka-semantics`).

## Questions a sweeper asks of each claim

- Who runs each node, and could any of them be compromised, buggy or physically tampered with? If yes,
  what is f, and does n satisfy n >= 3f+1 (`calc.bft_quorum`, `calc.bft_tolerates`)? If no, is
  n >= 2f+1 (`calc.cft_quorum`)?
- Are the failures independent, or do all replicas share firmware, keys or an operator?
- Are votes and readings signed by their originator, or do relays forward unauthenticated payloads?
  Is membership open?
- Does the brief promise progress "always", "never stalls", or within a deadline regardless of the
  network? Under what timing assumption?
- Does any requirement need two parties to be certain of each other's state before acting together?
- Is a lock or lease protecting a write to an external resource, and does that resource check a token?
- Is anything ordered or merged by timestamp? Whose clock?
- Does the brief say "exactly once"? Across which boundary, and what is the idempotency key?
- What happens in each component when a quorum, a heartbeat or an acknowledgement is lost?

## Severity guidance

- `harm-safety` answers yes when consensus or locking drives physical actuation, payments or medical
  state; a CFT protocol among possibly-compromised nodes in such a system is critical.
- `production-failure` answers yes for most traps here: the brief's own conditions (untrusted
  sites, lossy links, retries, process pauses) produce the failure.
- `principal-reject` fits impossibility promises (unconditional termination, certain simultaneity)
  where the realistic outcome is a spec that cannot be tested rather than a live incident.
- Lower the tier when the brief confines the claim to one trust domain, a single node, or a
  demonstration with no real effects; raise it when an adversary is named.

## Not this lens

- Replicated data consistency (CAP/PACELC), transaction isolation, dual writes across stores, hot
  partitions and secondary-index staleness: `databases`.
- Key management, signature schemes and nonce reuse behind message authentication: `cryptography`.
- Physical interlocks, actuator safety and control-loop timing: `cyber-physical`.
- Network latency budgets and bandwidth arithmetic: `performance` and `realtime-transport`.
- Multi-agent orchestration consensus between LLM agents: `agent-orchestration`.
