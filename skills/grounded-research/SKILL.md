---
name: grounded-research
description: Use this skill whenever you (Claude Code) encounter a tool, library, API, framework, CLI, or technique that is unfamiliar, newer than your training data, version-specific, or that you're not fully confident about — version-like names ("v2", "0.9", "next"), unfamiliar package names, or any claim about "current" or "latest" behavior are all triggers. Also use it whenever the user explicitly asks you to research, investigate, look into, or verify something. Do NOT just answer from memory or a single search result in these cases — this skill makes you check the installed/actual environment first, weigh source reliability, and run a real experiment to confirm claims before treating them as true. Especially important before writing code against an API you're unsure about, recommending a tool/version, or reporting a "fact" about software behavior back to the user.
---

# Grounded Research

## Why this exists

Claude's training data goes stale, and web sources vary wildly in reliability — docs get out of date, blog posts describe behavior that changed in the next release, and confident-sounding answers on forums are often wrong. The fix isn't "search the web and summarize the top result." It's: check what's actually true in this environment first, triage sources by how much to trust them, and when a claim really matters, write a small test that proves or disproves it instead of taking anyone's word for it — including your own memory.

Treat every external claim (including your own prior belief) as a hypothesis until something concrete confirms it: your own experiment, official documentation, or the actual installed code.

## The workflow

### Step 1 — Check ground truth you already have access to, before searching

You often have direct access to the actual answer sitting right there. Before searching the web:

- Is the tool/package already installed? Run it: `--help`, `--version`, `man <tool>`.
- Is the source available? `pip show`, `npm ls`, or find the package on disk and read the actual source, docstrings, or type definitions — these are ground truth for the exact version in use, more reliable than any doc page.
- Check CHANGELOGs, release notes, or `git log` in a cloned repo if available.
- Look for a local README or docs bundled with the package.

This step alone resolves a large fraction of "is this still true" questions without needing the open web at all, and it's specific to the exact version installed rather than whatever version a blog post happened to be describing.

### Step 2 — Search, but triage sources by reliability

When you do need the web, not all sources deserve equal trust. Roughly, from most to least reliable:

1. **Primary source**: official docs, the project's own repo (README, source, tests), official release notes/changelog
2. **Maintainer statements**: issues/PRs from maintainers, official blog posts, official migration guides
3. **Reputable technical writeups**: well-known engineering blogs, conference talks, publications with editorial standards
4. **Community knowledge**: Stack Overflow answers, wikis, forum threads — useful for surfacing *what to check*, but treat specific claims as unverified
5. **Unattributed or aggregator content**: SEO content farms, AI-generated summaries, outdated cached pages — these should raise your skepticism, not lower it just because they're easy to find

A recent date doesn't outrank a primary source, and a primary source that's clearly stale (e.g. docs for an old major version) doesn't outrank a maintainer's current statement. When sources disagree, that disagreement itself is a signal to move to Step 3 rather than picking whichever source you saw first.

### Step 3 — Verify with a real experiment before relying on a claim

This is the step that's easy to skip and shouldn't be. If a claim matters for what you're about to build or tell the user (a function signature, a default value, whether a flag exists, how an API responds, a performance claim, a "this doesn't work" claim), don't just report what a source said — check it:

- Write the smallest possible script/snippet that would prove or disprove the claim.
- Run it against the real, installed version in this environment.
- Compare actual output to the claimed behavior.
- If it's destructive, costly, or has side effects (deletes data, calls a paid API, modifies system state), isolate it — use a temp directory, a dry-run flag, a mock, or a sandboxed/throwaway environment — rather than skipping verification altogether.
- Clean up temporary test artifacts once you're done, unless the user wants them kept.

If you can't run a direct experiment (no local access to the tool, needs credentials you don't have, etc.), say so explicitly rather than silently falling back to an unverified claim — report the claim as unverified and name what it would take to confirm it.

A source saying something is true is evidence. Your own reproduction of the behavior is confirmation. Keep those two things distinct in your own reasoning and in what you tell the user.

### Step 4 — Report findings with honest confidence levels

When you summarize back to the user (or write code based on what you found), be explicit about how you know what you know. Don't flatten "I confirmed this by running it" and "a five-year-old forum post claims this" into the same confident tone. Use plain language, e.g.:

- "Confirmed — I ran `<command>` and got `<actual output>`."
- "Per the official docs (and consistent with the source code) — not independently re-run, but from a primary source."
- "Unverified — only source is a forum post from 2021; I'd want to test this before relying on it."

### Step 5 — Save findings for reuse

Write a short markdown note to `research-notes/<topic-slug>.md` in the project (create the directory if it doesn't exist) so future work — yours or a teammate's — doesn't repeat the investigation from scratch. Use this structure:

```markdown
# <Topic>

**Date**: <ISO date>
**Environment**: <version(s) checked, e.g. "package X v2.3.1, Python 3.12">

## Finding
<the actual answer, stated plainly>

## Confidence
<Confirmed by experiment / Primary source / Unverified — and why>

## Evidence
- <command run + actual output, or>
- <source + what it says, or>
- <both, if cross-checked>

## Notes
<caveats, version-specificity, anything that might go stale>
```

Keep it short — a few sources and one clear finding is more useful later than a sprawling research dump. If a note for this topic already exists, check whether it's stale (version mismatch, old date) before trusting it as-is; update it rather than leaving two conflicting notes.

## Judgment calls

- **Not everything needs a full experiment.** A quick `--version` check or reading one docstring is often enough to settle a trivial question. Scale the rigor of verification to how much the claim matters — save the deeper experiment-and-cross-check treatment for things that will actually affect what gets built or shipped.
- **Don't let this become research theater.** The goal is a correct, well-grounded answer delivered efficiently — not maximum process for its own sake. If Step 1 already gives you a confident, verifiable answer, you don't need Steps 2–3.
- **Flag genuine uncertainty rather than resolving it artificially.** If after real effort you still can't verify a claim, tell the user that plainly instead of presenting your best guess with unearned confidence.
