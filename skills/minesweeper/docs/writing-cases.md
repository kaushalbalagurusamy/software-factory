# Writing cases

Cases measure the sweep. They are synthetic, generic, and written from the trap catalogue, never
from a real project.

## Kinds (schema `engine/schemas/case.v1.json`)

| Kind | Brief | expect |
|---|---|---|
| planted | a realistic brief with exactly one trap | `traps: [<trap id>]`, optional `min_severity` |
| clean | the planted brief with only the trap removed or made safe | `none_from_lens: true` |
| omission | a brief in the lens's domain that silently omits one required statement | `omissions: [<lens>.<statement-id>]` |
| integration | (in `integration/`) several traps across lenses | `traps: [...]`, `omissions: [...]` |

Planted and omission cases name a clean `twin`. Twins differ only in the trap, so a finding on the
twin is a precise false alarm.

## Writing a good planted brief

- 6-15 lines, in the voice of a real brief: goals, users, a few ordinary requirements, a rubric line
  or two. The trap sits among them and is never labelled.
- Paraphrase the trap's cues; do not copy them. A sweep that only matches strings is not useful.
- Vary the surface: a rubric item, an "optional stretch goal", a sample-data line, a dependency
  named in passing. Traps hide in lines that look harmless.
- Invent neutral names ("a regional clinic network", "Acme Logistics"). The lint denylist fails on
  programme and project names.

## From a field finding

When a real sweep confirms a trap no case covers: write the trap as a generic catalogue entry,
then a planted case and twin that reproduce its shape with invented names. Record the field source
only in your private notes, never in the skill.
