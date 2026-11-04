# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 4 traps (proxy-metric-as-target, coverage-or-test-count-target, zero-misses-without-false-alarm-budget, llm-judge-self-grading), 2 required statements, planted/clean pairs per trap and 2 omission cases with clean twins.
- Verified: proxy-metric-as-target (Manheim and Garrabrant 2018; Skalse et al. 2022), zero-misses-without-false-alarm-budget (scikit-learn Precision-Recall example), llm-judge-self-grading (Zheng et al. 2023; Panickssery et al. 2024).
- Unverified: coverage-or-test-count-target; Inozemtseva and Holmes 2014 returns 403 from ACM with no HTML abstract.
- Corrected report attribution: "when a measure becomes a target" is Strathern's 1997 paraphrase, not Goodhart's wording.
