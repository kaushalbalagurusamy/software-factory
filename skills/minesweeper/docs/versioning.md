# Versioning

## Lenses

Semver in `lens.md`:
- **patch**: wording, cues, a new source or quote, a trap promoted to verified.
- **minor**: a new trap, a new required statement, a changed `applies_when`.
- **major**: a removed or renamed trap id (keep the old id as an alias where possible).

Every change adds a `CHANGELOG.md` entry and re-runs that lens's cases. Calibration is recorded
against a version, so any version bump makes the lens uncalibrated until its cases pass again.

## Engine, schemas, policy

- Schemas are versioned in their file names (`*.v1.json`). A breaking change creates `*.v2.json`,
  bumps `schema_version` in the documents, and keeps a reader for v1 for one release.
- A change to `engine/`, `config/policy.yaml` or any schema re-runs every case.
- `config/groups.yaml` and `config/models.yaml` are tuning: re-run the cases of the groups touched.

## Evaluation history

`runs/<date>-<label>/` directories are append-only. Failed runs stay; a rerun is a new label.
`runs/calibration.json` records, per lens, the version, the run directories, the metrics and
whether the thresholds in `policy.yaml calibration` were met. Thresholds are never loosened to make
a lens pass.
