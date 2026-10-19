# PRD template

A PRD is a markdown file. Its one machine-read part is the fenced `yaml scope` block.

```markdown
# PRD: <feature or change>
_Spec: <link to the business-facing spec> · Date: <date> · Status: draft | agreed_

## Source and targets
| Target | Text | Source |
|---|---|---|
| T1 | <spec target, verbatim, with its unit> | spec section |

## Decisions in force
Accepted ADRs and experiment verdicts this PRD builds on, one line each with a link. The PRD does not reopen them.

## Work units
For each unit: a short goal, why the scope is drawn where it is, and what it depends on. The scope block below is the machine-readable form of the same units.

(scope block)

## Shared files
Each shared file (lockfile, manifest, config, CI, migration directory, shared types) and the unit that owns it.

## Open questions
Questions for the business side or for `axiomatic-spec`. Scope change requests from implementers land here.
```

## Scope block

````markdown
```yaml scope
units:
  - id: U1
    goal: "One line"
    serves: [T1]
    owns: ["src/payments/**"]
    new: ["src/payments/refunds.py"]
    reads: ["src/orders/api.py", "docs/adr/ADR-0007-*.md"]
    entry_points:
      - {path: src/payments/charge.py, symbol: Charge.capture, why: "refund mirrors capture"}
    depends_on: []
    confidence: high
```
````

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique, short, stable (U1, U2). |
| `goal` | recommended | One line. Shown in expanded output. |
| `serves` | recommended | Target ids from the spec this unit contributes to. |
| `owns` | yes | Globs the unit may create or edit. Disjoint from every other unit's `owns`. |
| `new` | when creating files | Explicit paths the unit will create. Each must fall under its own `owns`. |
| `reads` | optional | Globs of existing files the unit reads but must not edit. May name another unit's `new` files. |
| `entry_points` | recommended | List of `path`, `symbol`, `why`. The path must exist or be a `new` path. Use symbol names, never line numbers. |
| `depends_on` | optional | Unit ids that must land first. No cycles. |
| `confidence` | optional | `high` (default) or `low`. Low means the scope is a guess and the first step is a bounded exploration. |

Glob syntax: `*` stays within one path segment, `**` crosses segments, `?` is one character, and a trailing `/` means everything below the directory. Character classes are not supported. Paths are relative to the repository root.

## Choosing what goes in `owns` and `reads`

- A file the unit edits belongs in `owns`. A file it only needs to understand belongs in `reads`.
- A test file belongs to the unit whose behavior it covers. Test files an implementer must not see are a later addition and are not part of this version.
- If two units must change the same file, the seam is wrong. Move the shared edit into one unit, or split the file.
- If a unit's `reads` grows past a handful of files, the unit probably spans two seams.
