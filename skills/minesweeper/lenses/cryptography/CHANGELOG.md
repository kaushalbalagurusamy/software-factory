# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 7 traps (gcm-deterministic-nonce from SEC-04, non-csprng from SEC-05,
  quantum-vulnerable-long-term-secrecy and pq-signature-size-mtu from SEC-06; extra generic traps
  gcm-random-nonce-volume, stateful-hbs-state-reuse, custom-crypto-construction), 3 required
  statements, 18 cases (7 planted/clean pairs, 2 omission pairs).
- All 7 traps verified on 2026-10-14 from RFC 5116, 8452, 4086, 9370, 9881, 8554, 8391, 9802, NIST FIPS
  203/204 and SP 800-208 abstracts, NIST IR 8547 (ipd) abstract, Python and Java API docs, Böck et al.
  (USENIX WOOT 2016) and OSV CVE-2026-50577 / CVE-2026-26014.
- Report corrections: CVE-2026-26014 describes random (not deterministic or frozen-counter) nonces;
  the "77,000 responses" figure for CVE-2026-50577 is not in the advisory. The AES-GCM-SIV "48 percent
  slower" figure is not used; RFC 8452 reports different measurements and any cost must be measured.
- Not fetchable as text: SP 800-38D body (PDF) and Joux's 2006 comments (PDF); listed or noted only.
