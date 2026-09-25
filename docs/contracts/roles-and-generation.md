# Contract: role specs and generated agent files

Status: published. Role data lives in `factory/agents/roles/<role>.yaml`, one file per role (seven files). Loader: `factory.agents.roles.load_roles(dir=default) -> dict[str, RoleSpec]`. Generator: `factory.agents.generate.generate_agents(profile, roles) -> dict[str, str]` mapping a project-relative path (`.claude/agents/<role>.md`) to file text. Deterministic: same inputs, byte-identical output; no clock, no randomness, no network.

## RoleSpec fields
`id` (one of `orchestrator research design audit implement test review`), `description`, `model`, `core_tools` (list of Claude Code tool names such as Read, Grep, Bash, `Agent(...)` entries), `disallowed_tools`, `skills`, `mcp` (list of `{server, access}` with access `read` or `write`), `spawns` (role ids, or plugin agent names for the review role), `writes` (one of `none`, `app`, `research_dir`, `design_dirs`, `audit_dir`, `eval_paths`), `hooks` (hook ids from `hook-io.md`), `max_tools` (integer, at most 20).

## Generated file
A Markdown file with YAML frontmatter, fields in this order: `name` (the role id), `description`, `model`, `tools`, `disallowedTools` (omitted when empty), `skills` (omitted when empty), `hooks` (omitted when empty; entries use the Claude Code shape `event -> [{matcher, hooks: [{type: command, command: "python -m factory.hooks <hook_id>"}]}]`). Then a body with these sections in order: role purpose, what the agent may write, what it must never do, and the skills to use. No other frontmatter fields.

`tools` is built from `core_tools`, plus for each `mcp` entry with the server present in the profile: `mcp__<server>` if access is `write`, otherwise the server's `read_tools` as `mcp__<server>__<tool>`. A server the profile does not provide is silently omitted. Profile overrides (`agents.<role>`) may change the model, add skills and add profile-declared servers; they may not add write access and may not change `writes`.

The generator raises `GenerationError` if a resulting tool list exceeds `max_tools`, if a role would gain write access it does not have, or if generated text contains a project name from the profile inside a role template body (project facts belong in the profile, not in role text).
