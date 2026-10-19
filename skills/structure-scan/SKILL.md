---
name: structure-scan
description: >-
  Structural exploration of a Python repository with the stdlib ast module: symbols with stable ids and source
  spans, call edges labelled resolved / syntactic / unresolved (with reasons), mutable state, a bounded scope
  around entry symbols, a structural diff by normalised-AST hash with affected callers, and a Mermaid Nesting
  Dolls model generated from the result. Use before changing unfamiliar Python code, when scoping a change, when
  a /sf slice needs the affected callers and touched state, to give the change-impact gate its structural half,
  or to refresh an architecture explorer from source. Python only; not a complete call graph.
---

# structure-scan

`python -m factory.structure` (run from the repository that contains the `factory/` package; needs only Python 3.10+).
It reads source with `ast`. It does not import or execute the target, does no type inference, and does not use
an LSP or tree-sitter. Other languages are out of scope: route them to other checks and say so.

## Commands

```bash
python -m factory.structure scan  REPO [--paths FILE...] [--exclude GLOB]... [--strict] [--summary]
python -m factory.structure scope REPO --entry pkg.mod:Class.method [--entry ...] [--depth 2] [--include-syntactic]
python -m factory.structure model REPO -o model.json [--entry ... --depth N] [--name TITLE] [--max-nodes 14]
python -m factory.structure diff  BASE HEAD [--repo GIT_REPO] [--depth 2] [--strict]
```

- Symbol ids are `<module.path>:<Qualname>` (module symbol: `pkg.mod:<module>`; nested functions
  `f.<locals>.g`; instance/class attributes are state ids `pkg.mod:Class#attr`). They do not contain line numbers.
- `diff` takes two directories or `git:<rev>` for either side (needs `--repo`); it reads with `git ls-tree` and
  `git show` and never checks anything out.
- Exit codes: 0 ok; 2 usage error (bad flag, unknown entry symbol, missing path or revision); 3 parse failure
  (any file with `--strict`; always for a file named in `scan --paths`).
- Use `--exclude 'tests/fixtures/*'` for files that are intentionally unparsable; excluding is an explicit choice, never a default.

## Reading the output

Every edge has a `kind`:

| kind | meaning | what you may conclude |
|---|---|---|
| `resolved` | name found through imports, local scope or class members to a symbol in the repo | the call reaches that symbol, subject to subclass overrides for `self.m()` |
| `syntactic` | matched by text only, such as a method on a parameter of unknown type | nothing; `candidates` are repo methods with that name, not claims |
| `unresolved` | dynamic or ambiguous; `reason_code` and `reason` say why | the callee is unknown. Reasons: `dynamic_attribute`, `dynamic_code`, `dynamic_import`, `call_through_variable`, `call_of_call`, `subscript_call`, `lambda_call`, `star_import`, `conditional_import`, `multiple_bindings`, `decorator_wrapped`, `unparsed_module`, `module_attr_missing` |

Calls to builtins and to modules outside the scanned tree are counted in `limits.external_calls_not_recorded`
and are not edges. A call to a function whose decorator may wrap it (anything outside a short allowlist such as
`staticmethod`, `property`, `lru_cache`) is `unresolved` with the function as a candidate.

Always read `limits` before relying on a result:

- `parse_failures`: files that could not be parsed. Their symbols are absent; in `diff` they are listed under
  `unknown_due_to_parse_failure` and the diff `status` is `incomplete`. An incomplete diff must not be treated as "no impact".
- `unresolved_edges`, `syntactic_edges`, `unresolved_in_scope`, `syntactic_in_scope`: how much the walk could not follow.
- `complete_call_graph` is always `false`. Callers that reach a symbol only through dynamic dispatch cannot be found.
- `scope.not_followed` lists every edge seen but not followed, with the reason; `depth_truncated` lists symbols
  whose edges were not expanded because of the depth bound.

## In an /sf slice

1. Exploration stage: `scope` around the entry symbols named by the slice. Put `callers`, `state_touched` and the
   limits into the slice notes. Unresolved edges in scope become explicit test or review obligations.
2. After implementation: `diff base head --strict`. `changed`, `added`, `removed` and `affected_callers` (labelled
   by edge kind) are the structural half of the change-impact gate. The per-symbol `hashes` are cache keys for a
   later verification step, but a cache must also key on dependency and contract hashes, tool versions and assumptions.
   Hashes ignore formatting and comments; docstring and constant changes do count.
3. Refresh the architecture explorer:
   ```bash
   python -m factory.structure model REPO -o structure-model.json --entry pkg.mod:f --depth 2
   python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py check structure-model.json --repo REPO
   python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py build structure-model.json -o structure.html --repo REPO
   ```
   The model nests system, package, module, class or function, method. Every node carries `files` with a real line
   range and a verified `contains` quote. Solid arrows are resolved calls, dashed arrows are syntactic name
   matches (drawn only with 5 or fewer candidates), and each diagram has an `Unresolved / dynamic calls` node
   listing reasons. `coverage` is not set: assign it by hand where you have evidence. Check, then build, then open
   the Check button in the browser as the dolls skill describes.

## Limits to state when you report

Python only; ast only; module names come from paths relative to the scanned root (no `src/` layout or `sys.path`
logic, so imports that rely on them look external); no type inference, so `obj.method()` stays syntactic; reads
of module state are recorded, but reads and writes through aliases of aliases are not; container mutation is
detected by method names (`append`, `update`, ...) and subscript stores, which is a heuristic.
