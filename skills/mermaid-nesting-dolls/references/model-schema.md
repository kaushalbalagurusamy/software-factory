# Model schema

One JSON file describes the whole explorer. `scripts/nesting_dolls.py check` enforces everything marked **checked**.

```json
{
  "meta": {
    "title": "Claude Software Factory",
    "subtitle": "How the factory works, why, and what is missing",
    "repo": "software-factory",
    "commit": "27bf148",
    "generated": "2026-10-19",
    "repoUrl": "https://github.com/owner/repo"
  },
  "workspace": {"root": "/abs/path/to/checkout", "editor": "vscode"},
  "root": "factory",
  "nodes": {
    "factory": {
      "title": "Claude Software Factory",
      "kind": "system",
      "summary": "One or two sentences. Shown in hover tooltips, search and the panel header.",
      "detail": ["Optional extra paragraphs."],
      "design": [{"choice": "What was chosen", "why": "Reason", "alternatives": "What was rejected"}],
      "files": [
        {"path": "factory/cli.py", "lines": "237-293", "contains": "add_subparsers", "note": "why this file matters"},
        {"path": "~/.claude/skills/sf/SKILL.md", "external": true, "lines": "95-100"}
      ],
      "coverage": {"status": "partial", "note": "Why this status.", "gaps": ["Specific missing thing"]},
      "diagram": "flowchart LR\n  a[\"A\"] -->|\"label\"| b[\"B\"]",
      "children": ["a", "b"]
    }
  }
}
```

## Rules

- **Tree, not graph.** Every node except `root` has exactly one parent (**checked**). A node with `children` must have a `diagram` (**checked**).
- **Diagram node ids are model ids.** Each child id must appear in the parent's diagram so it can be clicked (**checked**, and re-checked in the browser by the Check button). Use flowcharts; other diagram types render but cannot be clicked.
- `children` may be a list of ids, or an object `{"id used in the diagram": "global node id"}` when two diagrams reuse a short name (the omm importer does this).
- `diagram` is a string or a list of lines (joined with newlines; easier to edit in JSON).
- **A node with a `diagram` is a "doll"** (drawn as a stacked box, opens its own diagram). A node without one is a leaf (opens its details, shown inside the parent's diagram with a highlight).
- Ids: letters, digits, `-`, `/`; start with a letter; never a Mermaid keyword (`end`, `class`, `graph`, ...) (**checked**).
- Colour comes from `coverage.status`, applied by the viewer, so do not add `classDef`/`style` fills to the Mermaid source. Edge labels and `classDef` strokes are fine.

## coverage.status

| status | use when |
|---|---|
| `built` | Implemented and you saw evidence (a test run, a result file, a deploy) |
| `partial` | Some of it exists; say what is missing in `gaps` |
| `designed` | Specified or planned, no implementation |
| `external` | Lives outside the repository (global skills, hosted services); say where |
| `gap` | Missing, stale or contradictory in a way that matters |

Leave `coverage` off nodes where status is meaningless. Never mark `built` from a document's say-so alone: a claim in a README is a claim, and the explorer exists to separate the two.

## files (grounding)

- `path` is relative to `--repo`. A missing file is an error (**checked**); for `external` or `~/` paths it is a warning.
- `lines` ("10-40" or "12") must lie inside the file (**checked**).
- `contains` is a literal string that must occur in those lines (**checked**). Use it on every file that backs a specific claim: it turns a vague pointer into a verified one and breaks loudly when the code moves.
- A file with neither `lines` nor `contains` draws a warning: it is weakly grounded.

## workspace (optional, editor links)

`workspace.root` is the absolute checkout directory (`/abs/path` or `C:/abs/path`) and `workspace.editor` is one of `vscode`, `cursor`, `windsurf`, `antigravity-ide`, `zed`, `idea`, `sublime`, `textmate` or `none`. Both are **checked**. The viewer joins `root` and a file's `path` to open it in the editor at the first line of `lines`; `?editor=` and `?root=` in the page address override them. Omit `workspace` for a portable file (files then show `Copy path` only). `build --workspace-root DIR --editor NAME` writes it.
