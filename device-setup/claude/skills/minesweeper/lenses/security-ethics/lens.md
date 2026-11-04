---
id: security-ethics
version: 0.1.0
title: Security testing ethics and coordinated disclosure
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about security tooling that touches systems other than the operator's own:
  scanning, exploitation, proof of vulnerability, handling of data met during testing, and publishing
  findings. Securing the deliverable itself belongs to the security and cryptography lenses; personal
  data processing in the product belongs to privacy-regulated-data.
applies_when:
  signals: [vulnerability, vulnerabilities, security scan, vulnerability scan, port scan, scanner, pentest, penetration test, red team, red-team, exploit, cve, zero-day, 0-day, proof of concept, proof-of-concept, attack surface, bug bounty, disclosure, threat intelligence, security audit, fuzzing, payload, exposed instances, misconfigured hosts]
required_statements:
  - id: authorised-targets
    statement: The brief states which systems the tool may actively test and how the owner's authorisation for each is obtained and checked.
  - id: disclosure-route
    statement: The brief states how findings about systems the operator does not own are reported (privately to the owner, vendor or a coordinator) and when, if ever, they are published.
  - id: sensitive-data-handling
    statement: The brief states what the tool does when it meets personal or other sensitive data during testing (stop, do not retain or display, notify the owner).
    never_out_of_scope: regulatory-duties
adapters: [web_page]
---

# Security testing ethics and coordinated disclosure

## Principles

- Authorisation comes first. Accessing a computer without authorisation, or beyond authorised access,
  to obtain information, and knowingly transmitting code that intentionally causes damage without
  authorisation, are prohibited (`usc-18-1030`, 1030(a)(2), (a)(5)(A), (e)(6)). Anything not expressly
  in scope is not authorised for testing (`cisa-vdp-template`, Scope), and research belongs on
  equipment the finder is authorised to use (`cert-cvd-discovery`).
- Prove presence, not impact. An exploit is used only to the extent necessary to confirm a
  vulnerability; never to compromise or exfiltrate data, persist, or pivot (`cisa-vdp-template`,
  Guidelines).
- Data met during testing is not evidence to show off. A tester who meets sensitive data stops,
  notifies the owner and discloses it to no one (`cisa-vdp-template`). Exposing personal data is a
  personal data breach (`gdpr`, Article 4(12)) that controllers must secure against (Article 32) and
  notify (Article 33).
- Disclose in coordination. The owner gets a reasonable time to fix before public disclosure
  (`cisa-vdp-template`); release is synchronised with mitigations (`cisa-cvd`) and timelines are agreed
  with stakeholders to minimise harm (`cert-cvd-ethics`). Early publication is a fallback for an
  unresponsive vendor, not a default (`cisa-cvd`). ISO/IEC 29147 states the same practice but is
  paywalled and not quoted here (`iso-iec-29147`).

## Questions a sweeper asks of each claim

- Whose systems does this claim send traffic to, and where does the brief show the owner authorised it?
- Can scope grow on its own (discovered subdomains, connected services, "any URL a user enters")?
- What does the tool do after detecting a vulnerability: fingerprint, or run a payload? Could the
  payload read data, persist, pivot or damage?
- Does any output (report, dashboard, demo, rubric evidence) contain data taken from the tested system?
- Who learns of a finding first, and how soon can it become public? Is there a fix-first path?
- Does a rubric reward depth of compromise, volume of leaked records, or speed of publication?

## Severity guidance

Unauthorised access, exfiltration and publishing unpatched details answer yes to the first two policy
questions (break a law or ethics; harm third parties), so these traps are usually critical. Lower the
tier only when the brief shows written authorisation for named owned targets and the action stays within
it. Where the answer turns on whether a client can authorise testing of its providers, on a terms-of-
service reading, or on which jurisdiction's computer-misuse law applies, the disposition is ask-owner;
do not decide it as a matter of law.

## Not this lens

- Hardening the deliverable (authn, secrets, injection, MCP tool safety): agent-security, cryptography.
- Personal data processed by the product itself (lawful basis, retention, residency): privacy-regulated-data.
- Scraping, circumventing access controls for content, and text and data mining: copyright-data-rights.
- Provider acceptable-use terms for cloud or model APIs used by the tool: provider-terms.
- Safety interlocks and OT networks: cyber-physical.
