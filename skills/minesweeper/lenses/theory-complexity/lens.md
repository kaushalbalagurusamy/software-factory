---
id: theory-complexity
version: 0.1.0
title: Theory and complexity limits
group: theory-measurement
owner: sf
scope: >-
  Judges brief claims that theory rules out: exact optima for NP-hard combinatorial problems at scale
  and in real time, static guarantees about arbitrary user programs (halting, Rice's theorem), perfect
  detection of behavioural properties, and backtracking regex on untrusted input. Leaves measured
  throughput and latency budgets to performance, and metric design to ml-evaluation and rubric-inversion.
applies_when:
  signals: [optimal, optimum, optimis, optimiz, schedul, rostering, timetabl, routing, vehicle rout, bin pack, knapsack, shortest tour, travelling salesman, traveling salesman, custom rule, user-defined rule, rules engine, custom script, scripting, workflow builder, terminat, infinite loop, detect all, malicious, malware, virus, regex, regular expression, static analysis, provably]
required_statements:
  - id: optimality-target
    statement: For any optimisation feature, the brief states whether it needs the exact optimum or an approximation, and if an approximation, the acceptable optimality gap and the time budget per solve.
  - id: instance-size
    statement: The brief states the maximum problem size the optimiser or checker must handle (entities, nodes, constraints) together with the latency it must meet at that size.
  - id: rule-execution-bounds
    statement: Where users supply rules, scripts or patterns, the brief states the language's expressiveness and the run-time limits (steps or time, memory, recursion or trigger depth) that bound execution.
adapters: [paper, web_page]
---

# Theory and complexity limits

## Principles

- Covering, packing, routing, assignment and sequencing problems stand or fall together: either all
  have a polynomial-bounded algorithm or none does (karp-1972). A brief that wants the exact optimum,
  a hard latency bound and unbounded size wants something nobody knows how to deliver.
- Halting is undecidable (turing-1936) and so is every non-trivial semantic property of programs in a
  Turing-complete language (rice-1953). Static checks over such languages are either incomplete or
  unsound; run-time budgets are the enforceable guarantee. (Sources not yet quotable; trap unverified.)
- Precise detection of malicious behaviour is undecidable; only statistical or restricted detection
  exists (cohen-1987). Detection claims must be measured rates with containment behind them.
- Backtracking regex features carry potential exponential runtime; untrusted patterns or inputs need a
  linear-time engine (re2-readme).

## Questions a sweeper asks of each claim

- Does the brief say "optimal", "best", "minimum" or "guaranteed" about a scheduling, routing, packing,
  assignment or allocation problem? Is a reduction from a classic NP-hard problem visible?
- Is there a latency bound on that solve, and what is the largest instance it must handle?
- Would a bounded-time solver with a reported gap satisfy the real business goal?
- Can users submit logic (scripts, rules, triggers, regexes)? Is the language Turing-complete? What
  does the brief promise about it before it runs?
- Does any requirement say "all", "every", "never" or "100%" about a behavioural property of
  arbitrary code or content?
- Where untrusted text meets a regex, which engine, and is there a timeout and length cap?

## Severity guidance

- Exact optimum with a synchronous latency bound at production scale: production-failure (high).
- Static termination or safety promises over a Turing-complete user language: production-failure, and
  severe-security when the promise is the only isolation between tenants (high).
- Perfect detection promised as a security control: severe-security (high); as a marketing claim only,
  principal-reject (medium).
- Backtracking regex on untrusted input on a shared worker: production-failure (high).
- Lower the tier when instance sizes are small and fixed (an exact solver may be fine) or the
  optimisation runs offline with no deadline; say so with the measured size.

## Not this lens

- Measured throughput, memory and tail-latency budgets: performance.
- Agent tool-use sandboxing and prompt injection: agent-security.
- Detection-rate metrics and thresholds as rubric items: rubric-inversion and ml-evaluation.
- Consensus impossibility results (FLP, CAP, Byzantine bounds): distributed-systems.
