---
id: company-context
version: 0.1.0
title: Company context
group: business
owner: sf
scope: >-
  Judges whether a brief fits the organisation it is written for: its stated mission and published
  policies, the customer who pays, the regulator that governs it, and the data rights it actually
  holds. Holds no company data; it gives the procedure to research the named organisation per project.
  Statute-level privacy, AI and provider-terms rules belong to the law-terms-ethics lenses.
applies_when:
  always: true
required_statements:
  - id: organisation-and-payer
    statement: The brief names the organisation the product serves and who pays for it (the buyer, as distinct from the user and the evaluator).
  - id: governing-regulators
    statement: The brief names the regulator or regulators that govern the organisation's sector, or states that none applies and why.
    never_out_of_scope: regulatory-duties
adapters: [web_page]
---

# Company context

This lens carries no facts about any company. For each brief it runs a research procedure on the
organisation the brief names and writes the result to the project, then checks the brief against it.

## Research procedure (per brief)

Run it once per organisation per project, with grounded-research for single facts and deep-research
for the synthesis. Write the output to `docs/minesweep/company-<slug>.md` in the project repository,
never into this skill. Record each fact with its URL, fetch date and tier.

1. **Mission and stated values**: from the organisation's own site (about, mission, values pages).
   Quote them verbatim.
2. **Customers and who pays**: who the users are, who the buyer is, and the business model (seat,
   usage, transaction, grant, public budget). Prefer filings (SEC EDGAR for public companies),
   annual reports and the organisation's own pricing page over press coverage.
3. **Regulators**: which agencies and statutes govern the sector and jurisdiction (for example a
   health, financial, transport, education or telecom regulator). Note that general consumer
   protection law carves sectors out to other regulators (ftc-act-s5, 15 U.S.C. 45(a)(2)).
4. **Public incidents and enforcement**: regulator press releases, consent orders, court records,
   breach notifications. Primary records only; news is a lead, not evidence.
5. **Published policies**: privacy notice, terms of service, acceptable-use policy, AI or
   responsible-use principles, security and trust pages. Quote the clauses the brief touches.
6. **Hiring-page signals**: open roles and their stated priorities, as a weak signal of what the
   organisation actually invests in. Label it community-tier evidence.
7. **Gaps**: what could not be found, and what only the owner can confirm (contracts, data
   licences, internal policy). Those become ask-owner items, not assumptions.

## Principles

- An organisation's published privacy notice, terms and AI principles are representations to its
  customers; building a feature that contradicts them risks an unfair or deceptive practice, which
  US federal law declares unlawful (ftc-act-s5, 15 U.S.C. 45(a)(1)). Other jurisdictions: ask-owner.
- General consumer-protection jurisdiction excludes sectors with their own regulators (banks,
  common carriers, air carriers and others), so the governing regulator depends on the sector and
  must be named (ftc-act-s5, 15 U.S.C. 45(a)(2)).
- Data collected under one set of commitments cannot be repurposed by quietly changing them
  (ftc-terms-change-guidance, secondary; the rule is 15 U.S.C. 45).
- A metric optimised past the point where it tracks the real goal becomes ineffective or harmful
  (manheim-garrabrant-goodhart); a success metric must be the paying customer's outcome, not the
  evaluator's convenience.

## Questions a sweeper asks of each claim

- Who is the organisation, who uses the product, who pays, and who is grading it? Are these the
  same party? If not, whose outcome does each success metric measure?
- Does any requirement contradict a published policy or stated value? Quote both.
- Which regulator governs this organisation in this jurisdiction, and does the brief mention it?
- What data does the feature need, and under which consent, contract or licence does the
  organisation hold it? Is that documented or assumed?
- Has the organisation been the subject of enforcement for a practice the brief now asks for?

## Severity guidance

A requirement that contradicts a published privacy or AI policy usually answers yes to
law-licence-terms-ethics (critical) where deception law applies; jurisdiction and contract turn it
into ask-owner. Ignoring the governing regulator is regulatory-duties and cannot be closed as out of
scope; it is critical when the feature is itself regulated, high otherwise. An evaluator-serving
metric is usually principal-reject (medium), high when it would ship harm to the paying customer.
Assumed data rights are critical when personal data is involved, high for commercial data.

## Not this lens

- What a specific privacy statute requires: privacy-regulated-data.
- AI-specific statutory duties: ai-regulation. Provider or API terms: provider-terms.
- Copyright and dataset licences: copyright-data-rights. Price, volume and unit economics:
  market-reality. Rubrics that reward the wrong behaviour in general: rubric-inversion.
