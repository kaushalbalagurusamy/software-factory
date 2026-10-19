# Native Claude Code installation

`python -m factory.install` wires the factory into a project so the hooks, the seven role agents and
the Sonnet-only model routing apply in a real Claude Code session. The orchestrator exposes it as
`sf install`, `sf doctor`, `sf hitl`; until then call the modules directly.

```
python -m factory.install install   --project DIR [--factory-root DIR] [--python PATH] [--profile FILE]
                                    [--no-hooks] [--no-agents] [--allow-model NAME ...] [--dry-run]
python -m factory.install uninstall --project DIR
python -m factory.install doctor    [--project DIR] [--skills-dir DIR] [--json] [--allow-model NAME ...]
python -m factory.hitl request|status|release --root R ...
```

Exit codes (install, uninstall, doctor): 0 ok, 1 failure, 2 usage.

## What `install` writes (all under DIR; no git command is ever run there)

| File | Content |
|---|---|
| `.factory/profile.yaml` | Only if absent: copied from `--profile` or a minimal default (generic `evals/**`, `tests/held_out/**`, `tests/frozen/**`, `evals/baselines/**`; main session role `orchestrator`; the `graph` key omitted so the standard default graph applies; project name `project-<hash of path>`). An existing profile is validated and **never modified**. |
| `.claude/agents/<role>.md` x7 | From `generate_agents`, then post-processed deterministically (below). |
| `.claude/settings.json` | Existing file merged, never replaced: every unrelated key, user hook and the whole `permissions` object are preserved. Adds the hooks, `"model": "sonnet"` and `env` pins. |
| `.factory/install-manifest.json` | Factory version/commit/root, python, model pin, per-file sha256, `created` vs `existing` origin, backups. No timestamps (so a re-run is byte-identical). |
| `.claude/backups/<UTC stamp>/...` | The previous version of any file that differed, taken before it is overwritten. |

The installer adds no `permissions.allow` entry and does not touch `permissions`.

### Hook commands and the fail-open caveat

Claude Code treats a hook command that cannot run (exit other than 2) as a **non-blocking error**.
A project whose hooks say `python -m factory.hooks <id>` on a machine where that is unresolvable
therefore runs with no guard at all, silently. The installer writes the prefix-rewritten, absolute
form and verifies it:

`PYTHONPATH=<factory root> <absolute python> -m factory.hooks <id>`

(suffix unchanged). The root defaults to the checkout containing the installer; the interpreter to
`--python` or `<root>/.venv/bin/python`. It must exist and import `factory.hooks`, `z3` and `yaml`,
else the install fails before writing anything. The venv interpreter path is kept unresolved on
purpose (resolving a venv symlink would lose the venv). The same absolute command is written into
the agent files' frontmatter hooks, although project-subagent frontmatter hooks need folder trust
and are not relied on: the settings-level hooks (which also work headless and receive `agent_type`
and `agent_id`) are the enforcement.

### Sonnet-only routing, and why

The user-level settings may inherit an Opus default; that must not apply to factory work. Project
settings pin `"model": "sonnet"` and `env` `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`,
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (project `env` is honoured even in untrusted folders). The
role specs propose `opus` for orchestrator, design, review and test; the installer rewrites the
generated frontmatter to `model: sonnet` (the role YAMLs and any existing profile are untouched)
and records proposed vs pinned per role in the manifest. `--allow-model opus` explicitly lets a
role keep a proposed model that is in the allowed set; the settings pin stays `sonnet`, and
`doctor` then also needs `--allow-model`.

## Idempotence, dry run, rollback

* A second run with the same arguments writes nothing: no file changes, no new backup, output
  `unchanged`. A settings file already semantically equal is left byte-for-byte alone.
* `--dry-run` prints a unified diff per file and writes nothing.
* `uninstall` reads the manifest. A file still equal to the installed hash is removed (origin
  `created`) or restored from its first backup (origin `existing`). A file whose hash changed is
  **refused** and reported on stderr (exit 1); other files are still processed and the manifest
  keeps the refused entries so a retry is possible. Unrelated files are never touched; backups are kept.

## doctor

One line per check, `PASS`/`FAIL`/`SKIP` plus the exact cause; exit 1 on any FAIL; `--json` for tools.
It does not invoke `claude`. Checks: factory, z3 and yaml importable with the configured python; for
each skill in the repo `skills/` dir (13) the installed entry exists, is a symlink to the repo copy or
an identical copy, and its `SKILL.md` has `name` equal to the directory and a description; `sf`
resolves on PATH and `sf --help` runs and identifies as the factory CLI. With `--project`: valid
`settings.json`; model and env pins; a registered hook for every id used by the roles; **every hook
command executed** (in a scratch dir holding a copy of the profile, with the caller's `PYTHONPATH`
removed so the command's own is proven) with a canned benign `PreToolUse` payload (must exit 0; Stop,
SubagentStop and SessionStart hooks get a canned event payload and must exit 0 or 2, the only codes
the hooks can produce, so a non-run fails) and the deny payload (`git add -A` as role `implement`
against `bash_guard`, must exit 2); agent files exist with an allowed model; profile validates;
manifest hashes match (the profile is exempt, being user-editable); no `permissions.allow` entry
that mentions `factory.` or the installed python.

## Human stop (`python -m factory.hitl`)

* `request --root R --name N --reason TEXT [--scope run|slice:<id>] [--by WHO]` writes
  `R/.sf/stops/N.json` and appends a hash-chained entry to `R/.sf/stops/log.jsonl`.
* `status --root R [--scope S]` lists open stops. Exit 0 none applies, **3** an open stop applies
  (a `run` stop applies to every scope), **4** the ledger fails verification (fails closed).
* `release --root R --name N --by human:<ref>` appends a release and deletes the stop file. `--by`
  must start with `human:` and carry a reference; `agent:`, `subagent:` and `codex:` are refused
  with exit **5** (codex approval is not enough here).
* Tamper detection: the log is a hash chain; each open stop's file must exist and match the hash
  logged at request time, and no unlogged stop file may exist. Editing or deleting a stop file,
  editing, reordering or truncating the log, or forging a release line all yield exit 4.
* Integration: `python -m factory.slices done DIR [--root R]` exits **5** while an open stop
  applies to `slice:<DIR name>` or the run (or the ledger is tampered); R defaults to the nearest
  ancestor of DIR holding `.sf/stops`. `python -m factory.qa next` returns
  `{"action": "human_stop", "stops": [...]}` (never retry, escalate or accept, and `--apply` changes
  nothing) while a stop applies or the ledger is tampered.

Limits: `--by human:<ref>` is a declaration, not authentication; an agent with Bash can type it.
The chain catches edits, not a deliberate rewrite of the whole `.sf/stops` directory. Enforcement
against agents needs a `bash_guard` rule denying `factory.hitl release` for non-human roles (hooks
are outside this slice).

## Verification status

| Claim | Verified by unit tests (`tests/test_install.py`, `tests/test_hitl.py`) | Verified in a real Claude Code session |
|---|---|---|
| Install is idempotent, backs up once, preserves user settings and `permissions` | yes | not yet |
| Agent files all `model: sonnet`; settings pin and env written | yes | not yet |
| Unresolvable or z3-less python refused; nothing written | yes | not yet |
| Hook commands execute with the canned benign and deny payloads (exit 0 / 2) | yes (subprocess, as `sh -c`) | not yet |
| Doctor FAILs on a command that cannot run, a missing hook, a non-sonnet agent, a missing pin | yes | not yet |
| Uninstall restores; modified file refused | yes | not yet |
| `done` and `next` honour the stop; agent release refused; tamper exits 4 | yes | not yet |
| Claude Code honours `model`/`env` pins, runs settings hooks headless, passes `agent_type` | no | **not yet** (taken from the docs) |
| Subagents actually run on Sonnet whatever the user default | no | **not yet** |
| A denied tool call is blocked inside a live session | no | **not yet** |
| Frontmatter hooks in agent files behave (need folder trust) | no | **not yet** |
