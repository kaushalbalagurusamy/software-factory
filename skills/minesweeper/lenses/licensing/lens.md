---
id: licensing
version: 0.1.0
title: Software, model and dataset licensing
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims that choose, embed, modify, distribute or host third-party code, model weights or
  datasets, against the licence text that governs them (copyleft, network copyleft, source-available,
  non-commercial). Provider API terms belong to provider-terms; copyright in training data belongs to
  copyright-data-rights.
applies_when:
  signals: [open source, open-source, open-weight, gpl, agpl, sspl, busl, source-available, licence, license, library, libraries, dependency, dependencies, third-party component, fork, embed, bundle, statically link, on-prem, self-hosted, installer, sdk, managed service, hosted version, model weights, checkpoint, pretrained, dataset, creative commons]
required_statements:
  - id: dependency-licence-inventory
    statement: The brief states, or requires producing, the licence (SPDX id and version) of every third-party component, model and dataset the deliverable uses.
    never_out_of_scope: licences-terms
  - id: distribution-model
    statement: The brief states how the deliverable reaches users (shipped binary, mobile app, device image, on-prem install, or hosted service only), since copyleft triggers depend on it.
    never_out_of_scope: licences-terms
  - id: commercial-use
    statement: The brief states whether the deliverable is commercial (sold, revenue-bearing, or used for commercial advantage), so non-commercial assets can be excluded.
adapters: [web_page, spdx]
---

# Licensing

## Principles

- Copyleft follows distribution. GPLv3 obligations attach when a work is conveyed; conveying a work
  based on the program requires licensing the whole work under the GPL and supplying Corresponding
  Source with object code. Mere network interaction without transferring a copy is not conveying
  (`gpl-3-0`, Sections 0, 5(c), 6).
- Network copyleft follows modification plus remote use. AGPLv3 Section 13 requires a modified version
  to offer its Corresponding Source to every remote network user (`agpl-3-0`).
- Source-available is not open source. SSPL Section 13 reaches the whole service-operating stack when
  the program is offered as a service (`sspl-1-0`); BUSL 1.1 grants non-production use only, plus
  whatever the licensor's Additional Use Grant allows, until the Change Date (`busl-1-1`).
- Free to download is not free to sell. CC BY-NC 4.0 restricts use to purposes not primarily directed
  at commercial advantage (`cc-by-nc-4-0`); research-only model licences restrict in the same direction.
- Licences change between versions. Read the licence of the exact version at sweep time with the
  `licence.*` checks; never infer it from the project's name or from a vendor's past licence.

## Questions a sweeper asks of each claim

- Which components, models and datasets does this claim pull in, and what is each one's SPDX licence
  at the pinned version (`licence.package`, `licence.github`, `licence.spdx`, `licence.family`)?
- Does the deliverable leave the building as a copy (installer, SDK, app, device image, on-prem)? If
  so, which copyleft components ride along?
- Is any copyleft or AGPL component modified and reachable by remote users?
- Is a source-available component offered to third parties as a service, or used in production
  outside its grant?
- Is any asset licensed for non-commercial or research use only, and is the product commercial?
- Does the brief rank candidates on benchmarks alone, with licence never stated?

## Severity guidance

Shipping or hosting a component outside its licence grant answers yes to the first policy question
(break a licence), so these traps are usually critical. Lower the tier only when evidence shows the
component is unmodified and never conveyed (AGPL), or the licence grant plainly covers the use. Where
the answer turns on whether two programs form one work, or on an Additional Use Grant's wording, the
disposition is ask-owner; do not decide it as a matter of law.

## Not this lens

- API and model provider terms (output use, competing models, resale): provider-terms.
- Copyright and database rights in scraped or mined training data: copyright-data-rights.
- Malicious or hallucinated packages, provenance and typosquatting: supply-chain.
- Export control and sanctions: not covered by this group.
