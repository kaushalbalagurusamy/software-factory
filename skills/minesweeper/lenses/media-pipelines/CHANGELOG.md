# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 3 traps (decoded frames exceed worker memory, PERF-01; HDR quantized to 8-bit, PERF-02;
  uncompressed bandwidth between stages).
- Verified: decoded-frames-exceed-memory (Linux cgroup v2 memory.max quote; arithmetic by calc.memory).
- Unverified: hdr-quantized-to-8bit and uncompressed-bandwidth; ITU-R BT.2100 parameter tables are only in a
  PDF the web_page adapter cannot read.
- Required statements: media-format and memory-budget-per-worker (never_out_of_scope: physics).
- Checks: calc.memory, calc.bandwidth. Cases: planted and clean twins per trap, omission and clean twins
  per required statement.
