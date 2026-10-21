---
id: cryptography
version: 0.1.0
title: Cryptographic engineering
group: supply-chain-security-crypto
owner: sf
scope: >-
  Judges brief claims about how data is encrypted, signed and randomised: AEAD nonce handling (AES-GCM),
  randomness for keys and tokens, home-made constructions, post-quantum migration and message sizes,
  and stateful hash-based signatures. Who may call what (tokens, delegated authority) belongs to
  agent-security; network budgets beyond signature sizes belong to realtime-transport.
applies_when:
  signals:
    - encrypt
    - encryption
    - decrypt
    - cipher
    - aes-
    - " aes "
    - gcm
    - nonce
    - initialization vector
    - aead
    - chacha
    - signature
    - signing key
    - code signing
    - sign the
    - key exchange
    - rsa-
    - " rsa "
    - ecdsa
    - ecdh
    - elliptic
    - post-quantum
    - quantum
    - ml-kem
    - ml-dsa
    - kyber
    - dilithium
    - hash-based
    - random token
    - session key
    - secret key
    - entropy
    - cryptograph
required_statements:
  - id: key-nonce-management
    statement: The brief states how keys are generated, stored and rotated, and how nonce uniqueness per key is guaranteed.
    never_out_of_scope: keys-nonces
  - id: protection-lifetime
    statement: The brief states the adversary and how long confidentiality and signature validity must hold.
  - id: standard-algorithms
    statement: The brief names standard algorithms and maintained libraries rather than leaving the construction open.
adapters: [web_page, paper, osv]
---

# Cryptographic engineering

## Principles

- AEAD nonces must be distinct for every encryption under a key (rfc5116). GCM nonce reuse undermines
  confidentiality and all authenticity under the key, so GCM is only for settings where uniqueness is
  assured (rfc5116); AES-GCM-SIV is suggested where it cannot be, such as stateless counters or many
  encryptors on one key (rfc8452). Real deployments repeat nonces (bock-2016-nonce-disrespecting,
  osv-cve-2026-50577).
- Random nonces collide by the birthday bound, so volume per key must be bounded
  (rfc8452, bock-2016-nonce-disrespecting, osv-cve-2026-26014); compute it with `calc.birthday_collision`.
- General-purpose PRNGs are not for secrets (rfc4086, python-random-docs, java-util-random-docs).
- Standard AEADs exist so applications do not design crypto mechanisms; ad hoc cipher-plus-hash
  constructions are what they replaced (rfc5116, rfc8452).
- Recorded ciphertext can be decrypted once a quantum computer exists (rfc9370); ML-KEM and ML-DSA are
  believed secure against quantum adversaries (nist-fips203, nist-fips204) and NIST is transitioning
  away from quantum-vulnerable algorithms (nist-ir8547).
- Post-quantum signatures are large: 2420 bytes at the smallest ML-DSA set (rfc9881); check transports
  with `calc.payload_mtu`.
- LMS and XMSS are stateful; a reused one-time key voids security (nist-sp800-208, rfc8554, rfc8391, rfc9802).

## Questions a sweeper asks of each claim

- Where does each nonce come from? Can two encryptions under one key ever get the same one (restart,
  replica, fixed id, frozen counter, snapshot)?
- With random nonces, how many messages per key at the brief's stated volume? Run `calc.birthday_collision`.
- What generates keys, tokens and handles? Is it the platform CSPRNG?
- Does the brief design or compose a primitive, mode or integrity check itself?
- How long must the data stay secret? Does that reach the quantum horizon, and is key establishment hybrid?
- Do signed messages and certificates still fit their packets and fields at post-quantum sizes?
- Are hash-based signing keys ever backed up, cloned or shared across signers?

## Severity guidance

Nonce reuse, weak randomness for secrets and custom constructions answer yes to `severe-security`
(key recovery, forgery), so high; critical under `harm-safety` when the protected data is health,
financial or safety-relevant and exposure harms users. Quantum-vulnerable protection of long-lived
secrets is high when the stated lifetime reaches the horizon, and a principal-reject item when the
lifetime is unstated. Size overflow is high under `production-failure` when the brief names the
constrained transport. Performance cost of a safer mode is never quoted; route it to an experiment.

## Not this lens

- Token audience, delegated authority and session handles in agent systems: agent-security (randomness of
  those handles is checked here too).
- Packet loss, jitter and bandwidth budgets in general: realtime-transport and performance.
- Regulatory duties to encrypt (for example health data rules): privacy-regulated-data.
- Library provenance and pinning: supply-chain.
