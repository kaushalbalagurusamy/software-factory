# Changelog

## 0.1.0 - 2026-10-14
- Initial lens: 5 traps, all verified against providers' own terms pages (commercial terms, consumer
  terms and usage policy of one provider; Gemini API additional terms).
- Traps: output distillation into a competing model (LEG-01), unauthorised resale or proxying,
  multi-account limit evasion, unsupported region or tier, sensitive data on an unpaid tier.
- OpenAI terms pages return HTTP 403 to automated fetches and are not cached; noted on LEG-01.
- Required statements: provider and agreement, output use, data sent.
- Cases: a planted and clean twin per trap, plus one omission pair (output-use).
