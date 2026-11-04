---
name: progress-briefing
description: Use whenever the owner needs a major update on a long-running or autonomous piece of work, as a private three-tab Artifact page. Triggers - "progress update", "status", "where are we", "what's in flight", "brief me", "what's left", the end of an sf slice (stage 12), before a human gate or a deadline, after a long autonomous stretch, or whenever Claude has crossroads that need the owner's input. Tab 1 shows repo state, in flight, done and left against the requirements, each explained with a household analogy. Tab 2 tells the research and experiment story with real outcomes. Tab 3 is an open-question survey of the crossroads worth the owner's input, with answers stored so Claude can read them. Not for a one-line status reply or for repo documentation.
---

# Progress briefing

The owner follows long runs from a phone and cannot review every change. This skill turns "what is going on" into one private Artifact page with three tabs, rebuilt from primary sources each time. It layers on the Artifact tool's own rules: those win on page contract, theming, CDN limits and responsive layout, and `artifact-capabilities` is loaded for the survey tab.

## When to build or update one

- The owner asks for an update, in any wording.
- A slice finishes (sf stage 12) and anything in the three tabs changed materially.
- Before a human gate, a deadline, or going idle after a long run.
- Whenever a crossroads appears that the owner should decide (tab 3), do not wait for the next scheduled briefing.

Keep **one briefing artifact per project**. The first time, publish a new page and remember its URL in the project's memory or `.claude/` notes; every later briefing passes `url` to update it in place, so the link on the owner's phone stays the same. Mention in chat that the link is unchanged.

## Gather facts first, from primary sources

Never write a tab from memory or from the previous briefing. Pull, in this order:

1. Repo: `git status --short`, `git log --oneline` since the last briefing, current branch and HEAD hash, uncommitted file groups.
2. Requirements: the project's ledger (the build-loop profile names it). Count rows by status; list rows the work since the last briefing touched, with the artifact that satisfies each.
3. Tests and evals: the last runner's raw result, not the implementer's claim. Say which stage produced it and whether a re-run is pending.
4. In flight: running agents and background tasks (what each is doing, who started it, what it will report), scheduled wake-ups, pending human gates.
5. Research and experiments: the committed briefs, `experiments/*/RESULTS`, reviews and ADRs. Read the numbers from those files.
6. Open questions: the ledger's blocked rows, ADR "Human (gate)" candidates, decisions Claude made autonomously that the owner may want to overrule, and anything blocked on the owner.

Anything you could not verify is written as "not checked" or "could not verify" on the page. Put "as of <date time zone>, HEAD <hash>" at the top.

## Tab 1: Status (current state, in flight, done, left)

Order: a four-number strip, then in flight, then requirements (done, left), then repo state.

- **Strip:** requirements satisfied of total, items in flight, items waiting on the owner, commits since last briefing. Counts come from the ledger, not from estimates.
- **In flight:** one row per running task, with a status pill (running, waiting, blocked), what it is doing and what it will hand back.
- **Requirements, done and left:** group by what the owner cares about (not by ledger row id). Each group has a status pill, a one-line plain-English description, and a **household analogy** in its own labelled line. Keep the technical term beside it in small text so the owner learns the vocabulary. Rows that wait on the owner say so in the group.
- **Repo state:** branch, HEAD, commits since last time (hash and subject), uncommitted files grouped by purpose, test and eval results with who ran them.

Analogy rules: pick the analogy that is structurally right, not merely cute. A cache is a kitchen pantry (stock bought once, checked before you shop again); a failing-closed default is the oven's door lock; a one-way door is pouring concrete; an async worker pool is a kitchen with several cooks and one pass; a ledger is a shopping list you tick off. State where the analogy stops working when it matters (for example, "unlike a pantry, a wrong item here costs money"). One analogy per concept, never a decorative one, never an emoji.

## Tab 2: Research and experiments (the development story)

A cumulative, chronological record. Append new entries; never rewrite an old outcome except to mark it superseded by a later one. Each entry is a card with:

- **Question** the work set out to answer.
- **What was done** (method, data size, what it cost).
- **Real outcome**: the actual numbers with their denominators, intervals where the source gave them, and the **limits** (what the number does not show). Negative and surprising results get the same space as good ones.
- **What it changed**: the decision, ADR, or spec it fed, linked by file path or commit.
- **Source**: file path or commit hash.

No invented figures, no rounding that flatters, no "approximately" where the source has an exact value. Tab 2 uses plain engineering language; analogies are optional and brief. Include a short "could not verify" list for the whole story at the bottom.

## Tab 3: Open questions (survey)

Only crossroads that change what happens next and that the owner is the right person to decide: a trade-off with real consequences, something blocked on them, a one-way door, a call that overrules something Claude decided autonomously. Never "should I proceed", never a question the code or docs already answer.

Each question card has: the question in one sentence; **why it matters now** (what it blocks, by when); two to four options, each with its consequence in plain language and, where it helps, an analogy; the **recommended** option marked, with the reason; the **default Claude will use if no answer comes** (recorded as AI autonomous); and an "Other" free-text box. Group blocked-on-you questions first.

Answers are stored with the `db` capability (declare `{db: {}, user: {}}`), one document per question id in the collection `answers`: `{choice, note, at}`. The page embeds the questions themselves (regenerated each briefing) and reads answers live; answered questions move to a "Decided" list that stays visible. Claude reads the answers with the `ArtifactData` tool (`list` on `answers`) at the start of the next turn after a briefing, treats each as a **Human (gate)** decision, records it in the relevant ADR's decision table (and the project's memory if it is standing guidance), and then marks the question decided in the next version of the page. Do not put secrets in options or notes.

## Building the page

1. Start from `references/template.html` (same folder as this file). It already has the tab strip, the token system for light and dark, the survey wiring and a sample card of each kind; replace the sample content, keep the structure and the script.
2. Write the file to the scratchpad, publish with the Artifact tool, `capabilities: {db: {}, user: {}}`. First publish uses a stable two-to-four word title (for example "Equinox Briefing") and the icon `dashboard`; later publishes pass `url` and omit `icon`.
3. After the first publish only, do the capability check from `artifact-capabilities`: one `ArtifactData` `list` of `answers` (an empty result is fine). Say in one line what you checked.
4. In chat, give the link and at most five lines: the headline, what is in flight, how many questions need the owner. Do not repeat the page.

## Rules

- Private by default; never change sharing. Never embed keys, tokens, hostnames of private systems or personal data. Show env var names only, never values.
- The owner reads this, not a partner: the repo-docs voice rules (neutral team voice, no "you") do not apply to the page. Plain, direct, second person is fine. The page is not a repo document and is not committed.
- Do not pad. A slice that changed little gets a short update, and unchanged cards carry forward unchanged with their "as of" date.
- Report faithfully: a failing test, a skipped stage, an unrun check or a blocked item appears on the page as it is.
- Keep every claim traceable to a file, commit or tool result named on the page.
