# Token-saving options for Claude Code sessions (summer 2026 onward)

> **Scope:** built-in Claude Code features, MCP protocol patterns, and third-party skills, MCP servers, hooks and proxies that reduce tokens per Claude Code session. Excludes generic prompt-writing advice and API-only features we cannot use from Claude Code. Nothing was installed or measured locally for this report.
> **As of:** 2026-10-10, Claude Code 2.1.296. Goes stale with each Claude Code release and each tool's next version; savings figures are the most perishable part.

## Headline

1. **The biggest wins are already built in and mostly configuration:** deferred MCP tools (tool search), skills instead of long CLAUDE.md, subagents for verbose work, lower effort or a smaller model per subagent, and `/usage` attribution to find the actual cost driver.
2. **Third-party "token savers" are unproven and can backfire.** The only independent measurement found (DEV, 7 Oct) reports rtk +7.1%, caveman +10.9% and pxpipe +196.7% cost-weighted tokens versus no tool, because they added turns or per-call overhead. Measure before adopting any of them.
3. **For our VPS specifically:** idle-session costs (cross-session messages, scheduled wake-ups, goal check-ins) and cache misses after breaks resend the full context. These are directly relevant to the multi-session setup here.

## 1. Built-in Claude Code features (primary source: official docs and changelog)

| Feature | What it saves | Notes |
|---|---|---|
| MCP tool search (deferred tools, default on) | Tool schemas stay out of context until used; only names and server instructions load | Already active on this VPS. Changelog 2.1.295–2.1.296 changed description caps (4,096 chars up front, 16,384 via tool search). Disconnect unused servers with `/mcp`; prefer CLIs (`gh`, `railway`) over MCP where both exist |
| `/usage` attribution and behaviour flags | Shows which skills, subagents, plugins, MCP servers and loops use the most; flags long context and cache misses | Docs; per-loop rows need v2.1.242+. The first thing to run before buying any tool |
| Prompt cache line in `/usage` | Shows cache hit share, misses and their likely cause (v2.1.251+ / v2.1.260+) | A miss re-bills the whole context |
| Cache lifetime | 1 h on a subscription; drops to 5 min when drawing on usage credits unless you choose the TTL | Relevant if the owner's "credit reset" is usage credits — confirm |
| `crossSessionInbound: hold` | Stops idle sessions waking for every peer message (each wake resends full context) | Directly relevant to SF broadcasts to 7 sessions |
| `CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0` | Turns off idle goal check-ins (each resends full context) | Docs |
| Subagents with `model: haiku` and per-subagent `effort` | Keeps verbose output out of the main context and runs it cheaper | `effort` on the Agent tool added 2.1.292; `autoCompactWindow` per subagent 2.1.296 |
| Skills instead of CLAUDE.md | Skills load only when invoked; docs say keep CLAUDE.md under 200 lines | Our global CLAUDE.md and skill descriptions are always-loaded cost |
| Hooks that pre-filter output | Docs example: PreToolUse hook rewrites test commands to show only failures | The safe, local version of what rtk does |
| Code intelligence plugins | LSP "go to definition" replaces grep plus reading candidate files | Official plugins for typed languages |
| `/effort`, `MAX_THINKING_TOKENS` | Thinking is billed as output | Adaptive models (5.5 family) ignore budgets; use effort |
| `/clear` vs `/compact` | `/compact` is itself a large request; `/clear` is free | Docs |
| Resume from a summary | After a long break, resumes from a summary instead of full history (Pro/Max) | Docs |
| Pricing changes | Sonnet 5.5 cache reads now $0.10/Mtok (2.1.296); Haiku 5.5 at $0.10/$0.50 (2.1.293) | Makes cache hits and Haiku subagents cheaper |

Confidence: confirmed against the official costs page and changelog.

## 2. MCP protocol patterns (primary source: MCP docs, 2026-07-28 version)

- **Progressive discovery:** host loads tool definitions only on demand via a `search_tools` meta-tool; also connect and disconnect whole servers per task. A skill can declare which servers it needs. Claude Code already does tool-level deferral.
- **Programmatic tool calling ("code mode"):** the model writes a script that calls tools in a sandbox; only the final output returns. The docs illustrate ~150,000 → ~2,000 tokens. Not something we enable in Claude Code itself; it matters if we build our own agents (e.g. the factory, Grokbot intake).
- **Caching hints:** list results carry `ttlMs` and `cacheScope`; the docs warn that adding or removing tools mid-conversation breaks the prompt cache and can cost more than it saves.

Confidence: confirmed against the MCP docs page.

## 3. Third-party add-ons (all savings figures self-reported unless stated)

| Tool | Type | Layer | Claimed saving | Caveats |
|---|---|---|---|---|
| **context-mode** (mksglu) | MCP server + hooks plugin | Large tool outputs go to a sandbox and SQLite FTS index; only summaries enter context | 98% on its own 14 scenarios | Hooks on every tool call; full value needs the plugin, not MCP-only |
| **headroom** (headroomlabs-ai, Apache-2.0) | Local proxy (`headroom wrap claude`) | Compresses tool output, logs, files, history; reversible via `headroom_retrieve` | 60–95% structured data, 15–20% code | Proxy sits between Claude Code and the API: sees all traffic and keys. v0.30.0 dated 2026-07-03 |
| **rtk** (Rust Token Killer) | CLI proxy + Bash hook | Compresses shell command output | 60–90% | Independent test: **+7.1%** (extra turns to recover cut output); doesn't touch Read/Grep |
| **caveman** | Skill (+ proxy option) | Makes replies terse | 65% output | Independent test: **+10.9%** (~2,900-token rules paid every call) |
| **pxpipe** | Local proxy | Renders bulky context as images | — | Independent test: **+196.7%** |
| **Serena** | MCP server (MIT) | LSP-based symbol retrieval, 40+ languages | "30x" (marketing) | Overlaps official code-intelligence plugins |
| **jcodemunch-mcp** | MCP server | tree-sitter symbol fetch | 80–99% | Self-reported |
| **token-savior** (Mibayy) | MCP server | Structural navigation + memory | −45% cost on its 8-task re-run (2026-10-07) | Earlier result withdrawn 2026-08-10; single self-run benchmark |
| **super-token-saver** (ww-w-ai) | Plugin | Session restore with no LLM calls, cache-expiry prevention, cost dashboard | — | Not evaluated |
| **claude-token-efficient** | CLAUDE.md snippet | Terse output | — | Same overhead risk as caveman |
| **lean-ctx, sqz, code-context-engine, Bifrost Code Mode** | Various | Read compression, output compression, code index, MCP gateway | 60–95% | Leads only; not checked |

## Common misconceptions

- "Less output per step means fewer tokens." Not if the model takes more steps to recover what was cut (rtk result).
- "A terse-output skill is free." Its instructions are paid on every call.
- "MCP tool definitions eat 30–60k tokens." Older measurement; Claude Code now defers them by default.

## Recommendation (nothing installed)

1. Run `/usage` breakdown in two or three busy sessions (Meridian, Equinox, Cerbo) to see what actually dominates; the DEV author found 42% was always-loaded context and 6% command output.
2. Try the zero-install levers first: `crossSessionInbound: hold` on sessions that don't need peer messages, Haiku or low-effort subagents for test runs, trimming CLAUDE.md and skill descriptions, a local failure-only test-output hook.
3. If a third-party tool is still wanted, trial **context-mode** or **headroom** in one session with a before/after `/usage` comparison over the same tasks; skip caveman and pxpipe given the independent result.

## Open questions

- Is the owner's "credit reset" usage credits (5-minute cache TTL) or a plan reset? Changes how costly breaks are.
- No independent benchmark exists for context-mode, headroom, Serena or token-savior.
- The DEV post's year is not stated in the body; it is consistent with 2026 given the tool versions.

## Sources

**Primary**
- Claude Code docs, Manage costs: https://code.claude.com/docs/en/costs — built-in features, idle costs, hook example
- Claude Code changelog: https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md — 2.1.288–2.1.296 items
- MCP client best practices (2026-07-28): https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices — progressive discovery, code mode, caching
- Anthropic engineering, code execution with MCP: https://www.anthropic.com/engineering/code-execution-with-mcp

**Independent measurement**
- DEV, "Token-saving tools made my Claude Code usage go up": https://dev.to/awesome_fredtv_c0c3/token-saving-tools-made-my-claude-code-usage-go-up-heres-the-measurement-edk

**Project pages (self-reported claims)**
- context-mode: https://glama.ai/mcp/servers/mksglu/claude-context-mode
- headroom: https://gittrend.io/repo/chopratejas/headroom ; https://noqta.tn/en/blog/headroom-ai-context-compression-token-cost-reduction-2026
- caveman: https://github.com/juliusbrussee/caveman
- token-savior: https://github.com/mibayy/token-savior
- super-token-saver: https://github.com/ww-w-ai/claude-code-token-saver
- claude-token-efficient: https://github.com/drona23/claude-token-efficient
- jcodemunch-mcp: https://gittrend.io/repo/jgravelle/jcodemunch-mcp
- Serena guide: https://mcp.directory/blog/serena-mcp-complete-guide-2026

**Community roundups (leads only)**
- https://computingforgeeks.com/reduce-claude-code-token-usage-tools/
- https://www.deployhq.com/blog/free-github-repos-for-claude-code
- https://www.getmaxim.ai/articles/open-source-mcp-gateways-claude-code/
- https://github.com/topics/token-optimization

**How to refresh:** re-read the Claude Code changelog from 2.1.296 on and the costs page; re-search for independent benchmarks of the tools in section 3; re-check headroom and context-mode release notes.
