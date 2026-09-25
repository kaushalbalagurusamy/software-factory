# Skill trigger checks

Query sets and the checker used on 2026-09-24 to test whether each skill fires on the prompts it should and stays quiet on near misses.

- `trigger_check.py <set.json> <skill-name>` runs `claude -p` (2 runs per query) and counts a trigger when the first tool call is `Skill(<name>)` or a read of its SKILL.md. It tests the **installed** skill. It unsets `ANTHROPIC_API_KEY` for the child process so `claude -p` uses the login (an API key that is not tied to a workspace makes it fail).
- Why not skill-creator's `run_eval.py`: it counts only its own temporary copy of the skill, so an installed skill of the same name is never counted and every positive reads as a miss.
- The `*-smoke.json` sets are 6 queries each (4 should trigger, 2 near misses): they show no regression, not high accuracy. `eval-designer.json` is the earlier 28-query set (12 positives); recall there was about 60% before and after the description change.
