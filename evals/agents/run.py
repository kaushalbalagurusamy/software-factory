"""Run the agent-layer evals and print the summary. Usage: python evals/agents/run.py [pytest args]."""
from __future__ import annotations

import collections
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]


def main(argv):
    subprocess.run([sys.executable, "-m", "pytest", str(HERE), "-q", "-p", "no:cacheprovider", "--rootdir", str(HERE), *argv],
                   cwd=REPO, env={**__import__("os").environ, "PYTHONPATH": str(REPO)})
    records = json.loads((HERE / "results" / "latest.json").read_text())
    by = lambda key: collections.defaultdict(collections.Counter)  # noqa: E731
    tiers, tbs, reqs = by(0), by(0), by(0)
    problems = []
    ids = collections.Counter(r["id"] for r in records)
    problems += [f"duplicate case id {i}" for i, n in ids.items() if n > 1]
    for r in records:
        tiers[r["tier"]][r["status"]] += 1
        tbs[r["tb"]][r["status"]] += 1
        for q in r["reqs"]:
            reqs[q][r["status"]] += 1
        if r["status"] == "invalid_skip":
            problems.append(f"{r['id']}: skipped without BLOCKED")
    print("\n== by tier"); [print(f"  {k}: {dict(v)}") for k, v in sorted(tiers.items(), key=str)]
    print("== by TB"); [print(f"  TB-{k}: {dict(v)}") for k, v in sorted(tbs.items(), key=str)]
    print("== by requirement"); [print(f"  {k}: {dict(v)}") for k, v in sorted(reqs.items())]
    golden_ids = {r["id"] for r in records if r["tier"] == "golden"}
    gfile = HERE / "GOLDEN.json"
    if gfile.exists():
        expected = set(json.loads(gfile.read_text()))
        if expected != golden_ids:
            problems.append(f"golden membership differs: missing {sorted(expected - golden_ids)}, extra {sorted(golden_ids - expected)}")
    else:
        problems.append("GOLDEN.json missing")
    g = [r for r in records if r["tier"] == "golden"]
    green = bool(g) and all(r["status"] == "passed" for r in g) and not problems
    print(f"\ngolden: {sum(r['status']=='passed' for r in g)}/{len(g)} passed, "
          f"{sum(r['status']=='blocked' for r in g)} blocked, {sum(r['status']=='failed' for r in g)} failed")
    for p in problems:
        print("PROBLEM:", p)
    print("GOLDEN VERDICT:", "GREEN" if green else "NOT GREEN")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
