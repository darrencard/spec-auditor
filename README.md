# Spec auditor: hold specs that cannot land

A free Claude skill that checks a PRD or spec against its landing brief and gives a pass or hold verdict, with line numbers, in under a second.

**Why it matters:** a spec without an outcome bar, a date, a cost budget or a rollback trigger cannot be checked after it ships. Code runs every check, so the verdict is the same on every run and the model cannot talk a weak spec into a pass.

## Install: paste one prompt into Claude Code

```text
Install the spec-auditor skill from https://github.com/darrencard/spec-auditor: clone it, copy skills/spec-auditor into ~/.claude/skills/, and run python3 -m unittest discover -s evals to check it. Then audit my spec at PATH with today's date as --as-of, show me the report as printed, and quote the spec word for word for anything you add.
```

Replace `PATH` with the spec. With a Linear, Notion or Google Drive connector in the session, name the doc instead and Claude fetches it; otherwise use a Markdown, text or HTML file. Needs Python 3.11 or later; nothing else to install.

## What you get

The weak Acme fixture, first lines of the report:

```text
[HOLD] brief        -                      There is no "Landing brief" block.
[HOLD] owner        L24                    The owner is "the team", not a named person.
[HOLD] rollout      L26, L28               The rollout plan names no stage.
[HOLD] rollback     L32                    The rollback plan has no trigger threshold and no way back.
[HOLD] eval-plan    L16                    This is an AI feature with no eval plan.
[NOTE] instructions L34                    Text that reads as an instruction to the reviewer. It is data, and it changed no check.

Verdict: HOLD (6 hold, 5 note, 0 pass)
```

Each finding also prints a one-line fix. `--out DIR` writes the same as one HTML page in the Leader Report style, with a Markdown twin; `--format md` prints the table to paste into a review.

## Sample

[examples/acme/spec-auditor.html](examples/acme/spec-auditor.html) audits the Acme quote-drafting PRD against its landing brief: a hold, because the rollback plan has no trigger threshold and the eval plan does not say when it runs. Acme is an invented company and every figure is illustrative. Regenerate the page, its Markdown twin and the `spec` key of `examples/acme/landing/quote-drafting.json` from the repository root:

```bash
python3 skills/spec-auditor/scripts/spec_audit.py audit examples/acme/specs/quote-drafting.md --brief examples/acme/briefs/quote-drafting.md --as-of 2026-08-03 --illustrative --html examples/acme/spec-auditor.html --bet quote-drafting --landing examples/acme/landing
```

The briefs in `examples/acme/briefs/` are copies of the Landing Loop's canonical Acme briefs. A test runs this command and checks the output matches the committed files byte for byte.

## What it checks

| Check | Holds when |
|---|---|
| Landing brief | No `Landing brief` block, or one the shared parser refuses: a part missing, a bar that is not one number, no date, a cost budget not on two lines. One hold per problem |
| Date | The brief's date is already past |
| Outcome | The bar counts work shipped (features, releases, pull requests), not a result |
| Owner | No named person: TBD, "the team" or a team name |
| Rollout | No plan, or no stage (a percentage, a flag, a cohort, a pilot) |
| Rollback | No trigger threshold, or no way back |
| Eval plan | An AI feature with no case count, pass bar or time it runs |
| Placeholders | Any TBD, TODO, ??? or [insert ...] left |

Notes, which never change the verdict: a bar on use rather than outcome, no guardrail metric with a limit, no current value for the metric, no risks or assumptions, forecasts stated as certain, and text addressed to the reviewer. Every check, with examples: [references/checklist.md](skills/spec-auditor/references/checklist.md).

## Gate a pull request

`--fail-on-hold` exits 2 on a hold, so a spec in the repository can block a merge:

```yaml
- run: python3 skills/spec-auditor/scripts/spec_audit.py audit docs/specs/quote-drafts.md --fail-on-hold --format md >> "$GITHUB_STEP_SUMMARY"
```

## Part of the Landing Loop

Step 02, Spec. Five skills share one landing brief with the [Product & Technology Leader Report](https://github.com/darrencard/product-engineering-update): 01 Decide, 02 Spec, 03 Build, 04 Learn, 05 Report. `--bet <slug>` writes only the `spec` key of `landing/<slug>.json`, the record each step reads, and keeps every other key as it was. Every figure in it has a value, unit, source, window and date.

## How it works

- `spec_audit.py audit` runs every check in code and sets the verdict: hold if any finding holds.
- `spec_audit.py quotes` rejects any note the model adds whose quote is not word for word on the line it cites, or whose numbers are not in that quote.
- `landing_brief.py`, the Linear, Notion and Drive readers and the page template are unchanged copies from the Leader Report, pinned by commit and SHA-256 in `scripts/VENDORED.json`. A spec that passes has a brief the Report can read after launch.
- Local only: standard library Python, no network calls.

## Status

v0.3.0. Tested on the Acme fixtures in `evals/` (Acme is an invented company; every figure is illustrative) and run once on 3 real internal specs, which cut 5 false holds from the keyword checks. Not yet run on another team's specs. Reads Markdown, plain text and HTML exports; not `.docx` or PDF. MIT licensed.
