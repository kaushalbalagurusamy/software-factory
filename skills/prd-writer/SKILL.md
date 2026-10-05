---
name: prd-writer
description: >-
  Writes the developer-facing PRD, whose work units each carry a file scope: the files a unit owns,
  the files it may read, and the entry points to start from. Use this whenever a business-facing spec
  and its decisions exist and work is about to be handed to implementers, and whenever someone asks to
  split or partition work, say what files each part touches, scope an implementer, or cut down the
  searching and repo-structure context an agent spends on every task. The scope acts as a soft
  sandbox, so implementers start from a known map instead of grepping. It does not write the
  business-facing spec (spec-writer), choose architectures, or write axioms (axiomatic-spec).
---

# prd-writer

The business-facing spec says what must be true. The PRD says how the work divides and where each piece lives, in terms an implementer can act on without exploring the repository first. It runs at station 7 of the build loop, before `axiomatic-spec` derives axioms and contracts from it.

This version of the PRD carries file scope. Contracts, per-unit budget shares, and held-out QA cases attach to the same work-unit table in later iterations. Leave those fields out until then, because an empty field reads as a requirement that was considered and found trivial.

## Why file scope

An agent that does not know where a change belongs searches for it. Every search spends tokens, and the answers are often wrong or partial. Repo-structure listings in `CLAUDE.md` try to solve this for every task at once, so they load into every session whether or not the task needs them. A per-unit scope gives the same orientation only to the agent that needs it: the files it may change, the files it should read, and where to begin.

The scope is a soft sandbox. It tells the implementer where to work and lets a reviewer see when it left. It does not stop an agent from reading or editing elsewhere. A hard allowlist enforced by a hook or worktree comes later, once the scopes have proved accurate.

## Inputs

- The business-facing spec and its target ids.
- Accepted ADRs and experiment verdicts. They fix the decisions the PRD must not reopen.
- A `brownfield-explorer` map when the repo already exists. Use it to find seams instead of searching again.
- The repository checkout, so paths and symbols can be verified.

## Writing the work units

1. **Split along seams.** A unit is one coherent change an implementer can finish alone. Cut where modules, packages, or interfaces already divide the code.
2. **Give each unit a scope.** `owns` lists the globs it may create or edit. `new` lists explicit paths it will create. `reads` lists files it needs for context and must not edit. `entry_points` lists path, symbol, and a reason, so the implementer starts at the right place.
3. **Keep scopes small and disjoint.** Every file has exactly one owner. Prefer directories and explicit files over wide globs, and use `**` only inside the unit's own package. Never use a root wildcard.
4. **Assign shared files once.** Lockfiles, manifests, config, CI, migrations, and shared types go to one unit. Other units list them under `reads` and raise a request to change them through the PRD's open questions.
5. **Find entry points now.** Search for the symbols while writing the PRD so no implementer has to. Use symbol names, not line numbers, because line numbers go stale.
6. **Keep `reads` short.** Its length is the unit's context budget. Include the interface files of dependencies and the relevant ADRs, not whole packages.
7. **Say when the scope is a guess.** Set `confidence: low` when no explorer map backs it. The unit's first step is then a bounded exploration, and its report states the real scope.

Put the scope in one fenced block labelled `yaml scope` inside the PRD. `references/prd-template.md` has the layout and the field list.

## Check the scope

Run the checker from this skill's directory against the repository:

```
python scripts/check_scope.py PRD.md --repo <repo root>
```

It reports errors for overlapping owners, globs that match nothing, paths that do not exist, dependency cycles, and root wildcards. It warns about stale symbols and wildcard scopes that might overlap on files not yet created. Fix every error. Read every warning and either fix it or leave a reason in the PRD. Overlap in particular cannot be judged reliably by eye, which is why the check exists.

## Handing a scope to an implementer

Print the concrete file lists for the unit:

```
python scripts/check_scope.py PRD.md --repo <repo root> --expand U1
```

Put that output in the implementer's brief with these instructions: work inside `owns`, read the files listed under `reads`, start from the entry points, and do not search the wider repository. If a file outside the scope is needed, name it and say why in the report instead of going to find it. The implementer is told to ask; nothing prevents it from looking, so the PRD's value depends on how accurate the scope is.

After the unit is done:

```
python scripts/check_scope.py PRD.md --repo <repo root> --unit U1 --diff
```

This lists every changed file outside the unit's scope and says which unit, if any, owns it. It reports and never reverts. A stray edit is a signal that the scope was wrong or the implementer drifted, and a person or the coordinator decides which.

## Repo structure in CLAUDE.md

When a task has a PRD scope, directory listings in `CLAUDE.md` duplicate it. Propose removing them to the user and let them decide, since `CLAUDE.md` serves tasks that have no PRD. Conventions, commands, and rules stay where they are.

## Boundaries

This skill does not write the business-facing spec, choose architectures, or write axioms and contracts. It does not enforce the scope. If the decisions a PRD depends on are not yet recorded, stop and say which ones, instead of making them inside the PRD.

## Reference files

- `references/prd-template.md`: the PRD layout and every scope field. Read it before writing a PRD.
- `references/example-prd.md`: a short PRD whose scope block names real paths in this repository and passes the checker.
- `scripts/check_scope.py`: the checker. Run it with `--help` for the options.
