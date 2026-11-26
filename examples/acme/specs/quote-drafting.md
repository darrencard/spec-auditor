# PRD: Quote drafting assistant

Acme (invented company). Illustrative sample spec; every figure is illustrative.
Squad: Quoting. Status: ready for review. Brief: briefs/quote-drafting.md.

## Landing brief

- **Problem:** Tradespeople spend evenings writing quotes by hand, so quotes go out late and lose the job.
- **Metric:** Quote draft acceptance rate
- **Bar:** 40%
- **Better:** higher
- **By:** 2026-11-15
- **Non-goals:** No pricing advice. No change to the quote PDF.
- **Tokens per task:** 9,000
- **Price per token:** $0.000003
- **The line:** model call. The assistant drafts the quote text; prices come from the price book in fixed code.
- **Decides the next step:** Head of Product, Quoting squad

## Who it is for

Owner-operators and office managers at plumbing, electrical and HVAC firms with 2 to 20 staff. They visit a site, take notes on a phone, and write the quote that evening.

## What we will build

1. After a site visit, the tradesperson dictates or types job notes in the Acme app.
2. A model call turns the notes into draft quote text: a scope summary and draft line items.
3. Fixed code matches each line item to the firm's price book and adds tax and totals. The model never sets a price.
4. The tradesperson edits and sends. Nothing is sent without a tap on Send.

Acceptance rate counts a draft as accepted when it is sent with at most light edits (under 20% of characters changed).

## Guardrails

- Guardrail: quotes sent with a price outside the price book stay at 0.
- Guardrail: support tickets about quotes do not rise more than 10% on the July level.

## Eval plan

- 300 job notes from pilot firms who agreed to share them, with the quote the tradesperson finally sent as the reference.
- Pass bar: 85% of draft line items match a sent line item, and 0 drafts include a price.

## Rollout

- Stage 1: internal staff accounts behind the `quote_drafts` feature flag, two weeks.
- Stage 2: a pilot cohort of 40 firms who opted in.
- Stage 3: 25% of accounts, then 100%.

## Rollback

- If drafts start to look wrong, the squad turns off the `quote_drafts` flag and quoting falls back to the manual form.

## Risks and open questions

- Riskiest assumption: tradespeople will send a draft after light edits. Test: stage 1 measures the share of drafts sent with light edits before the pilot starts.
- Do jobs over $10,000 need a second review? The Head of Product decides before stage 3.
