---
id: market-reality
version: 0.1.0
title: Market reality
group: business
owner: sf
scope: >-
  Judges whether a brief's commercial premises can hold: who the customer is, what they pay, the
  volume that implies, whether the cost to serve fits under the price, how the market was sized, and
  which single capability must work (the correctness floor). Leaves the organisation's mission,
  policies and regulators to company-context, and provider terms to provider-terms.
applies_when:
  signals: [pricing, price, per month, per seat, subscription, free tier, freemium, revenue, margin,
    unit economics, market size, total addressable, serviceable market, addressable market, willingness to pay, customers will pay,
    users will pay, business model, monetis, monetiz, paid plan, cost per, per request, per user,
    daily active, monthly active, go-to-market, scale to, million users]
required_statements:
  - id: customer-price-volume
    statement: The brief states the target customer, the price they pay, and the expected volume (users and requests per user per period).
  - id: correctness-floor
    statement: The brief states the correctness floor, the one capability that must work for the product to have value to that customer.
  - id: cost-to-serve
    statement: The brief states or bounds the marginal cost to serve one user or request, with the provider prices it rests on.
adapters: [web_page]
---

# Market reality

Business lenses rarely have a statute that decides them. Most traps here are settled by arithmetic
on the brief's own numbers plus a provider's price page, or by deep-research; few can be verified by
a single quote, and that is expected.

## Principles

- **Size before you optimise.** Follow deep-research step 2b and experiment-designer step 0: who
  the users are and how many, what they spend and what the project earns per user after fees, what
  they tolerate at that price, the request volume computed from those, and the correctness floor.
  The sizing relaxes some targets (often latency and raw scale) and hardens others (often accuracy).
  Each figure is sourced or marked `[proposed]`, as a range where sources disagree.
- **Bottom-up sizing from primary counts.** Count reachable buyers from primary statistics (census-susb,
  bls-oews, eurostat-sbs) times a sourced price; a top-down "1% of a big market" figure is not sizing.
- **Public-company figures come from filings** (sec-edgar-search), not press releases or analyst
  summaries.
- **Unit economics from the provider's own price page** (anthropic-pricing as an example; use the
  provider the brief names, refreshed within 30 days): cost per user = requests per user x units per
  request x unit price. It must sit below revenue per user after fees, with margin.
- **Free tiers need a cap.** A free user's marginal cost is real; without a per-user quota the
  worst-case cost is unbounded.
- **Latency and scale are tolerances, not goals.** Perceived-latency thresholds (nng-response-times,
  secondary) tell what users notice; a target tighter than the market needs, while accuracy is
  unstated, spends budget on the wrong axis.

## Questions a sweeper asks of each claim

- Who exactly is the paying customer, how many are reachable, and from which primary count?
- What is the price, and what is revenue per user after payment and platform fees?
- How many requests per user per month, and what does each cost at the provider's current price?
  Does cost per user exceed revenue per user at the stated volume?
- Where does the willingness-to-pay figure come from: interviews, a pricing test, comparable
  public filings, or nowhere?
- Is there a free tier, and what bounds one free user's monthly cost?
- What is the correctness floor? Are latency or scale targets stated while it is not?

## Severity guidance

Unit economics that cannot work at the stated price, or an uncapped free tier, answer yes to
material-exposure (high). A top-down TAM, an unsourced willingness-to-pay or a latency target that
displaces an unstated correctness floor is usually principal-reject (medium), rising to high when
the brief commits spend or a launch on it. Price and margin choices are the owner's: the usual
disposition is reframe (state the sizing) or ask-owner (choose the price).

## Not this lens

- Mission, policies, regulators and data rights of the organisation: company-context.
- Whether a provider's terms permit the use: provider-terms. Physical latency and bandwidth limits:
  performance and capacity lenses. Evaluation statistics: ml-evaluation.
