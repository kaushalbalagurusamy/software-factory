---
id: privacy-regulated-data
version: 0.1.0
title: Privacy and regulated data
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about collecting, sending, storing, caching or retaining personal data, especially
  regulated classes (health, special-category, children's data), against HIPAA, GDPR and COPPA rule text.
  Provider tier rules belong to provider-terms; AI-specific duties belong to ai-regulation.
applies_when:
  signals: [patient, clinical, medical, health, phi, hipaa, ehr, diagnosis, therapy, personal data, personal information, pii, gdpr, special category, biometric, children, kids, minors, students, employee records, customer records, user data, location history, retention, data residency, cdn, edge cache, transcripts]
required_statements:
  - id: data-classes
    statement: The brief lists the classes of personal data processed, flagging regulated ones (health, special-category, children's, financial).
    never_out_of_scope: regulatory-duties
  - id: processors-and-agreements
    statement: The brief names every third party that receives personal data and the agreement covering it (BAA, Article 28 processor contract, DPA).
    never_out_of_scope: regulatory-duties
  - id: residency-and-retention
    statement: The brief states where personal data is stored, cached and processed, and how long each class is retained.
adapters: [web_page]
---

# Privacy and regulated data

## Principles

- PHI moves only under a business associate contract. A covered entity may let a business associate
  handle PHI only with satisfactory assurances, i.e. a contract with the 164.504(e) terms
  (`hipaa-164-502`, `hipaa-164-504`, `hipaa-164-308`).
- Special-category data is prohibited by default. GDPR Article 9(1) bans processing health, biometric
  and similar data unless an Article 9(2) condition applies; processors need Article 28 guarantees and a
  binding contract (`gdpr`).
- Location is processing. Transfers outside the EEA, including edge caches and replicas, need a Chapter V
  basis (Article 44) (`gdpr`).
- Collect less, keep shorter. Data minimisation and storage limitation, Article 5(1)(c) and (e) (`gdpr`).
- Children's data needs parental consent first under COPPA (`coppa-312-5`).
- eCFR blocks automated fetches; HIPAA and COPPA text is read from the LII reproduction. Check eCFR by
  hand where exact wording decides a dispute.

## Questions a sweeper asks of each claim

- What personal data does this claim touch, and is any of it health, biometric, children's or another
  special category?
- Which third parties receive it (model APIs, transcription, analytics, CDN), and under what agreement?
- Where does it physically sit, including caches, logs, replicas and backups?
- How long is each class kept, and what deletes it?
- Who are the users: patients, minors, employees? Which jurisdictions?

## Severity guidance

Regulated data sent to a party with no BAA or processor contract, special-category data cached abroad
with no transfer basis, and children's data without parental consent answer yes to the first policy
question: critical. Over-collection and indefinite retention are high (material legal exposure) unless the
data is regulated. Covered-entity status, the Article 9(2) condition and the transfer mechanism turn on
facts and law: ask-owner.

## Not this lens

- Whether a model provider's tier may train on inputs: provider-terms.
- Encryption, key management and breach mechanics: cryptography, agent-security.
- Emotion inference and biometric categorisation bans: ai-regulation.
- Publishing others' data to prove a vulnerability: security-ethics.
