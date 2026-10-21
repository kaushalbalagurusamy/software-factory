# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 7 traps (seeds DIST-01, DIST-03, DIST-04, DIST-06 plus extras for unauthenticated relays,
  FLP termination promises and exactly-once delivery), 4 required statements (fault-model and
  trust-boundary tagged never_out_of_scope byzantine-faults / consensus-trust), 16 cases (7 planted/clean
  pairs, one omission case with its clean twin).
- Verified (primary quotes present on refresh): cft-in-byzantine-setting, unauthenticated-relay,
  two-generals-simultaneous-action, lock-without-fencing-token, wall-clock-ordering, exactly-once-delivery.
- Unverified: consensus-guaranteed-termination; the FLP paper (DOI 10.1145/3149.214) could not be fetched
  as text.
- Correction to the seed report: 3f+1 is the bound for asynchronous systems and unsigned messages; with
  unforgeable signatures under synchrony 2f+1 suffices (Pease, Shostak, Lamport). Fencing tokens are
  sourced to the Chubby sequencer, not to a blog.
