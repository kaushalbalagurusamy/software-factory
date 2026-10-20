# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 5 traps (fan-out tail amplification, PERF-04; egress unit economics and high-cardinality
  metric labels, PERF-06; unbounded queues; latency promise without a load model or percentile).
- All 5 verified: The Tail at Scale (authors' abstract; full text returned 403), Little 1961 (publisher
  abstract via Crossref; publisher page returned 403), Prometheus naming docs, AWS VPC and Google Cloud
  network pricing pages (terms, 30-day freshness; no price copied).
- Required statements: load-model, latency-slo-percentile (never_out_of_scope: physics), cost-ceiling-per-unit.
- Checks: calc.fanout_tail, calc.egress_cost. Cases: planted and clean twins per trap, omission and clean
  twins per required statement.
