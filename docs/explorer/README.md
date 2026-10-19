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

The model was written at commit `27bf148` on branch `agent-graph` (2026-10-19). Statuses reflect that checkout; the test result quoted in the model (31 passed, 9 failed) came from a clean virtualenv with pytest and pyyaml only, without the sibling `unity` repository.
