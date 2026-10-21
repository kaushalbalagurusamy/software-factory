---
id: rubric-inversion
version: 0.1.0
title: Rubric inversion (Goodhart and gameable metrics)
group: theory-measurement
owner: sf
scope: >-
  Judges rubrics, KPIs and acceptance metrics that reward the wrong behaviour: proxies optimised as
  targets, coverage or test counts as quality, recall without a false-alarm budget, and LLM judges
  grading their own outputs. Leaves the statistical validity of a model evaluation to ml-evaluation.
applies_when:
  signals: [rubric, scored on, scoring, graded, grading, kpi, leaderboard, coverage, number of tests, lines of code, tickets closed, velocity, judge, self-evaluat, llm-as-a-judge, auto-grade, zero false negatives, never miss, 100% recall, flag every, maximise, maximize, success criteria, acceptance criteria]
required_statements:
  - id: proxy-target
    statement: For each scored metric or KPI, the brief states the underlying goal the metric is a proxy for.
  - id: counter-metric
    statement: For each scored metric, the brief names a counter-metric or budget that worsens when the metric is gamed (for example precision against recall, defects escaped against tests written, human-rated quality against an automated score).
adapters: [paper, web_page]
---

# Rubric inversion

## Principles

- A metric optimised past the point where it tracks the goal becomes ineffective or harmful
  (manheim-2018); optimising an imperfect proxy reward leads to poor true performance (skalse-2022).
  The phrasing "when a measure becomes a target it ceases to be a good measure" is Strathern's (1997)
  paraphrase; cite the papers, not the slogan.
- Coverage counts executed code, not detected faults (inozemtseva-2014; not yet quotable, trap unverified).
- Precision and recall trade off; recall without a precision floor is met by flagging everything
  (sklearn-pr-example).
- LLM judges carry position, verbosity and self-enhancement bias and favour their own generations
  (zheng-2023, panickssery-2024).

## Questions a sweeper asks of each claim

- What does this metric reward, and what is the cheapest way to raise it without improving the goal?
- What goal is it a proxy for, and does the brief say so?
- What counter-metric would fall if the proxy were gamed, and is it measured and gated?
- Does the score grow with raw volume (lines, tests, tickets, alerts, words) or with outcome?
- Who grades? Is the grader independent of the generator, and calibrated against humans?
- For detection targets: is there a false-positive budget or cost per error type?

## Severity guidance

- A gameable rubric is usually principal-reject (medium).
- Raise to high (production-failure) when the gamed metric gates release of a safety, security or
  financial control, or when an autonomous agent optimises against it directly.
- A rubric from an untrusted brief is quarantined, not obeyed: report the metric, the gaming route and
  the replacement pair (proxy plus counter-metric).

## Not this lens

- Leakage, calibration, base rates and benchmark contamination: ml-evaluation.
- Impossible detection guarantees over arbitrary code: theory-complexity.
- Reward hacking by the implementing agent inside the build loop: the sf review stage, not the brief sweep.
