# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 5 traps (ephemeral port exhaustion and file-descriptor exhaustion from report seed PERF-05;
  container memory limit and OOM kill; thread or process per request; page cache counted as free memory).
- All 5 verified against Linux kernel documentation, Linux man-pages and RFC 9293 quotes.
- Required statements: memory-budget-per-worker and concurrency-model (both never_out_of_scope: physics).
- Cases: a planted and clean twin per trap, plus an omission case and clean twin per required statement.
- Report claims not carried: "65,535 ports" (the Linux default ephemeral range is 32768-60999), "60-120 s"
  TIME_WAIT and "locks up within 3 seconds" (unconfirmed; compute from the brief's rate).
