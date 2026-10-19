# Hook: `secrets_guard`

Module `factory/hooks/secrets_guard.py` (TB-07; requirements R-12, R-23). Run as `python -m factory.hooks secrets_guard`. Registered for every role with matcher `Write|Edit|MultiEdit|NotebookEdit|Bash`.

## What it does
Stops a secret value from being written into a file or typed into a command. It inspects, for every role:

| Tool | Field |
|---|---|
| Write | `content` |
| Edit | `new_string` |
| Bash | `command` |

Other tools are allowed. A missing field is allowed; a field that is present but not a string is denied (`hook error: ...`). Malformed stdin is denied by the core adapter (`hook error:`, exit 2).

## Denied values
`sk-or-v1-` + 20 or more hex; `sk-ant-` + 20 or more URL-safe; `sk-` + 32 or more alphanumerics; `ghp_`, `gho_`, `ghs_`, `github_pat_` + 20 or more alphanumerics or `_`; `glpat-` + 20 or more (`A-Za-z0-9_-`); `AKIA` + 16 uppercase alphanumerics; `xox[baprs]-` + 10 or more (`A-Za-z0-9-`); `AIza` + 35 or more URL-safe; a PEM header `-----BEGIN ... PRIVATE KEY-----`; and an assignment (`=`, `:`, `:=`, `=>`, quoted or unquoted name) of a quoted value of 16 or more characters to a name containing `api_key`, `apikey`, `secret`, `token` or `password` (case-insensitive).

## Allowed
- References by name: `$NAME`, `${NAME}`, `os.environ["NAME"]`, `process.env.NAME`, and a quoted value that is exactly a variable reference (`"${X}"`, `"$X"`; clarification A-07-2).
- Bare mentions of a key's shape or name without a value.
- Placeholders. The text inspected is the whitespace- or quote-delimited token containing the match (A-07-3), the match, and the part after the fixed prefix (for assignments, the quoted value). It is a placeholder if it is one repeated character, contains `xxxx`, `example`, `placeholder`, `your`, `changeme`, `<` or `>` (any case, A-07-4), or ends in `...`.
- Values matching any regex in `profile.secret_allow_patterns` (`re.search` against the matched value or its token).

## Output and privacy
A deny reason names the pattern kind and line number(s), never the value: `secret value in Bash command (anthropic key at line 2). Reference it by variable name ...`. The module exports only `decide`; it has no `record`, logs nothing and persists nothing. No network or model call.

## Example (R-24)
Synthetic key built from fragments so that no key-shaped literal is stored (R-23):

```python
import json
key = "sk-" + "ant-" + "a1B2c3D4" * 4
payload = {
    "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": ".",
    "tool_input": {"command": 'export OPENROUTER_API_KEY=ok\ncurl -H "x-api-key: ' + key + '" https://example.test'},
}
# echo "$(python build.py)" | python -m factory.hooks secrets_guard
```

Recorded result: exit code 2, stderr

```
secret value in Bash command (anthropic key at line 2). Reference it by variable name (for example $NAME or os.environ) instead of writing the value.
```

Replacing the key with `$ANTHROPIC_API_KEY` gives exit 0 and empty stdout.

## Known limits
- Placeholder detection is token-based per the clarification, so a real value sharing a token with a placeholder word (for example `your_key=<real value>` with no spaces) is allowed. Not verified against any eval.
- Prefixes are matched without a word boundary. Unquoted assignments (`TOKEN=value`) are not caught unless the value has a known key shape.
- A value that is all one repeated character after its prefix is treated as a placeholder (reading of A-07-3 for `sk-000...0`; unverified).

Unit tests: `tests/hooks/test_secrets_guard.py` (`python -m pytest tests/hooks/test_secrets_guard.py`).
