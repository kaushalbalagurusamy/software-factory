# Adding a lens

A lens is a folder. Adding one never touches the engine.

1. `cp -r lenses/_template lenses/<id>` and rename the two example cases.
2. **lens.md front matter** (schema `engine/schemas/lens.v1.json`): `id` = folder name, `version`
   0.1.0, `group` = a key in `config/groups.yaml`, `scope`, `applies_when` (`signals` that would
   appear in a brief needing this lens, or `always: true`), `required_statements` (what a brief in
   this domain must state; each becomes an omission check; tag `never_out_of_scope` where it
   applies), `adapters`.
3. **Body**: principles (each tied to a source id), the questions a sweeper asks, severity guidance,
   and "not this lens" (neighbours and who owns them). 60-140 lines.
4. **traps.yaml**: generic patterns, never project anecdotes. Ids `<lens>.<slug>`; external ids in
   `aliases`. New traps start `status: unverified`.
5. **sources.yaml**: primary sources only for anything that will decide a trap: the statute,
   licence, terms page, standard, specification, original paper, advisory. Pick an adapter from
   `sources/adapters/`; a new source kind needs a new adapter module with `fetch(source) -> dict`.
6. **Verify**: `python3 tools/refresh.py --lens <id>` fetches into the cache. Copy the decisive
   passage verbatim into `quotes` (with `locator`, `fetched`, `supports`), re-run refresh with
   `--force`, and mark the trap `verified` with `verified_on` only when no quote is reported missing
   and every cited source is primary.
7. **Cases**: one planted case and one clean twin per trap, and at least one omission case per lens
   (`docs/writing-cases.md`).
8. Add the lens to a group in `config/groups.yaml`.
9. `python3 tools/lint.py` must report zero errors; then
   `python3 tools/evaluate.py run --label <id>-initial --lens <id>` and
   `python3 tools/evaluate.py score runs/<dir> --record`. Commit the run directory and
   `runs/calibration.json` with the lens.
