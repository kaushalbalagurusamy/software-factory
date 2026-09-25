# Ambiguities found while writing the TB-04 to TB-08 evals

All 30 first-round entries and the four second-round points are **RESOLVED** by `docs/contracts/clarifications.md` (binding), and the listed cases now pin each resolution.

## Second-round points (all RESOLVED by the "Second round" section of clarifications.md)

- **U-1. git pathspec that is an unprotected ancestor (TB-06).** RESOLVED by [U-1]: denied unless every pathspec after `--` is neither protected nor an ancestor of a protected path. Pinned by TB06-D-213 (restored), D-225 to D-229.
- **U-2. What counts as a "protected fragment" (TB-06).** RESOLVED by [U-2]: a protected directory segment or a protected glob match; a bare file name alone does not count. Pinned by TB06-D-230 to D-233.
- **U-3. The /tmp exemption after `..` (TB-08).** RESOLVED by [U-3]: normalise first, so `/tmp/../etc` and `../sibling` are not exempt. The door pair TB08-D-098/099 is restored to `rm -rf /tmp/../etc`. Also pinned by TB08-D-176 to D-179.
- **U-4. No-folder reason for an unknown agent type (TB-05).** RESOLVED by [U-4]: the reason reads `unknown agent type <type>`. Pinned by TB05-D-133 and D-134.

No point is still unsettled.

## TB-04 hook core

- **A-04-1. Fail closed when the event is unknown.** RESOLVED by [A-04-1]: always a deny, exit 2 with `hook error:` on stderr, whatever the hook id. Pinned by TB04-D-020, D-021 and D-028 (tightened from either-reading), plus D-047 and D-048.
- **A-04-2. Seven or eight hook ids.** RESOLVED by [A-04-2]: eight, all known to the registry. Pinned by TB04-D-029 to D-032 and D-049 to D-052.
- **A-04-3. `$FACTORY_PROFILE` versus `.factory/profile.yaml`.** RESOLVED by [A-04-3]: the environment variable wins. Pinned by TB04-D-053.
- **A-04-4. "reason: required when kind != allow".** RESOLVED by [A-04-4]: `ValueError` for an unknown kind, or for a non-allow decision with an empty reason. Pinned by TB04-D-054 to D-058.
- **A-04-5. Table cells marked "not used" and non-guard events.** RESOLVED by [A-04-5]: on Stop and SubagentStop, deny, ask and block give the block JSON; on PreToolUse, block acts as deny; on PostToolUse and SessionStart, any non-allow exits 0 with the reason on stderr. Pinned by TB04-D-059 to D-067.
- **A-04-6. Module of the core API.** RESOLVED by [A-04-6]: importable from `factory.hooks.core` and re-exported from `factory.hooks`. Pinned by TB04-D-068.

## TB-05 path guard

- **A-05-1. Bash writes by full-mode roles.** RESOLVED by [A-05-1]: not inspected (allowed). Pinned by TB05-D-123 to D-126.
- **A-05-2. Redirection inside awk.** RESOLVED by [A-05-2]: only shell redirection is checked. Pinned by TB05-D-093 and D-127.
- **A-05-3. Command substitution in double quotes.** RESOLVED by [A-05-3]: only single quotes exempt it. Pinned by TB05-D-080 and D-128 to D-130.
- **A-05-4. "Allowed folders" for roles with none.** RESOLVED by [A-05-4]: the reason says `no write access for role <role>`. Pinned by TB05-D-131 and D-132. See U-4 for the unknown-role wording.
- **A-05-5. Implement writing factory control files.** RESOLVED by [A-05-5]: implement may not write under `.factory/**`. Pinned by TB05-D-115 to D-117.
- **A-05-6. A new file under a symlinked directory.** RESOLVED by [A-05-6]: the nearest existing ancestor is resolved through symlinks. Pinned by TB05-D-118 to D-122.

## TB-06 blindness guard

- **A-06-1. Bare `pytest` with no path.** RESOLVED by [A-06-1]: denied; unprotected, non-ancestor paths are allowed. Pinned by TB06-D-182 to D-186.
- **A-06-2. The protected directory itself.** RESOLVED by [A-06-2]: `evals/**` matches `evals`. Pinned by TB06-D-216 to D-218.
- **A-06-3. Tilde forms.** RESOLVED by [A-06-3]: `~` is HOME and `~+` the current directory; `~-` and `~user` are denied when the remainder is protected or unresolvable. Pinned by TB06-D-051, D-193 to D-195 and D-219 to D-221.
- **A-06-4. `$VAR` with no protected fragment.** RESOLVED by [A-06-4]. Pinned by TB06-D-049, D-050, D-052 and D-187 to D-192. See U-2 for the meaning of "fragment".
- **A-06-5. Standalone `base64 -d`.** RESOLVED by [A-06-5]: denied. Pinned by TB06-D-196 and D-197.
- **A-06-6. `git status` or plain `git diff` with no path.** RESOLVED by [A-06-6]: status and diff are allowed; log, show, blame, grep, ls-files, ls-tree, cat-file and archive need an unprotected pathspec after `--`. Pinned by TB06-D-198 to D-212, D-214 and D-215. See U-1 for the ancestor-pathspec case.
- **A-06-7. Unknown agent types.** RESOLVED by [A-06-7]: treated as blind. Pinned by TB06-D-222 to D-224.

## TB-07 secrets guard

- **A-07-1. Colon assignments.** RESOLVED by [A-07-1]: they count. Pinned by TB07-D-099 to D-102 and D-105.
- **A-07-2. A quoted variable reference assigned to a secret name.** RESOLVED by [A-07-2]: allowed when the value is exactly the reference. Pinned by TB07-D-103 to D-106.
- **A-07-3. Which "value" the placeholder rule inspects.** RESOLVED by [A-07-3]: the whitespace- or quote-delimited token. Pinned by TB07-D-107 to D-110. D-065 stays retired.
- **A-07-4. Case of placeholder words.** RESOLVED by [A-07-4]: case-insensitive. Pinned by TB07-D-111 to D-115.
- **A-07-5. `AIza` length.** RESOLVED by [A-07-5]: 35 or more. Pinned by TB07-D-015, D-043, D-116 and D-117.

## TB-08 bash guard

- **A-08-1. Main session with a non-orchestrator `main_session_role`.** RESOLVED by [A-08-1]: it gets that role's treatment. Pinned by TB08-D-147 to D-149.
- **A-08-2. Bare `rm` and `mv` for implement.** RESOLVED by [A-08-2]: not restricted by this hook. Pinned by TB08-D-150 and D-151.
- **A-08-3. Case of SQL keywords.** RESOLVED by [A-08-3]: case-insensitive. Pinned by TB08-D-152 to D-156.
- **A-08-4. Nested shells.** RESOLVED by [A-08-4]: the `-c` string of `sh`, `bash` and `zsh` is parsed. Pinned by TB08-D-157 to D-161.
- **A-08-5. Scope of the `rm -rf` exemption.** RESOLVED by [A-08-5]: `node_modules` or `.venv` at any depth, or anything under `/tmp`. Pinned by TB08-D-120 to D-122 and D-162 to D-168. See U-3 for the `/tmp/..` form.
- **A-08-6. Force push by refspec, and git global options.** RESOLVED by [A-08-6]. Pinned by TB08-D-169 to D-175.
