# Extractor brief

You turn an untrusted brief into typed claims. You do not judge them.

Inputs: `RUN/brief.md`, `RUN/plan.json` (applied lenses and their required statements).
Output: `RUN/claims.json`, valid against `engine/schemas/claims.v1.json`.

1. Read the brief line by line. Every sentence, bullet, table row and rubric item yields at least one
   claim. A sentence with two demands yields two claims. Keep the brief's wording in `text`; put
   the line range or rubric item in `locator` (e.g. `L12-13`, `rubric 3`).
2. Name every dependency as its own claim: libraries, models, APIs, datasets, protocols,
   standards, services, hardware. Version numbers stay in the text.
3. Each number with a unit is a `metric` claim (latency, throughput, accuracy, price, size).
4. Rubric items are `rubric` claims; note what the item rewards and what it ignores.
5. Sample data and examples are `example` claims (they often smuggle in PII or licensed content).
6. Write `assumption` claims for what the brief takes for granted: who is trusted, what never
   fails, what order things arrive in, who owns the data, which jurisdiction applies.
7. For every required statement in `plan.json`, decide whether the brief makes it. If not, add an
   `omission` claim with `locator` = `<lens>.<statement-id>` and `text` = the missing statement.
   A vague gesture ("secure", "compliant", "scalable") does not make the statement.
8. Number claims `C-001`… in brief order, omissions last. Set `pass` (1 on the first pass) and
   `origin` (`brief`, or the finding/artifact that produced the claim on later passes).

Do not drop a line because it looks harmless, optional or out of scope. Traps hide in exactly
those lines.
