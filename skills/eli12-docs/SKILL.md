---
name: eli12-docs
description: >-
  Use whenever code is added or changed and the plain-English documentation for it must be written,
  refreshed or checked: "document this module", "write the docs so a non-programmer can follow",
  "ELI12", "explain it like I'm 12", "what does X take and give back, who uses it", "are the docs
  stale", and at sf stage 10 (docs and dashboard) or in lsf before declaring a change done. Creates
  one page per Python module under docs/eli12/ in a fixed format (what it does, what goes in, what
  comes out, who uses it, what it uses), computes the who-uses-who lines from the code so nobody
  guesses them, and fails a check when an entry is missing, stale, too long or full of jargon. Not
  for architecture essays, API reference generation or README writing.
---

# ELI12 docs

Docs written for the author cannot be read by the next person. The owner's rule: for every object
or function, say in plain words "X expects ABC and gives back DEF, Y uses it, it uses Z". This
skill makes that format fixed and lets a script check it.

The tool is `skills/eli12-docs/scripts/eli12.py` (standard library only, Python 3.9+, no network,
no model calls). It never writes meanings for you: it computes the facts that must not be guessed
(signature fingerprint, who calls it, what it calls) and leaves `TODO` for the words only you can
write.

## The format

One file per Python module: `docs/eli12/<dotted.module.path>.md` (dots, not slashes; a package
`__init__` uses the package path). Line one is `# <path of the .py file>`. The next paragraph is
one sentence saying what the file is for. Then one section per public class or function (names not
starting with `_`; methods as `Class.method`):

```
## parse_price
<!-- sig:3fa9c2d1 -->

**What it does:** Turns a price written as text, like "$4.50", into a number of cents.

**Expects:**
- text (str): the price as a person typed it, for example "$4.50"
- currency (str): the money sign to strip, for example "$"

**Gives back:** int: the price in cents, for example 450

**Used by:**
- shop.cart.add_item (shop/cart.py:41)

**Depends on:**
- shop.money.strip_sign (shop/money.py:12)

**Watch out:** Gives back 0 for an empty string instead of failing.
```

Rules the check enforces: the labelled lines come in exactly this order (`Watch out` is optional
and last); `What it does` is one sentence of at most 25 words; every parameter reads
`name (type): meaning` or the line says `nothing`; `Gives back` is `type: meaning` or `nothing`; no
line is over 160 characters; no `TODO` is left; the `sig` comment matches the code; `Used by` and
`Depends on` match what the code says. Calls the tool cannot pin to one project symbol are listed
with a `(maybe)` suffix; keep them, they are honest.

## Writing for a 12-year-old

- Short words. Say "looks up" not "resolves", "list" not "collection", "stops with an error" not
  "raises".
- One idea per sentence. Start with what it does for the reader, not how it works inside.
- Give one real example value for any parameter that is not obvious ("a user id, like `u_42`").
- Say what happens when it goes wrong in `Watch out`, in one line.
- A technical word that cannot be avoided goes in `docs/eli12/GLOSSARY.md` with a plain meaning
  (start from `assets/GLOSSARY.template.md`). `assets/jargon.txt` is the default list of words that
  need a glossary entry; copy it to `docs/eli12/jargon.txt` to change the list for a project.
- Describe what the code does today, taken from the code and its tests. Never guess.

## Steps

1. Scaffold: `python3 skills/eli12-docs/scripts/eli12.py scaffold --root . path/to/module.py ...`.
   It creates or updates the page. On an existing page it only refreshes `sig`, `Used by` and
   `Depends on` and adds missing sections; your sentences are never overwritten.
2. Fill every `TODO` from the code and its tests, in the words above. Check each `(maybe)` line by
   reading the code and keep or remove it only by changing the code, not the doc.
3. Check: `python3 skills/eli12-docs/scripts/eli12.py check --root .` (exit 0 clean, 1 findings, 2
   usage error). Useful flags: `--paths P...`, `--changed GITREF` (only modules changed since the
   ref plus modules whose lists mention them), `--json`, `--include DIRNAME` (to scan a folder that
   is skipped by default: `.venv`, `node_modules`, `.git`, `evals`). Each finding is
   `path:line: code: message`. Codes: `missing-entry`, `orphan-entry`, `stale-signature`,
   `stale-dependencies`, `todo`, `format`, `too-long`, `bad-param`, `jargon`, `unparseable`.
4. Index: `eli12.py index --root .` writes `docs/eli12/INDEX.md` and `docs/eli12/index.json`
   (module path to doc path, for the explorer and dashboards to link each file to its page).
   Scaffold also refreshes `index.json`.

A stale-signature or stale-dependencies finding means the code moved on: reread the code, fix the
sentences if needed, then run scaffold to refresh the computed parts.

## Where it plugs in

- sf stage 10 (docs and dashboard): `doc-sync` runs `eli12.py check` and treats every finding as a
  stale document to fix before the slice closes.
- implementation-review: approval needs `eli12.py check` clean for the changed modules
  (`--changed <base ref>`).
- lsf: run scaffold and check for modules touched by the change before reporting it done; the
  final report lists any finding left, never hides one.
