---
id: accessibility
version: 0.1.0
title: Digital accessibility of user interfaces
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about user-facing web content, mobile apps and documents that omit or reject
  accessibility, against WCAG and the laws that make it a floor (ADA Title II for US public entities,
  the European Accessibility Act for covered EU consumer services). Physical-premises accessibility and
  employment accommodation are out of scope.
applies_when:
  signals: [accessibility, accessible, a11y, wcag, screen reader, screen-reader, assistive technology, keyboard navigation, colour contrast, color contrast, alt text, alt-text, captions, aria, ui, frontend, front-end, web app, mobile app, website, portal, checkout, e-commerce, ecommerce, e-book, government service, public sector, section 508, disability]
required_statements:
  - id: a11y-standard
    statement: The brief states the accessibility standard and level the UI targets (for example WCAG 2.2 Level AA) and treats it as an acceptance gate.
  - id: legal-coverage
    statement: The brief states whether the product is a US public-entity service (ADA Title II) or an EAA-covered EU consumer service, which set a binding accessibility floor.
    never_out_of_scope: regulatory-duties
  - id: non-visual-operable
    statement: The brief states that information and operation do not depend on a single sense or input (not colour-only, keyboard operable, works without a precise drag).
adapters: [web_page]
---

# Digital accessibility of user interfaces

## Principles

- Do not encode meaning in one channel. Colour must not be the only visual means of conveying
  information, action or state (`wcag-22`, SC 1.4.1).
- Everything must be operable without a mouse. All functionality is keyboard operable (`wcag-22`,
  SC 2.1.1), and a drag operation has a single-pointer alternative unless dragging is essential
  (`wcag-22`, SC 2.5.7). Level AA conformance requires every Level A and AA criterion to be met
  (`wcag-22`, Conformance).
- Public-sector digital services have a legal floor. US public entities must make web content and
  mobile apps accessible and meet WCAG 2.1 Level AA on the phased dates, absent a fundamental
  alteration or undue burden (`ada-28-cfr-35-200`, 35.200).
- Covered EU consumer services have a legal floor. The European Accessibility Act applies to listed
  services provided to consumers after 28 June 2025 and requires them to meet Annex I: perceivable,
  operable, understandable, robust (`eaa-2019-882`, Articles 2(2), 4(1), 13(1), Annex I).

## Questions a sweeper asks of each claim

- Does the UI carry any information or state through colour alone, or through one sense only?
- Can every function be reached and used with a keyboard, and without a precise drag?
- Is the product a government service (ADA Title II) or a covered EU consumer service (EAA)? If so, is
  the legal accessibility floor treated as a requirement rather than deferred?
- Does a requirement or rubric drop, defer or mark accessibility "optional", "phase 2" or a "stretch goal"?
- Does the brief name the standard and level it targets, and is it an acceptance gate?

## Severity guidance

A WCAG failure in a product with no legal coverage is usually a principal-level correctness defect
(medium to high). The same failure in an ADA Title II public-entity service or an EAA-covered EU
consumer service answers the first policy question (breaks a regulation) and is usually high to
critical. Lower the tier only where the brief shows the floor is met or a documented exception applies.
Whether a body is a Title II "public entity", whether a service is EAA-covered, the exact compliance
deadline, and microenterprise or undue-burden exceptions are ask-owner.

## Not this lens

- EU AI Act and other AI duties: ai-regulation. Clinical review duties: professional-duty.
- Media encoding and caption generation mechanics: media-pipelines (this lens covers whether captions
  and text alternatives are required, not how they are produced).
- Privacy of user data in the UI: privacy-regulated-data. Licensing of UI components: licensing.
