---
id: numeric-representation
version: 0.1.0
title: Numeric representation (money, floats, time, integer width)
group: theory-measurement
owner: sf
scope: >-
  Judges how a brief represents numbers and time: money in binary floating point, float equality and
  order-dependent sums, naive local timestamps, and fixed-width counters that can wrap. Leaves tax and
  accounting law to the regulatory lenses and database type mechanics beyond representation to databases.
applies_when:
  signals: [price, pricing, payment, invoice, ledger, balance, currency, money, premium, refund, payout, sales tax, vat rate, cents, float, double, decimal, numeric, rounding, timestamp, time zone, timezone, daylight, utc offset, in utc, utc time, schedule, counters, running total, sequence number, int32, 32-bit, overflow]
required_statements:
  - id: money-type-and-rounding
    statement: Where money appears, the brief states the numeric type (integer minor units or fixed-scale decimal), the currency scale, and the rounding rule and where rounding happens.
  - id: time-representation
    statement: Where times are stored or compared, the brief states that instants are stored in UTC or with an offset and how user time zones and daylight-saving changes are handled.
  - id: integer-ranges
    statement: Where counters, ids or running totals are stored, the brief states their maximum lifetime value or width and what happens on overflow.
adapters: [web_page, paper]
---

# Numeric representation

## Principles

- Most decimal fractions are not exactly representable in binary floating point (python-floatingpoint,
  goldberg-1991); exact decimal arithmetic is preferred in accounting because binary differences break
  equality and accumulate (python-decimal).
- Equality on computed floats is unreliable, and a fixed error bound is not a general cure
  (python-floatingpoint, goldberg-1991).
- Floating-point addition is not associative, so parallel or reordered sums differ (goldberg-1991).
- A naive timestamp cannot be placed unambiguously, and a local time's UTC instant can depend on
  daylight-saving decisions (python-datetime, rfc3339).
- Fixed-width integer arithmetic wraps silently in mainstream languages (jls-integer-ops).

## Questions a sweeper asks of each claim

- What type holds each monetary amount, in storage, in transit (JSON numbers are binary doubles in
  most parsers) and in computation? What is the rounding rule for division, pro-rating and allocation,
  and who gets the remainder?
- Does any acceptance criterion compare computed floats for exact equality, or a fixed epsilon with no
  justification?
- Must a total reproduce across runs, shards, or batch versus streaming paths?
- Are instants stored in UTC or with an offset? Are future local-time events (a 02:30 job, a billing
  day) stored with their zone? What happens on DST gaps and overlaps?
- What is the maximum lifetime value of each counter, id and sum, and is the width enough?

## Severity guidance

- Money in binary float in a ledger, billing or payout path: production-failure or material-exposure (high).
- Naive timestamps across zones or DST in scheduling or billing: production-failure (high).
- Counter or id width that will be exceeded at the brief's stated scale: production-failure (high);
  if the scale is unknown, record the omission.
- Float equality and order-dependent sums in tests or reports: principal-reject (medium), higher when
  they decide money or safety.
- Rounding rules mandated by law or contract turn on jurisdiction: disposition ask-owner.

## Not this lens

- Tax, accounting standards and consumer price display law: regulatory lenses.
- Column type choice, migrations and indexing beyond representation: databases.
- Clock synchronisation and ordering across nodes: distributed-systems.
