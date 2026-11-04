---
id: provider-terms
version: 0.1.0
title: Model and API provider terms
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about how a third-party model or API is used (outputs, accounts, limits, resale,
  regions, data tiers) against that provider's own current terms, usage policy and service-specific terms.
  Licences of downloadable code and weights belong to licensing; personal-data law belongs to
  privacy-regulated-data.
applies_when:
  signals: [llm, gpt, claude, gemini, openai, anthropic, foundation model, frontier model, model api, api key, completion, completions, fine-tune, fine-tuning, distil, distill, synthetic data, teacher model, student model, rate limit, free tier, free quota, inference cost, reseller, white-label, third-party api, terms of service]
required_statements:
  - id: provider-and-agreement
    statement: The brief names each external model or API provider and the agreement or tier it will be used under (consumer, free, paid API, enterprise).
    never_out_of_scope: licences-terms
  - id: output-use
    statement: The brief states what happens to provider outputs beyond showing them to the user (stored, used for training or evaluation, redistributed).
    never_out_of_scope: licences-terms
  - id: data-sent
    statement: The brief states what classes of data are sent to each provider.
adapters: [web_page]
---

# Provider terms

## Principles

- No distillation without permission. Provider terms bar using services or outputs to train competing
  models without authorisation (`anthropic-commercial` D.4, `anthropic-consumer` s.3, `anthropic-aup`,
  `gemini-terms`).
- Access is personal to the agreement. Reselling or proxying access, including through consumer
  subscriptions, needs the provider's approval (`anthropic-commercial` D.4, `anthropic-aup`).
- Limits are part of the contract. Multiple accounts to evade detection or guardrails, and bypassing
  restrictions or sign-up, are prohibited (`anthropic-aup`).
- Regions and tiers are conditions of access (`anthropic-aup`, `gemini-terms`).
- Unpaid tiers can mean training and human review of inputs (`gemini-terms`).
- Terms are per provider and change often. Read the provider's current page at sweep time; treat the
  quotes here as the rule on the fetch date. Enterprise agreements can override public terms: if the
  brief relies on one, the disposition is ask-owner.

## Questions a sweeper asks of each claim

- Which provider and which agreement or tier does this claim run on?
- Do provider outputs flow anywhere other than the end user: logs used for training, evaluation sets,
  synthetic data, a "teacher" pipeline?
- Does the design need more throughput than one account's granted limits, and how does it get it?
- Does a third party reach the model through our account, and do the terms allow that audience?
- Which countries are users in, and does the tier in use serve them?
- What data is sent, and does the tier's data clause allow it?

## Severity guidance

Output harvesting for a competing model, unauthorised resale and personal data on a training-enabled
tier answer yes to the first policy question (break third-party terms): critical. Limit evasion and
region or tier mismatches are high when the brief's capacity or market depends on them. Where the brief
cites a custom enterprise agreement the sweeper cannot read, record ask-owner rather than dismissing.

## Not this lens

- Licences of open-weight models, code and datasets: licensing.
- Copyright in scraped content and site terms for scraping: copyright-data-rights.
- HIPAA business associate agreements and GDPR processor contracts: privacy-regulated-data.
- Prompt injection and agent tool safety: agent-security.
