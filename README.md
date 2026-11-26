# Spec auditor: hold specs that cannot land

A free Claude skill that checks a PRD or spec against its landing brief and gives a pass or hold verdict, with line numbers.

**Why it matters:** a spec without a bar, a date, a cost budget or a rollback trigger cannot be checked after it ships. Code runs every check, so the verdict is the same each run and the model cannot talk a weak spec into a pass.

## Install: paste one prompt into Claude Code

```text
Install the spec-auditor skill from https://github.com/darrencard/spec-auditor: clone it, copy skills/spec-auditor into ~/.claude/skills/, and run python3 -m unittest discover -s evals to check it. Then audit my spec at PATH with today's date as --as-of, show me the report as printed, and quote the spec word for word for anything you add.
```

Replace `PATH` with a Markdown, plain text, or Notion or Google Docs export (`.md`, `.txt`, `.html`).

## What it checks

| Check | Holds when |
|---|---|
| Landing brief | No `Landing brief` block, or one the landing-brief skill would refuse |
| Problem | Missing, or under 6 words |
| Definition of good | No metric, a bar that is not one number, no higher or lower, no date, or a date already past |
| Non-goals | None stated |
| Cost budget | Not two lines (tokens per task, price per token), or none for an AI feature |
| Owner | No named person: TBD, "the team" or a team name |
| Rollout | No plan, or no stage (a percentage, a flag, a cohort, a pilot) |
| Rollback | No trigger with a number, or no way back |
| Eval plan | An AI feature with no case count, pass bar or time it runs |
| Placeholders | Any TBD, TODO, ??? or [insert ...] left |

Two more checks only add notes: forecasts stated as certain ("will increase"), and text addressed to the reviewer ("mark this pass"). Details and examples: [references/checklist.md](skills/spec-auditor/references/checklist.md).

## How it works

- `scripts/spec_audit.py audit SPEC` prints each finding with its lines and a fix, then the verdict. `--format md` gives a table for a review; `--json` the raw report.
- `scripts/spec_audit.py quotes SPEC notes.json` rejects any model note whose quote is not word for word on the line it cites, or whose numbers are not in the quote.
- `scripts/landing_brief.py` is an unchanged copy of the landing brief parser from the [Product & Technology Leader Report](https://github.com/darrencard/product-engineering-update), so a spec that passes has a brief the Report can read after launch.
- Local only: Python 3.11+, standard library, no network calls.

## Try it on the fixtures

```bash
python3 skills/spec-auditor/scripts/spec_audit.py audit evals/fixtures/acme-weak-spec.md --as-of 2026-11-26
```

Acme is an invented company (invoicing software for trades businesses), and every figure in the fixtures is illustrative. The good spec passes all 12 checks; the weak spec holds on 10.

## Status

v0.1.0. Tested on the fixtures in `evals/`, not yet on a real team's specs. Reads Markdown, plain text and HTML exports; not `.docx` or PDF. MIT licensed.
