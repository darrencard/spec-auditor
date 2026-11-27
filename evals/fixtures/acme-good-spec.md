# Quote drafts from job notes

Acme (invented company, illustrative figures). Status: ready for review.

## Landing brief

- **Problem:** Tradespeople finish a site visit with notes on their phone, then spend about 25 minutes that evening typing the quote, so a third of quotes go out the next day or later and lose the job.
- **Metric:** Quotes sent within 2 hours of the visit
- **Bar:** 60%
- **Better:** higher
- **By:** 2027-03-31
- **Non-goals:** No pricing advice. No changes to invoice chasing. No new mobile app; this ships inside the existing one.
- **Tokens per task:** 9,000
- **Price per token:** $0.000003
- **The line:** model call. Line items, totals and tax stay in fixed code; only turning free-text notes into draft line items calls a model.
- **Decides the next step:** Head of Product, Quoting squad

## How it works

1. The tradesperson dictates or types job notes after the visit.
2. A model call turns the notes into draft line items, each matched to the customer's own price book.
3. Fixed code prices the lines, adds tax and totals the quote. The model never sets a price or a total.
4. The tradesperson edits and sends. Nothing is sent without a tap on Send.

Today 34% of quotes go out within 2 hours (illustrative, from the quoting events table, Q3 2026).

## Eval plan

- A set of 400 real job notes from consenting pilot customers, with the line items the tradesperson finally sent as the reference.
- Pass bar: 90% of draft line items match a sent line item, and 0 drafts include a price the price book does not hold.
- Runs in CI on every prompt change or model change, and before each rollout stage.
- Owner of the eval set: Tech lead, Quoting squad.

## Guardrails

- Guardrail: quote edits after send stay under 5% of quotes.
- Guardrail: support tickets about quotes do not rise more than 10% on the Q3 level.

## Rollout

- Stage 1: internal staff accounts behind the `quote_drafts` feature flag, two weeks.
- Stage 2: a pilot cohort of 50 customers who opted in.
- Stage 3: 25% of accounts, then 100%, each step only after the eval pass bar holds and the metric is moving the right way.

## Rollback

- Trigger: draft line-item acceptance below 70% for 3 days, or any quote sent with a price outside the price book.
- How: turn off the `quote_drafts` flag. Quoting falls back to the manual form with no data lost.
- Who: the on-call engineer can turn it off without asking; Head of Product, Quoting squad decides whether it comes back.

## Open questions

- Should drafts for jobs over $10,000 need a second review? Owner: Head of Product, Quoting squad, answer by 2026-12-15.
- Riskiest assumption: tradespeople will send a draft after light edits. Test: the internal stage measures how many draft lines are kept, before the pilot starts.
