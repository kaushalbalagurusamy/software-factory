# System-design load simulator

Open the **Load simulator** dashboard tab. It runs arithmetic in the browser;
it does not send requests to modeled services or create infrastructure.

Declare the repo's actual topology in `docs/load-model.json`. With no model the
tab displays an explicitly labelled illustrative web architecture. Do not present
that example as discovered repo structure. A small CLI can have a single node.

```json
{
  "title": "Checkout service",
  "entry": "api",
  "nodes": [
    {"id": "api", "label": "Checkout API", "capacity_rps": 1000,
     "source": "Assumption: 4 replicas at 250 req/s each; not measured"},
    {"id": "db", "label": "Orders DB", "capacity_rps": 200,
     "source": "Assumption; requires later measurement"}
  ],
  "edges": [{"from": "api", "to": "db", "factor": 0.5}]
}
```

Move the active-user slider, requests/user/second and burst controls. Each node
shows offered request rate, capacity and utilization. Every declared path shows
its demand. Red marks capacity reached/exceeded or a simulated outage; amber
marks 80% utilization or a downstream dependency affected by upstream overload.
The table identifies capacity assumptions. Outage checkboxes model zero capacity.
Edit capacities, cache-miss factors and topology in the expandable JSON editor.
Those browser edits are scenario state only; they do not modify the repo model.

Demand at entry = users × requests/user/second × burst. Each downstream visit
rate sums upstream visit rates × edge factors, including converging paths. A
cache miss rate of 10% is factor 0.1; three downstream calls is factor 3.
The user ceiling is the minimum node capacity / per-user node demand. A reached
capacity is a modeled constraint, not a measured failure. Edge rates are offered
demand, not achieved throughput after drops or backpressure.

Limits: directed acyclic graph, 40 nodes/120 paths; use bounded retry factors or
unroll loops. No autoscaling, queue accumulation, response-time prediction,
correctness guarantee or stochastic traffic model. Fixed RPS capacity hides
request-mix and infrastructure effects. Zero traffic has no meaningful user
ceiling. Unreachable services carry zero demand. Optional branches still affect
the reported all-path capacity ceiling; that does not mean every UX journey fails.

Use the graph during exploration/plan review and final HITL. The builder should
link services to its nesting-dolls architecture, document sources/uncertainty,
and update the model when implementation changes topology. Antigravity can
investigate the assumptions; it does not approve or edit them by default.
