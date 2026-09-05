---
name: one-way-door-guard
description: >-
  Pre-flight safety inspection for operations with irreversible consequences (schema drops,
  vector re-indexing, public API contract breakage, cloud resource destruction).
  Ensures blast-radius calculation, automated rollback path design, and human confirmation.
---

# One-Way Door Guard & Blast-Radius Assessment

## 1. Intent & Rationale
Software changes vary dramatically in their reversibility:
* **Two-Way Doors:** If a refactor breaks a helper function or a CSS style, rolling it back is a single git revert and instant deployment.
* **One-Way Doors:** Dropping a database table, changing a production vector dimension, deleting an S3/GCS bucket, or altering an external API contract causes immediate data loss, client failure, or days of downtime.

This skill provides a **lightweight, non-blocking blast-radius evaluation** that only pauses execution when truly irreversible operations are detected.

---

## 2. Blast-Radius Classification

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ High Blast Radius (STOP & EVALUATE)                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ • SQL `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, or destructive migrations    │
│ • Re-indexing vector databases that require full corpus regeneration         │
│ • Deleting cloud storage buckets or primary database instances              │
│ • Removing or renaming fields in public API endpoints                       │
│ • Changing cryptographic algorithms or secret encryption keys               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The 3-Step Assessment Checklist

### Step 1: Blast-Radius Calculation
Answer the following questions before staging changes:
1. **Data Impact:** Is any existing data permanently destroyed or altered?
2. **Client Impact:** Will older versions of mobile clients, external webhooks, or third-party integrations break?
3. **Recovery Time Objective (RTO):** If this change fails in production, how long does recovery take?

### Step 2: Rollback Strategy Design
* **Expand-and-Contract Migration Pattern:**
  * Step 1 (Expand): Add the new column/field alongside the old one.
  * Step 2 (Dual Write): Write to both old and new fields; read from old.
  * Step 3 (Backfill): Backfill existing data into the new field.
  * Step 4 (Switch): Switch reads to the new field.
  * Step 5 (Contract): Deprecate and safely remove the old field after client adoption.
* **Soft Deletion & Snapshots:** Ensure tables use `deleted_at` timestamps or automated pre-migration snapshots before destructive operations.

### Step 3: Explicit Human Verification
Present the blast radius and the drafted rollback plan to the human. Never run destructive CLI commands or migrations in unattended headless loops.
