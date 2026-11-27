# Changelog

## 0.3.2, 2026-11-27

- The HTML page follows the Landing Loop sample anatomy, built like did-it-land's and eval-kit's: the shared header (mark, DACARD, skill, date, version, blue Illustrative tag) in place of the report's rail, an h1 verdict ("Hold: two checks stop this build plan."), the verdict mark with what to fix, the signature picture, one next step for the person the landing brief names (brass) and when, then the findings with the passes folded, and the landing brief beside the lines the holds cite. Check codes, files and flags fold under "For your engineers". No call to action: the page is the skill's own output.
- The signature picture: the build plan drawn as a page outline, one stroke per line and its headings marked, with each check ticked down the edge at the first line it rests on. A hold is solid ink with its line numbers ("Hold L48, L50") and its cited lines drawn heavy; a pass is an outlined tick; a note is a ring. Checks on the landing brief sit above the page, checks on the whole plan below it. A 640 wide variant beside the next step on desktop and a 340 wide one for phones; its aria-label states the answer. Drawn with svgkit, vendored byte-identical from landing-loop 5d01756 and pinned in `scripts/VENDORED.json` under `landing-loop`.
- Plain words in the page and the Markdown twin: build plan, target, quality tests, when to undo it, release stages, group of customers. The page takes the vendored template's whole stylesheet; the template file itself is unchanged. The report, the JSON and the `spec` key keep their words apart from the version.
- Tests: the picture draws only figures the page prints, one solid mark per hold, no status colour, the aria-label states the answer, public copy uses the plain words, the page follows the anatomy, and the vendored svgkit matches its pin.

## 0.3.1, 2026-11-26

- README: install through the Landing Loop bundle (`/plugin marketplace add darrencard/landing-loop`, then `/plugin install spec-auditor@landing-loop`), with the paste-in prompt kept for a standalone install.
- README: the repository is public, so the private-until-review notes are gone, and the loop is counted as eleven skills plus the Product & Technology Leader Report.
- README: one trademark line for Claude and Claude Code.
- Acme fixtures name people by role (Head of Product, Quoting squad; Quoting squad tech lead), as the loop briefs do.
- No change to what the skill computes. The version in the sample record's `tool` field moves with the release.
- A hold prints in ink, not brass; brass is kept for the owner's name. Text selection and the focus ring print in ink, not the template's green.
- `spec_audit.py` checks for Python 3.11 or later first, before it reads or writes anything, and stops with a plain message on anything older.
