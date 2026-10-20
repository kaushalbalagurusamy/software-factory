---
id: supply-chain
version: 0.1.0
title: Software supply chain
group: supply-chain-security-crypto
owner: sf
scope: >-
  Judges brief claims about which third-party packages, images, binaries and models enter the product
  and how they are installed: named packages that may not exist, agent-driven installs, install-time
  code execution, version pinning and artifact provenance. Licence terms of those dependencies belong
  to the licensing lens; agent tool servers and their runtime behaviour belong to agent-security.
applies_when:
  signals:
    - npm
    - pip install
    - pypi
    - package
    - dependency
    - dependencies
    - library
    - libraries
    - lockfile
    - requirements.txt
    - package.json
    - npx
    - uvx
    - docker image
    - container image
    - prebuilt
    - binary
    - registry
    - open source
    - open-source
    - sdk
    - install
    - ci pipeline
    - build pipeline
    - coding agent
    - model weights
required_statements:
  - id: dependency-vetting
    statement: The brief states where dependencies come from (registries or an allowlisted mirror) and how a new dependency is vetted before first use.
  - id: pinning-policy
    statement: The brief states that dependencies are pinned (lockfile, hashes or digests) and how updates are reviewed.
  - id: agent-install-policy
    statement: The brief states whether automated agents may add or install packages, and what human approval that requires.
    never_out_of_scope: agent-action-safety
adapters: [web_page, paper, osv]
---

# Software supply chain

## Principles

- A package name is a claim, not a fact. Code-generating models emit package names that do not exist, and
  this is a package-confusion attack on the supply chain (spracklen-2024-package-hallucination);
  lookalike names are a recognised threat (slsa-threats). Check every named package against its registry.
- Installing runs code. npm runs preinstall, install and postinstall lifecycle scripts on install
  (npm-scripts) unless `ignore-scripts` is set (npm-config); pip by default runs arbitrary code from
  distributions with no tamper checks (pip-secure-installs).
- Reproducible installs need locks enforced at install time: `npm ci` fails when the lock and manifest
  disagree (npm-ci); pip hash-checking mode protects against remote tampering (pip-secure-installs);
  SLSA suggests pinning build dependencies by digest (slsa-threats). Malicious releases of popular
  packages published with stolen tokens are documented (osv-pysec-2026-2).
- Provenance ties an artifact to how it was built, and SLSA's dependency mitigation is to verify it
  (slsa-provenance, slsa-threats).

## Questions a sweeper asks of each claim

- Does every package the brief names exist on the registry it implies, and is it the project the brief
  means? Run `registry.exists`, `registry.age`, `registry.cross_registry` on each name.
- Is the name very new, low-download, single-maintainer, or present only on the other ecosystem's registry?
- Who or what installs dependencies: a human, CI or an agent? With what approval and which secrets in scope?
- Do installs run lifecycle scripts or build from source distributions? In a job holding deploy secrets?
- Are versions pinned and hashed, and is the lockfile enforced in CI? Does anything say "latest"?
- Where do binaries, images and model weights come from, and is their provenance verified?

## Severity guidance

Hallucinated or unverified names and unattended agent installs usually answer yes to `severe-security`
(supply-chain compromise) and so are high; they become critical under `harm-safety` when the brief's
environment holds production or customer credentials. Unpinned versions are high when the build feeds
releases. Missing provenance on optional tooling is medium. The policy questions decide.

## Not this lens

- Licence compatibility of dependencies: licensing.
- Provider terms for APIs and models: provider-terms.
- MCP or agent tool servers' runtime behaviour, tool poisoning and tokens: agent-security.
- Cryptographic primitive choice inside a library: cryptography.
- Agent orchestration and autonomy design in general: agent-orchestration.
