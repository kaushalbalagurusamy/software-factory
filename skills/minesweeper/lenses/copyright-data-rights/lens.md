---
id: copyright-data-rights
version: 0.1.0
title: Copyright and data rights in acquired content
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about acquiring, mining or training on third-party content (web pages, articles,
  books, media, datasets) against copyright, text-and-data-mining and anti-circumvention rules, and the
  copyright duties of general-purpose AI model providers. Licences of code and packaged datasets belong to
  licensing; whether access to a system is authorised belongs to security-ethics.
applies_when:
  signals: [scrape, scraping, scraper, crawl, crawler, harvest, corpus, training data, train on, pretraining, text and data mining, tdm, dataset, robots, paywall, drm, e-book, news articles, publisher, copyrighted, foundation model, general-purpose ai, base model, release weights, media library, transcripts]
required_statements:
  - id: content-provenance
    statement: The brief states where every training or mined content source comes from and the legal basis or licence for using it.
    never_out_of_scope: licences-terms
  - id: opt-out-handling
    statement: Where content is crawled or mined, the brief states how rightholder reservations (robots directives, machine-readable TDM opt-outs) are honoured.
adapters: [web_page]
---

# Copyright and data rights

## Principles

- Mining is an exception with conditions. The EU TDM exception covers lawfully accessible works only
  (Directive (EU) 2019/790 Article 4(1)) and yields to a rightholder's express reservation, for online
  content by machine-readable means (Article 4(3)) (`dsm-2019-790`).
- General-purpose AI model providers must honour those reservations through a copyright policy and
  publish a training-content summary (Regulation (EU) 2024/1689 Article 53(1)(c), (d)) (`eu-ai-act`).
- Access controls are a boundary. Circumventing a technological measure that controls access to a
  protected work is prohibited in the US (17 U.S.C. 1201(a)(1)(A)) (`usc-17-1201`), and content behind
  one is not lawfully accessible for the EU exception.
- Jurisdiction decides. US fair use, EU exceptions and other regimes differ; the sweeper flags and cites,
  the owner decides with counsel.

## Questions a sweeper asks of each claim

- Where does each content source come from, and under what licence or exception?
- Does the crawler read and honour machine-readable reservations, and is that logged per document?
- Does acquisition defeat any paywall, login, encryption, DRM or anti-bot measure?
- Is the output a general-purpose model placed on the EU market? If so, is there a copyright policy and a
  public training-content summary?
- Is provenance recorded well enough to remove a source later?

## Severity guidance

Circumventing access controls and mining reserved content answer yes to the first policy question:
critical. A missing GPAI copyright policy or training summary is high (regulatory exposure at release).
Fair use, exemptions and whether a model is general-purpose turn on facts and law: ask-owner.

## Not this lens

- Licences attached to datasets and model weights (CC BY-NC, research-only): licensing.
- Terms of a model provider about using its outputs: provider-terms.
- Unauthorised access to computers and scanning: security-ethics.
- Personal data inside scraped content: privacy-regulated-data.
