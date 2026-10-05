# Seed schema

A seed is one line of research, written so a subagent can run it with no other context. `seeds.yaml` holds the cap and the list.

```yaml
round_cap: 3            # research rounds allowed before the human sees the gap reports
seeds:
  - id: S1
    question: "Which storage paradigms can hold vectors and relational integrity together at this scale and latency?"
    protects: [T1]      # terminal requirement ids this seed serves
    feeds: "storage decision (one-way door)"
    route: deep-research   # deep-research | grounded-research | brownfield-explorer | experiment-designer
    door: one-way          # one-way | two-way
    priority: 1            # 1 is first
    constraints:           # propagated verbatim to the researcher
      time: "as of 2026"
      scale: "100,000+ articles, under 50 ms per query"
      other: "must keep foreign-key integrity to organization models"
    sources: ["vendor documentation", "independent benchmarks", "engineering write-ups"]
    stop_when: "two independent sources agree, or a reproducible test settles it"
    budget: {scouts: 1, time_box_minutes: 30}
    depends_on: []
    round: 1
    origin: decomposition   # decomposition | gap-report
```

Rules:

- `question` is open ("Which ...", "How ...", "What limits ..."), never a request to confirm a chosen solution.
- `protects` is never empty. A seed that protects no terminal requirement has no reason to run.
- `constraints` carries every bound from the original requirement (time, region, scale, compliance). Researchers drift without them.
- `stop_when` names an observable condition, not a feeling of having found enough.
- `depends_on` is set for every `experiment-designer` seed, listing the research seeds whose avenues it needs.

## Gap-report extension

When every avenue fails a target, the experiment referee writes one seed per binding gap, with `origin: gap-report`, `round` increased by one, and a `gap` block. All numbers in this example are illustrative.

```yaml
  - id: S7
    question: "Which approaches reach p95 under 50 ms on 100k documents when HNSW index build memory exceeds the 4 GB limit?"
    protects: [T1]
    feeds: "storage decision (one-way door), round 2"
    route: deep-research
    door: one-way
    priority: 1
    constraints: {scale: "100,000+ articles, under 50 ms per query", other: "4 GB memory limit; already tried: pgvector HNSW, Elasticsearch dense_vector"}
    sources: ["vendor documentation", "independent benchmarks"]
    stop_when: "at least one avenue not yet tried has published numbers within the limit, or none exists"
    budget: {scouts: 2, time_box_minutes: 30}
    depends_on: []
    round: 2
    origin: gap-report
    gap:
      avenue: "pgvector HNSW"
      target: "p95 under 50 ms"
      measured: "p95 71 ms (range 66 to 78 over 3 repeats)"
      binding_constraint: "index build memory"
```

The question names the binding constraint and lists what was already tried, so the next round searches somewhere new instead of rediscovering the same avenues.

## Worked example, adapted from the ADR example in sf-adr-debate

Terminal requirement T1: semantic search over 100,000+ technical articles, under 50 ms per query, with relational integrity to the organization models.

| Seed | Question | Route | Door |
|---|---|---|---|
| S1 | Which storage paradigms can hold vectors and relational integrity together at this scale and latency? | `deep-research` | one-way, priority 1 |
| S2 | What are the build-memory and recall limits of HNSW indexing in pgvector at 100k documents? | `grounded-research` | feeds S1 |
| S3 | How are organization models and articles joined in the current schema? | `brownfield-explorer` | constraint |
| S4 | Does the embedding dimension change recall on this corpus? | `experiment-designer`, `depends_on: [S1]` | one-way |

S2 names a specific tool because it is a single verifiable claim, which `grounded-research` handles. S1 stays open because it is a survey.
