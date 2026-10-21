# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 5 traps (seeds DIST-02 and DIST-05 plus extras for isolation anomalies, monotonic-key hot
  partitions and secondary-index read-after-write), 4 required statements (consistency-model tagged
  never_out_of_scope consensus-trust), 12 cases (5 planted/clean pairs, one omission case with its clean
  twin).
- Verified (primary quotes present on refresh): all 5 traps. The CAP trap cites Gilbert and Lynch (2012)
  because the 2002 proof could not be fetched as text, and Abadi's 2010 post as the originator's first
  statement of PACELC (the 2012 IEEE paper is JavaScript-only).
- Speed-of-light round-trip figures from the seed report are left to physics arithmetic or measurement.
