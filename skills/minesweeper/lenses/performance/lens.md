---
id: performance
version: 0.1.0
title: Performance, queueing and unit economics
group: systems-performance
owner: sf
scope: >-
  Judges latency, throughput and cost claims: percentile targets without a load model, fan-out tail
  amplification, unbounded queues, metric cardinality, and data-transfer charges that scale with volume.
  Leaves kernel resource limits to os-systems, media buffer and frame-rate arithmetic to media-pipelines, and
  live-media transport to realtime-transport.
applies_when:
  signals: [latency, p99, p95, p50, percentile, response time, milliseconds, throughput, requests per second, rps, qps, per second, concurrent users, scale to, fan out, fan-out, microservice, downstream services, shards, queue, retry, egress, data transfer, cross-region, multi-region, nat gateway, bandwidth cost, telemetry, metric label, time series, observability, prometheus, dashboard load, service level]
required_statements:
  - id: load-model
    statement: The brief states the load model - peak arrival rate, payload size distribution and concurrency - that its performance targets must hold under.
    never_out_of_scope: physics
  - id: latency-slo-percentile
    statement: Every latency target names a percentile and where it is measured (for example p99 at the API edge).
    never_out_of_scope: physics
  - id: cost-ceiling-per-unit
    statement: The brief states a cost ceiling per unit (per user, request, device or GB) that infrastructure and data-transfer costs must stay under.
adapters: [web_page]
---

# Performance, queueing and unit economics

## Principles

- Tail latency at scale: temporary slow episodes that do not matter for one server dominate a large system,
  and tails grow with scale and utilization (tail-at-scale). A request waiting on n independent calls misses
  a per-call percentile p with probability 1 - p^n (calc.fanout_tail).
- Little's law: mean number in system = arrival rate x mean time in system, for a stationary system
  (little-1961). Overload is not stationary: unbounded queues grow without limit.
- Every unique label combination is a new time series; high-cardinality identifiers do not belong in labels
  (prometheus-naming).
- Data transfer is billed per GB/GiB: NAT gateway processing regardless of source or destination plus
  standard transfer, and inter-region transfer (aws-vpc-pricing, gcp-network-pricing). Prices are read at
  sweep time and passed to calc.egress_cost; never recalled or copied.
- Performance ratios and sizes are not quoted from anyone: compute with a calc check or design an experiment.

## Questions a sweeper asks of each claim

- Which percentile, measured where, under what rate, payload and concurrency?
- Does one user request wait on many calls? What is n, and what does calc.fanout_tail give?
- Where does excess work go when arrivals exceed capacity? Is every queue bounded, with a stated overflow
  behaviour and a retry budget?
- Which identifiers become metric labels? Are their value sets bounded?
- How many bytes cross a region, NAT or the internet per user per month, at what current price (cited,
  dated), against what cost ceiling per unit?
- Does the brief state a load model, a percentile and a cost ceiling? If not, raise the omission.

## Severity guidance

Fan-out SLO fallacies and unbounded queues under the brief's own load answer production-failure (high).
Transfer costs that scale past revenue answer material-exposure (high). Missing percentiles or load models,
and label cardinality at modest scale, are principal-reject (medium). A missing cost ceiling is medium unless
the brief moves large volumes, then high.

## Not this lens

- Ports, descriptors, threads, container memory: os-systems.
- Frame memory, bit depth and uncompressed frame rates: media-pipelines.
- Live media transport, jitter buffers, MTU: realtime-transport.
- Consistency and replication cost trade-offs: distributed-systems and databases.
- Whether the business can bear the cost at all: market-reality.
