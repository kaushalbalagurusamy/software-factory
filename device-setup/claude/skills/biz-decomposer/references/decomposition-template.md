# decomposition.md layout

```markdown
# Decomposition: <project or feature name>
_Source: <spec file or stakeholder statements> · Date: <date> · Round cap: <n>_

## Terminal requirements
| Id | Verbatim text | Owner | Target (with unit) | Source |
|---|---|---|---|---|
| T1 | ... | ... | ... | spec line or statement |

## Requirement tree
- T1 <short name>
  - D1.1 derived requirement  (leaf: question | choice | ready)
  - D1.2 ...
    - D1.2.1 ...  (leaf: question)

## Constraints
Budget, latency, compliance, team, existing systems. One line each, with source.

## Assumptions ledger
| Id | Assumption | Validation (unvalidated / how) | Cost of being wrong | Confidence | Seed |
|---|---|---|---|---|---|

## Door classification
| Leaf | Door | Uncertainty | Seed or "decide in build" |
|---|---|---|---|

## Questions for the human
Business intent, priority, and budget questions that research cannot answer. Each states what depends on the answer.

## Seeds
Pointer to `seeds.yaml`, with the ranked list and each route in one line.
```

Re-entry mode appends a dated section per round: assumption updates, target status (met, unmet, unknown, with measured value), and the gap reports handed back to research.
