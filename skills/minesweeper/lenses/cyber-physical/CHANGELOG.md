# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: OT write paths, safety interlocks, IT/OT zoning and vendor access, patching of live
  controllers, internal network monitoring, cloud control loops, NERC CIP and process-safety duties.
- Traps (8): standing-vendor-remote-access (CPS-01), unauthenticated-ot-write-path (CPS-02),
  unattended-patch-reboot (CPS-03), no-internal-network-monitoring (CPS-04), safety-interlock-bypass,
  cloud-hard-realtime-loop, flat-it-ot-network, bes-cip-deferred.
- Verified (6) on 2026-10-14 against 16 U.S.C. 824o and 825o-1, 18 CFR 40.2 and 385.1602, 29 CFR 1910.119,
  FERC Orders 850 and 907 (Federal Register via govinfo) and the CISA/FBI/EPA/DOE OT primary mitigations.
- Unverified (2): unattended-patch-reboot (CIP-007 is a PDF the adapter cannot read; hand-read only) and
  cloud-hard-realtime-loop (latency bound needs an experiment).
- Report penalty figure $1,584,648 per violation per day confirmed in 18 CFR 385.1602(d) (Order 906, Jan 2025).
  Report's CIP-015-1 enforcement date (2028-10-01) and CIP-003-9 April 2026 date are unconfirmed.
- Required statements: safety-function-ownership, actuation-write-path (agent-action-safety),
  regulatory-regime (regulatory-duties), network-zones.
