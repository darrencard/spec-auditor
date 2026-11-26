## Spec audit: **hold**

2 hold, 1 note, 11 pass. AI feature: yes. As of 2026-08-03. Line numbers refer to examples/acme/specs/quote-drafting.md. The brief is examples/acme/briefs/quote-drafting.md.

| Result | Check | Lines | Finding | Fix |
|---|---|---|---|---|
| hold | rollback | L48, L50 | The rollback plan has no trigger threshold. | Say what number triggers it (such as an error rate over 2%) and how it is done. |
| hold | eval-plan | L37, L39, L40 | The eval plan has no time it runs. | State the number of cases, the pass bar as a number, and when the evals run. |
| note | baseline | - | No current value for the metric, so the size of the gap to the bar is unknown. | State it with its source, such as "Today 34% (quoting events table, Q3)". |
| pass | brief | brief L5 | The landing brief parses, with every part present. |  |
| pass | date | brief L11 | The brief's date, 2026-11-15, is still ahead. |  |
| pass | outcome | brief L8 | The metric is a result, not a count of work or use. |  |
| pass | brief-match | L6 | The spec's copy of the landing brief matches the brief. |  |
| pass | owner | brief L16 | Owner named: Head of Product, Quoting squad. |  |
| pass | rollout | L42, L44, L45, L46 | Rollout plan with 3 staged lines. |  |
| pass | placeholders | - | No placeholders left. |  |
| pass | guardrail | L32, L34, L35 | A guardrail metric with a limit is named. |  |
| pass | assumptions | L52 | Risks, assumptions or open questions listed (2 lines). |  |
| pass | certainty | - | No forecast stated as certain. |  |
| pass | instructions | - | No text addressed to the reviewer. |  |
