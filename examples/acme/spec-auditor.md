## Spec audit: **hold**

**Hold: two checks stop this build plan. Set the number that triggers an undo and complete the quality test plan before build starts.**

2 hold, 1 note, 11 pass. AI feature: yes. As of 2026-08-03. The build plan is checked against its landing brief, a one-page plan: what good looks like, by when, at what cost. Line numbers refer to examples/acme/specs/quote-drafting.md. The landing brief is examples/acme/briefs/quote-drafting.md.

| Result | Check | Lines | Finding | Fix |
|---|---|---|---|---|
| hold | When to undo it | L48, L50 | The plan for undoing it has no number that triggers the undo. | Say what number triggers it (such as an error rate over 2%) and how it is done. |
| hold | Quality tests | L37, L39, L40 | The quality test plan does not say when the tests run. | State the number of cases, the pass mark as a number, and when the quality tests run. |
| note | Today's number | - | No current value for the number, so the size of the gap to the target is unknown. | State it with its source, such as "Today 34% (quoting events table, Q3)". |
| pass | Landing brief | brief L5 | The landing brief is complete: every part is there. |  |
| pass | Brief date | brief L11 | The brief's date, 2026-11-15, is still ahead. |  |
| pass | Result, not work | brief L8 | The number is a result, not a count of work or use. |  |
| pass | Brief copy | L6 | The build plan's copy of the landing brief matches the brief. |  |
| pass | Owner | brief L16 | Owner named: Head of Product, Quoting squad. |  |
| pass | Release stages | L42, L44, L45, L46 | Release stages planned, on 3 lines. |  |
| pass | Placeholders | - | No placeholders left. |  |
| pass | Guardrail | L32, L34, L35 | A guardrail number with a limit is named. |  |
| pass | Assumptions | L52 | Risks, assumptions or open questions listed (2 lines). |  |
| pass | Certainty | - | No forecast stated as certain. |  |
| pass | Notes to reviewer | - | No text addressed to the reviewer. |  |

For your engineers: check codes Landing brief = brief, Brief date = date, Result, not work = outcome, Brief copy = brief-match, Owner = owner, Release stages = rollout, When to undo it = rollback, Quality tests = eval-plan, Placeholders = placeholders, Guardrail = guardrail, Today's number = baseline, Assumptions = assumptions, Certainty = certainty, Notes to reviewer = instructions.
