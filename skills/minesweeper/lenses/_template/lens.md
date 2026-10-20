---
id: example-lens            # must equal the folder name
version: 0.1.0              # semver; see docs/versioning.md
title: Example lens
group: law-terms-ethics     # a key in config/groups.yaml
owner: sf
scope: >-
  One or two sentences: what kind of brief claim this lens judges and what it deliberately leaves to
  other lenses.
applies_when:
  signals: [keyword one, keyword two]   # case-insensitive substrings of the brief; or `always: true`
required_statements:
  - id: threat-model
    statement: The brief states who the adversary is and what they control.
    never_out_of_scope: keys-nonces     # optional: a policy.yaml never_out_of_scope id
adapters: [web_page]
model: sonnet               # optional override of the group model
---

# Example lens

## Principles

The rules this lens applies, each in a sentence or two, with the source id that decides it.

## Questions a sweeper asks of each claim

- ...

## Severity guidance

Which policy.yaml questions usually answer yes for this lens's traps, and what raises or lowers
the tier in context. The policy questions still decide.

## Not this lens

Neighbouring concerns and the lens that owns them.
