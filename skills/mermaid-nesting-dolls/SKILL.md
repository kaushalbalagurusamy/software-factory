---
name: mermaid-nesting-dolls
description: >-
  Mermaid Nesting Dolls: build a portable, interactive HTML explorer of a repository or system, where a
  high-level Mermaid architecture diagram opens into more detailed diagrams component by component, recursively,
  with breadcrumbs, back/home navigation, component explanations, design choices, coverage and gaps, and
  source-file references checked against the real repo. Use whenever the user wants to explore, understand,
  document, onboard onto, audit or present a codebase, workflow or architecture as drill-down diagrams, asks for
  "nesting dolls", "click into a component", "interactive architecture diagram", "architecture walkthrough for a
  demo", or "show the overall system and let me zoom in", even if they never say Mermaid. Also use to turn an
  oh-my-mermaid .omm/ scan into a navigable page. Not for a single static diagram (draw it inline instead).
---

# Mermaid Nesting Dolls

The output is one self-contained `.html` file (Mermaid is inlined, no network needed). The first screen is a
systems architecture diagram. Clicking a stacked box opens the diagram inside it, and so on down to leaf
components. A side panel explains whatever is selected: what it does, the design choices behind it, the source
files that back it (verified), and how complete it is.

Why a model file instead of hand-written HTML: the value is in the *content being true*. The builder checks
every file path, line range and quoted string against the repository, so a presenter can click through
without finding a stale reference. Keep the content in `model.json` and regenerate the HTML.

## Workflow

1. **Pin the story.** Ask what the audience needs to leave with (understand the workflow, present design
   choices, see what is missing). A system has many valid decompositions; pick the one that serves that
   story, usually flow of work at the top and ownership/files underneath.
2. **Explore for evidence, not impressions.** Read the manifests, entry points, docs and tests. Reuse what
   exists before writing new analysis: `brownfield-explorer` for large repos, and oh-my-mermaid when its plugin
   is installed (`/omm-scan` writes `.omm/`; `scripts/nesting_dolls.py import-omm .omm -o model.json` turns
   that tree into a starting model). Note what you could not verify as you go.
3. **Draft `model.json`** (schema: `references/model-schema.md`). Rules of thumb that make it readable:
   - Top level: 5 to 9 components with labelled edges that say *why* they connect, not just that they do.
   - Open a component into a diagram only when it has distinct parts. A single file or a trivial wrapper is a leaf.
   - At most about 9 nodes per diagram and 3 to 5 levels deep. Past that, split a level rather than shrink text.
   - Short labels (`Title<br/>path/`); put explanation in the panel, not in the node.
   - Fill `design` with the choice, the reason and the rejected alternative. That is the part people present from.
   - Be harsh and specific in `coverage`. A `gap` or `partial` with a named missing thing is more useful than
     an all-green picture, and the Coverage tab collects them.
   - Back claims with `files` using `lines` and `contains`; check cites by running the checker, not by memory.
4. **Check, then build:**
   ```bash
   python3 <skill>/scripts/nesting_dolls.py check model.json --repo .
   python3 <skill>/scripts/nesting_dolls.py build model.json -o explorer.html --repo .
   ```
   Fix every `ERROR`. Treat each `warn` as a decision: either add `lines`/`contains` or accept it knowingly.
5. **Verify in a browser** (the checker cannot parse Mermaid). Open `explorer.html?check=1` or press the Check
   button: it renders every diagram and confirms each child is a clickable node; the result is also in
   `window.__ndCheck`. Then click from the top to a leaf and back with Back/Home/breadcrumbs. Common failures:
   an id that is a Mermaid keyword, `<` or `>` in a label (use `&lt;`), an unquoted label with parentheses.
6. **Deliver** the file path and what was verified. Publishing, deploying or hosting is a separate decision for
   the owner; do not do it unprompted.

## Presenting

`Present` hides the side panel; `n`/`p` walk the tree depth-first, `h` home, `u` up, `/` search, `f` present,
Alt+← back. The Coverage tab lists every status with the reasons: the honest closing slide.

## Files

- `scripts/nesting_dolls.py`: `check`, `build`, `import-omm` (Python 3 standard library only).
- `assets/template.html`: the viewer. `assets/vendor/`: Mermaid (version in `VERSION`, MIT licence file alongside).
- `references/model-schema.md`: the model format and the rules the checker enforces.
- A worked example lives in the repository that first used it: `docs/explorer/` in software-factory.

## Loading a model at view time

`assets/template.html` embeds the model by default. When the embedded model is empty (a viewer built with `__MODEL_JSON__` replaced by nothing, as `python -m factory.ops bundle` does for `ops/viewer.html`), it loads the model from the `?model=<url>` query parameter instead and shows the error on the page if the load fails. The normal `build` output is unchanged.
