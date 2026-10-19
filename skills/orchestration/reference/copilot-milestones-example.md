# Example: Clinical Co-Pilot milestone bundles and tripwires

> **Project-specific example, not general policy.** This is how the orchestration skill's independent-review gates were set up for the OpenEMR Clinical Co-Pilot build: its tracer bullets (TB-01 to TB-11), its R41 redaction rule and its Codex Plus quota. Carried over unchanged from the former sf-hierarchical-orchestration skill (section 3). Use it as a worked pattern for bundling work into a few milestone audits; do not apply the TB numbers or invariants to another project.

Codex on the Plus plan had to be conserved for high-leverage architectural and invariant audits.

## A. The 4 milestone bundles
Never invoke Codex per-PR or per-tracer-bullet. Bundle tracer bullets into 4 milestones:

1. **Milestone 1 — Foundational Invariants (`TB-01`, `TB-02`, `TB-03`):**
   - *Prerequisite:* Claude has green deterministic tests on Pydantic contracts and FHIR read mock.
   - *Codex Check:* Verify coordinate space invariants ($[0, 1000]$), `needs_review` enforcement, and patient isolation.
2. **Milestone 2 — Ingestion & Rendering Pipeline (`TB-04`, `TB-05`, `TB-06`):**
   - *Prerequisite:* Document state machine and PDF.js DOM overlay tests pass locally.
   - *Codex Check:* Verify DOM bounding-box security sandbox (no canvas serialization), CSP headers, and streaming proxy `no-store`.
3. **Milestone 3 — Clinical Logic, RAG & Integrity (`TB-07`, `TB-08`, `TB-10`):**
   - *Prerequisite:* Grounded supervisor, confirm modal, pinned denial, and EEG gate pass locally.
   - *Codex Check:* Verify R41 SaaS redaction (no raw PHI in OTLP spans), cross-patient denial logic, and prohibition on direct unverified lab writes.
4. **Milestone 4 — Pre-Submission Freeze (`TB-09`, `TB-11` + E2E Suite):**
   - *Prerequisite:* 19-metric LiveOps dashboard, SVG trend charts, and end-to-end synthetic harness pass.
   - *Codex Check:* Architectural consistency with `W2_ARCHITECTURE.md`, honest telemetry status reporting, and zero unresolved safety blockers.

## B. Emergency tripwires (out-of-band Codex invocation)
Deploy Codex outside the 4 milestones **only** if:
- **R41 Leak Risk:** New telemetry/logging exporter touches OTLP/Langfuse.
- **Persistent Deadlock:** Sonnet + Opus fail to resolve a defect after 3 attempts.
- **External Merge/Deploy:** Before any branch merge or remote deployment.

## C. Standard Codex review packet format
Always invoke Codex with a read-only packet containing:
1. `git diff base..HEAD --stat` + surgical diff of target files.
2. Exact checklist of 3–5 invariant questions.
3. Explicit instruction: `Read-only audit. Output APPROVE or REJECT with file and line citations.`

---
