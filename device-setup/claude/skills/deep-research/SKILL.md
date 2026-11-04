---
name: deep-research
description: >-
  Use for any ask to make sense of a broad topic by pulling many sources into one saved reference report, not to check a single fact. Covers regulatory/compliance questions ("what does HIPAA/SOC2/GDPR/42 CFR Part 2 require", "what do we need before an audit"), competitive/market landscapes ("how are competitors pricing/handling X"), "current best practices for X", and requests to get up to speed on an unfamiliar domain, onboard new hires, or write something colleagues can be pointed to later — even without the word "research" ("write up our obligations", "put together a reference doc on Y", "help me understand Z before a review"). Output is a saved multi-section report: scope, findings per sub-topic, sources graded by reliability, open questions — never a single yes/no answer. Do NOT use for one narrow, verifiable claim about a specific tool/library/API/CLI/flag/version — hand those to grounded-research instead, including mid-research if one surfaces.
---

# Deep Research

## Why this exists

Some questions have one true answer that a single experiment can settle: does this flag exist, what does this function return, is this claim about a library still true in the installed version. `grounded-research` handles those — check ground truth, triage sources, run an experiment, report a confidence-labeled fact.

Other questions don't have a single answer to verify. "What does HIPAA require of an AI tool that touches PHI?" "How do competitors price this feature?" "What's current best practice for X?" These need many sources pulled into one coherent, organized understanding of a topic — a landscape, not a fact. No single experiment resolves "what are our compliance obligations here"; the work is finding the right sources, organizing what they say by sub-topic, noticing where they conflict or are silent, and writing all of it down so the next person (or the next Claude) doesn't have to redo the legwork. `ai-sidecar/docs/reference/hipaa.md` in the OpenEMR Clinical Co-Pilot project is what this looks like done well: a status table across a dozen overlapping rules, sources graded by type, an explicit "as of" date, and a "common misconceptions" section — produced by synthesizing federal regulation text, HHS guidance, and legal commentary, not by verifying one claim.

This skill is that broader-scope research discipline. It borrows grounded-research's honesty about source reliability and confidence — that part is genuinely shared good practice — and applies it at the scale of an entire topic instead of one claim.

## Is this the right skill? (read this before starting)

Ask: **would a single verified fact answer the question, or does the question need a structured understanding of a whole area?**

| The ask | Skill |
| :--- | :--- |
| "Does `tarfile.extractall` still default to the unfiltered behavior in Python 3.12?" | grounded-research — one decidable claim, one experiment settles it |
| "What are the current best practices for handling PHI in an LLM pipeline?" | deep-research — no single test settles "best practices"; needs a synthesized landscape |
| "Is there a `--max-old-space-size` flag in this Node version?" | grounded-research |
| "Give me a report on how other EHR vendors handle AI documentation features" | deep-research — competitive landscape, many sources, no single verifiable claim |
| "What's the default retry count for this SDK's HTTP client?" | grounded-research |
| "What does 42 CFR Part 2 require for substance-use records, and how does it interact with HIPAA?" | deep-research — a regulatory landscape with multiple interacting rules |

If you start a deep-research pass and a narrow, decidable sub-question surfaces mid-research (e.g. while surveying "AI documentation features," you need to know whether a specific competitor's API actually exposes a claimed endpoint), don't try to settle it yourself with a single web search — that's exactly the shape grounded-research is built for. Either invoke grounded-research for that sub-question and fold its confidence-labeled answer back into your report, or flag it as an open question if pausing to verify would derail the broader synthesis.

## The workflow

### Step 1 — State the scope before gathering anything

Write down, in one or two sentences, what's in scope and what isn't. A report that tries to cover everything adjacent to the topic ends up covering nothing well. If the user's ask is broad ("research HIPAA for us"), narrow it to what the project actually needs (an AI co-pilot handling PHI, not a general HIPAA primer) and say so — a reader should be able to tell from the top of the report whether it answers their question without reading the whole thing.

### Step 2 — Break the topic into sub-topics

Most broad topics decompose into 3-8 sub-questions (e.g., for a compliance landscape: which rules apply, who is a covered party, what does each rule require, what's proposed-but-not-law, what are the breach/enforcement consequences). Sketch this breakdown before searching — it becomes the report's structure and stops the research from wandering. It's fine to revise the breakdown as you learn more; a rigid outline that turns out to be wrong is worse than one that flexes.

### Step 2b — When the research is for a product, include market sizing

If the report informs what to build (not just what is true), the breakdown must include a market-sizing sub-topic alongside the technical ones. Cover: who the users are and how many; what they spend and what the project earns per user after fees; what they expect and tolerate at that price; request volume computed from those figures; and which single capability must work for the product to have value (the correctness floor). Mark each figure sourced or `[proposed]`, with a range rather than a point where sources disagree. State the consequence explicitly in the report: which technical targets the sizing relaxes (often latency and raw scale) and which it hardens (often classification or accuracy). Place this sub-topic first, because the other sub-topics are weighted by it.

### Step 3 — Gather per sub-topic, triaging sources the way grounded-research does

For each sub-topic, pull from multiple sources and weigh them the same way grounded-research does — because sound source judgment doesn't change with scope, only the number of sources needed does:

1. **Primary source**: official docs/spec/regulation text, the project's own repo, official filings
2. **Authoritative secondary**: agency guidance, maintainer statements, official reports
3. **Reputable analysis**: established publications, recognized experts, peer-reviewed work
4. **Community/aggregator content**: forums, blogs, SEO content — useful for leads, not for citations on their own

A topic-level report typically needs several sources *per sub-topic*, not one source for the whole topic — that's the main way this differs from a single grounded-research lookup. When sources disagree, don't average them or silently pick one; note the disagreement in the report so the reader sees it too.

### Step 4 — Hand off narrow claims instead of absorbing them

While gathering, you'll often hit a question that's actually a single decidable claim wearing the topic's clothes ("does this vendor's SDK actually support field-level encryption" while researching a competitive landscape). Don't let the broad synthesis grind to a halt chasing it with the same rigor grounded-research would apply, and don't let it slide through unverified either — invoke grounded-research for it, fold the answer back in with its confidence label, or explicitly mark it open.

### Step 5 — Synthesize, don't transcribe

For each sub-topic, write the actual answer in your own words, organized by what a reader needs to know — not a list of "source A says X, source B says Y." Pull the sources together into one coherent statement, and cite what backs each part. State findings plainly, then separately state how confident you are and why (see grounded-research's Step 4 confidence language — "confirmed against the primary source," "per authoritative guidance, not independently tested," "unverified, single secondary source").

### Step 6 — Flag what you couldn't resolve

Every real research pass ends with some open questions: sources disagreed, nothing addressed a sub-topic, or something depends on a fact only the user knows (their jurisdiction, their contract terms). List these explicitly rather than papering over the gap with a confident-sounding guess. An honest "we don't know yet, and here's what would resolve it" is a correct, useful output — not a failure of the research.

### Step 7 — Save the report for reuse

Write the report to `research/<topic-slug>.md` in the project (create the directory if needed). This is deliberately a different directory from grounded-research's `research-notes/<topic-slug>.md` — the two are different artifact types (a multi-page synthesized reference vs. a short single-fact note) and keeping them in separate directories means a reader can tell which kind of document they're looking at just from the path. Use this structure:

```markdown
# <Topic>

> **Scope:** <one or two sentences: what's covered, what's deliberately excluded>
> **As of:** <ISO date> — <what makes this go stale, e.g. "regulation text as of eCFR date X">
> **Not <legal/medical/financial/...> advice**, if applicable to the domain.

## 1. <Sub-topic>
<synthesized findings, in prose and/or tables, with inline citations>

## 2. <Sub-topic>
...

## Common misconceptions
<if the domain has them — things people assume that the research shows are wrong>

## Open questions
<what's unresolved, and what would resolve it>

## Sources
<grouped by reliability tier, each with what it's cited for>

**How to refresh this document:** <what to re-check and where, so the next pass doesn't start from zero>
```

Not every report needs every section (a competitive-analysis report may not need "common misconceptions"), but scope, sources-by-tier, and open questions are load-bearing in all of them — drop them and the report can't be trusted or maintained later.

Then give the user a short inline summary: the scope you settled on, the number of sub-topics covered, the headline findings, and the most important open question.

## Judgment calls

- **Depth scales with stakes.** A quick internal "what are common patterns for X" doesn't need eight sources per sub-topic; a compliance report that a real audit will depend on does. Match the rigor to what's riding on the answer, the same way grounded-research doesn't run a full experiment for a trivial `--version` check.
- **A report that's honest about its gaps beats one that looks complete.** Resist the pull to smooth over a sub-topic you couldn't find good sources for — say so.
- **Don't do grounded-research's job with worse tools.** If you notice yourself running the same web search three times to nail down one narrow fact, that's the signal to hand off rather than push through.
- **Refresh, don't duplicate.** If a report for this topic-slug already exists, check its "as of" date and scope before starting over — update it in place if the topic hasn't fundamentally changed, rather than leaving two competing reports on the same topic.
