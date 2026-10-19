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

The model was refreshed on 2026-10-19 after the sf toolchain build (120 components, 16 diagrams). `build_model.py` is the generator: edit it and re-run it (`python3 docs/explorer/build_model.py <commit> docs/explorer/software-factory.model.json`); it re-anchors each cited line range to where the quoted text now is, so a moved line does not silently break the references. Statuses reflect that checkout and the evidence quoted in each node (4,017 unit tests and 1,497 of 1,498 eval cases pass; golden gate 141 of 141).
