# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 4 traps (live media over a reliable in-order stream, PERF-03; playback with no jitter buffer;
  datagrams above the path MTU; simultaneous translation promised ahead of its input, from PERF-03 prose).
- All 4 verified against RFC 9293, RFC 9000, RFC 3550, RFC 8085 and the STACL paper abstract (arXiv 1810.08398).
- Required statements: network-path and latency-budget (never_out_of_scope: physics).
- Checks: calc.payload_mtu. Cases: planted and clean twins per trap, omission and clean twins per required
  statement.
