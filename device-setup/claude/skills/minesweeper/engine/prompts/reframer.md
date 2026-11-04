# Reframer brief

For each confirmed or plausible finding, write the fields that turn a trap into a better problem.

1. **severity**: answer `config/policy.yaml severity_questions` in order. Each answer is
   `{"id", "q", "a": true|false, "why"}`. Stop at the first yes; the tier is that question's tier.
   If all are no, the tier is low. The trap's default tier is only a hint; context decides (data
   type, jurisdiction, scale, who is harmed). `tools/validate.py` recomputes the tier.
2. **underlying_problem**: the real problem the brief should have stated, in one or two sentences
   (e.g. "reduce inference cost without training on provider outputs" rather than "log completions
   to fine-tune").
3. **disposition**: `comply-safely`, `reframe`, `decline` or `ask-owner`. Use ask-owner when the
   answer depends on jurisdiction, contract terms or a business choice, and write `owner_question`
   as a question with options.
4. **spec_section**: where the technical spec must answer it: trust-consensus,
   crypto-agent-security, capacity-physics, verification-calibration, legal-terms, product-scope.
5. If a brief line or rubric item will not be followed as written, add a quarantine entry:
   locator, the text, finding ids, reason, and the replacement statement (an invariant, SLO,
   guardrail or non-goal).

Keep the brief's legitimate business objective. The point is to serve it safely, not to refuse it.
Never close a finding as out of scope on a `never_out_of_scope` topic.
