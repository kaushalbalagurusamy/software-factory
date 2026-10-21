# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 5 traps (money-in-binary-float [TCS-03], float-equality, order-dependent-float-aggregation, naive-local-timestamps, fixed-width-counter-overflow), 3 required statements, planted/clean pairs per trap and 3 omission cases with clean twins.
- All 5 traps verified from Python docs (floating-point tutorial, decimal, datetime), Goldberg 1991 (Oracle-hosted), RFC 3339 and JLS SE 21 section 4.2.2. IEEE 754 itself is paywalled and not cited.
- Corrected report claim: Kahan summation does not make float money exact and is not needed for integer minor units.
