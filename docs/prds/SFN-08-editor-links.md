# SFN-08: Dashboard and dolls open the exact file in the owner's editor

| | |
|---|---|
| **Delivers** | Owner follow-up 2026-10-20 (`docs/requirements/owner-followup-2026-10-20-lsf.md`): "the nested mermaids will be crucial on the ops dashboard which should open up specific files on our code editor" |
| **Depends on** | none |
| **Implementer model** | Sonnet |

## Purpose
In a review session the owner clicks a node in the nested diagrams and lands in the source at the right line. One small pure function builds the link; every surface that names a file uses it.

## UX story (first)
As the owner reviewing code on the Mac in front of an audience, I click a box in the architecture view, see its files, click `src/qa.py:120-168`, and my editor opens at line 120.

## Required behaviour
- **K-01 the function.** `skills/mermaid-nesting-dolls/assets/editor-links.js` defines, as plain ES5 with no dependencies and a UMD-style export (`module.exports` under Node, `window.SFEditorLinks` in a browser), `editorUrl(editor, root, relPath, line)` returning a string URL or `null`.
- **K-02 schemes.** Editors and their output (root and relPath joined with `/`, each path segment percent-encoded with `encodeURIComponent`, `/` kept): `vscode` -> `vscode://file/<abs>:<line>`; `cursor` -> `cursor://file/<abs>:<line>`; `windsurf` -> `windsurf://file/<abs>:<line>`; `zed` -> `zed://file/<abs>:<line>`; `idea` -> `idea://open?file=<encoded abs>&line=<line>`; `sublime` -> `subl://open?url=file://<abs>&line=<line>`; `textmate` -> `txmt://open?url=file://<abs>&line=<line>`. The `:line` part is omitted when line is missing, not a positive integer, or above 10,000,000. `none` or an unknown editor returns `null`.
- **K-03 safety.** Returns `null` when `relPath` is absolute, contains a `..` segment, a NUL, a backslash, or a scheme prefix (`x:`); when `root` is not an absolute POSIX path (leading `/`) or a Windows drive path; or when either is longer than 4,096 characters. Never returns a `javascript:`, `data:` or `file:` URL. Line may be a number or a numeric string; ranges such as `120-168` are given by the caller as the first number.
- **K-04 explorer viewer.** `skills/mermaid-nesting-dolls/assets/template.html` and the builder inline the function. The model JSON may carry a top-level `workspace: {root, editor}`; the page also accepts `?editor=` and `?root=` query parameters that override it (validated by K-02/K-03; an invalid root is ignored). Each file entry shown in a node's detail panel renders `path:lines` as a link that opens the editor at the first line of its range, plus a `Copy path` button; with editor `none` or no root the entry shows only the copy button and a one-line hint saying how to set the editor. Links are keyboard reachable and at least 40 px tall on touch.
- **K-05 builder.** `nesting_dolls.py build` gains `--workspace-root DIR` and `--editor NAME`, stored in the model's `workspace`; `check` validates them (root absolute, editor in the K-02 list or `none`). Omitting both builds as before (no regression).
- **K-06 ops shell.** `ops/shell/index.html` inlines the same function and renders every file path it already shows (ADR, research, experiment, bug and architecture items) as an editor link or a copy button, reading `editor` and `workspace_root` from `ops/config.json` (served through the runtime file) or `?editor=&root=`. Do not change tab logic otherwise (SFN-03 owns it).
- **K-07 single source.** A test proves the inlined copies in the template, the ops shell and (later) the lsf dashboard are byte-identical to `editor-links.js` between the markers `/* editor-links:begin */` and `/* editor-links:end */`; `nesting_dolls.py check --assets` reports a mismatch as a failure.
- **K-08 demo model.** `docs/explorer/software-factory.html` is rebuilt with `--workspace-root` left unset (portable) and `docs/explorer/README.md` states how to set the editor.

## Acceptance
Graded by hidden evals (Node for K-01..03, a headless browser check for K-04 if available). Write your own unit tests (`skills/mermaid-nesting-dolls/tests/` and `tests/test_editor_links.py`). Where a behaviour and a contract disagree, stop and report.

## Ownership
- **OWN:** `skills/mermaid-nesting-dolls/assets/editor-links.js`, `skills/mermaid-nesting-dolls/assets/template.html`, `skills/mermaid-nesting-dolls/scripts/nesting_dolls.py`, `skills/mermaid-nesting-dolls/references/model-schema.md`, `skills/mermaid-nesting-dolls/SKILL.md` (editor section only), `ops/shell/index.html` (file-link rendering only), `docs/explorer/README.md`, `docs/explorer/*.html` (rebuild), `tests/test_editor_links.py`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/prds/**`, `docs/requirements/**`, `pyproject.toml`, `factory/ops/*.py`, any file another slice owns
- Use `scripts/bounded-pytest.sh`; never read or search `evals/`.
