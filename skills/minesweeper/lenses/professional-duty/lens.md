---
id: professional-duty
version: 0.1.0
title: Professional duties an engineer cannot sign away
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims that ask an engineer to breach a professional duty: certifying software without a
  basis, suppressing a danger, making deceptive claims, or fielding clinical recommendation software a
  clinician cannot review. Covers the generic duty, not sector conformity regimes; the EU AI Act belongs
  to ai-regulation and OT functional safety to cyber-physical.
applies_when:
  signals: [sign off, sign-off, signoff, approve the release, certify, certification, safety-critical, safety critical, code of ethics, professional responsibility, duty to warn, whistleblow, ship it anyway, clinical decision, clinical recommendation, diagnosis, treatment recommendation, triage, patient, do not disclose, keep it quiet, guarantee, accuracy claim]
required_statements:
  - id: approval-basis
    statement: The brief states what evidence (tests, review, risk assessment) a release approval or sign-off attests to, rather than treating the signature itself as the gate.
  - id: escalation-path
    statement: The brief states how an engineer who finds a danger or a likely failure records it and reports it to someone able to act.
  - id: clinical-oversight
    statement: For clinical recommendation software, the brief states that a qualified human can review the basis of each recommendation and remains the decision-maker.
adapters: [web_page]
---

# Professional duties an engineer cannot sign away

Keep this lens modest. It names a few duties stated in a primary professional code or statute, not a
general theory of ethics. Where a duty turns on contract or jurisdiction, the disposition is ask-owner.

## Principles

- Approve only with a basis. An engineer approves software only with a well-founded belief it is safe,
  meets specification and passes tests (`se-code` 1.03), endorses only what is within their competence
  and that they agree with (`se-code` 4.02), and ensures adequate testing and review (`se-code` 3.10).
- Warn about danger; do not bury it. Engineers disclose actual or potential dangers to those who should
  know (`se-code` 1.04) and promptly document and report a project likely to fail or overrun
  (`se-code` 2.06). Confidentiality holds only where consistent with the public interest and the law
  (`se-code` 2.05).
- Do not deceive. Public statements about software must be fair and non-deceptive (`se-code` 1.06), and
  estimates must be realistic with stated uncertainty (`se-code` 3.09).
- Clinical recommendations need a reviewable basis. US law treats recommendation software as non-device
  only where the clinician can independently review its basis and is not meant to rely on it primarily
  (`usc-21-360j` 360j(o)(1)(E)); otherwise FDA device policies apply (`fda-cds-guidance`).

## Questions a sweeper asks of each claim

- Does a signature, approval or certification stand in for the evidence it should attest to?
- Is anyone asked not to write down, or not to report, a danger, defect or likely failure?
- Is a stated capability, metric or date unsupported by current evidence, or scripted regardless of it?
- For clinical output: can a qualified human see and review the basis, and do they remain the decision-maker?

## Severity guidance

A plain breach of a professional code or a duty to warn answers yes to the first policy question (ethics),
and unreviewable clinical advice answers the harm question, so these traps are usually high to critical.
Lower the tier where the brief already builds in the evidence, escalation and human review. Where a duty
depends on which jurisdiction or contract governs (external whistleblowing, device classification, licensed
professions), set the disposition to ask-owner rather than deciding it.

## Not this lens

- EU AI Act human-oversight, logging and high-risk duties: ai-regulation.
- OT safety interlocks and functional-safety sign-off (process safety, IEC 61508/61511): cyber-physical.
- Unauthorised security testing and disclosure ethics: security-ethics.
- How a metric is actually measured (leakage, calibration): ml-evaluation; business viability: market-reality.
- The ACM and IEEE codes restate these duties but their pages block automated fetches, so this lens quotes
  the joint ACM/IEEE-CS Software Engineering Code (`se-code`) instead.
