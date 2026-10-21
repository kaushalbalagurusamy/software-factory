# Software factory explorer

An interactive, nesting-dolls view of this repository: the factory workflow, its design choices, and what is built versus missing.

- Open `software-factory.html` in any browser (one self-contained file, works offline). Click a stacked box to open the diagram inside it; use the breadcrumbs, Home, Back and Up to move; the **Coverage & gaps** tab lists every status with reasons; **Present** hides the side panel and `n`/`p` walk the tree.
- `software-factory.model.json` is the source of truth. Every file path, line range and quoted string in it is checked against this repository.

Regenerate after editing the model (or after the repo changes):

```bash
python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py check docs/explorer/software-factory.model.json --repo .
python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py build docs/explorer/software-factory.model.json -o docs/explorer/software-factory.html --repo .
```

Then open `software-factory.html?check=1`, or press **Check**, to render every diagram and confirm every child is clickable. The skill that produced this is `skills/mermaid-nesting-dolls/SKILL.md`.

The model was refreshed on 2026-10-20 after the lite factory, eli12-docs, editor-links, ops-events and eight-role changes (162 components and 23 diagrams, up from 122 and 16; statuses: 91 built, 42 partial, 18 external, 3 gap, 8 without a status). New or reworked: **Lite factory (lsf)** at the top level (CLI, phase clock and budget, stop ledger and human checkpoints, dashboard server and routes, dashboard tabs, hooks and telemetry, installer); **Docs tools** under the skills library (eli12-docs with its format, scaffold, check codes and index; the explorer with editor links, their inlined copies, build options and the `--assets` drift check); the ops dashboard opened into events, emission from `run_tool` and the hooks, `sf ops` commands, runtime telemetry (repo head, behind, stops, Langfuse), tab sources (one-page PRD, resolved experiments, bug log, human stops), QA promote-notes and the shell banners; the agent layer with eight Sonnet roles, the qa role, the reviewer skills, doctor role-skill and external-pin checks and ADR-0005; and a flow node under the build loop showing sf stages against lsf phases with the four loop-backs. Honest limits recorded in the nodes: the intake gate, a full QA loop with real agents, reviewer amendments and the lsf skill driven by Claude Code have not run in a real session, so those nodes are partial; the lsf experiments collector fails its parity test against `factory/ops` (`tests/lsf/test_hooks_collect.py`); each sub-agent stop is recorded twice. Test and eval counts are not restated here: see `docs/sf-flow.md` (Evidence base) and `docs/adr/ADR-0005-sonnet-only-roles-and-qa-role.md`. `build_model.py` is the generator: edit it and re-run it (`python3 docs/explorer/build_model.py <commit> docs/explorer/software-factory.model.json`); it fills every missing line range from the quoted text (a function or class extent, a Markdown section) and re-anchors each cited range to where the quoted text now is, so a moved line does not silently break the references and an editor link lands on the quoted line. References to untracked files such as `.claude/` are not cited.

## Opening files in your editor

Every file in a node's panel is a link that opens your editor at the first line of its range, with a `Copy path` button beside it. The committed `software-factory.html` is built without a workspace root so it is portable, which means it shows only `Copy path` and a hint until you tell it where your checkout is. Either add the settings to the page address, for example `software-factory.html?editor=vscode&root=/Users/you/software-factory` (editors: vscode, cursor, windsurf, zed, idea, sublime, textmate, none), or build your own copy:

```bash
python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py build docs/explorer/software-factory.model.json -o /tmp/explorer.html --repo . --workspace-root "$PWD" --editor vscode
```

`python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py check --assets` confirms the link builder inlined in the viewer and in `ops/shell/index.html` still matches `skills/mermaid-nesting-dolls/assets/editor-links.js`.
