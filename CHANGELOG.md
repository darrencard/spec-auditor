# Changelog

## 0.3.5 (2026-11-27)

- 12px floor: every label on the page (the header, the next step, who decides and who owns it, status lines, section labels, the figures table, owner names and due dates) renders at 12px or more. The page raises any smaller size in the vendored template and svgkit to 12px as it inlines them (was 11px), 11.5px text included; the vendored files are unchanged. A test checks no font size under 12px in the page CSS.
- Dates never break: every ISO date in the page's text (headings, intro, figure lines) is held on one line with `white-space: nowrap`, so a narrow screen never splits one at a hyphen. A test checks every date on the sample.
- Plain words: the README defines a bet once, under its opening line ("A bet is a project you expect to move a number; its bar is the target its landing brief sets."), and SKILL.md tells Claude to use the user's word, project or bet, while the record key stays `bet`. A test checks no other README or SKILL.md prose says bet or bar.

## 0.3.4 (2026-11-27)

- Full column: the heading, the intro, the next step, section text and captions run the full width of the content column, the same width as the scorecard frame (the site's rule since 2026-11-25). The page's own CSS drops its caps on text (the heading's 22ch and the notes' 80ch) and overrides the vendored template's 62ch intro and svgkit's 76ch caption after their rules, so neither hash-pinned file changes. The next step runs the full column too, with the cover's figures under it in place of beside it. The heading balances its lines; text breaks with `text-wrap: pretty`. A test checks the page CSS caps no text and the sample carries the override.

## 0.3.3 (2026-11-27)

- Scorecard fix round: a check row has no picture, so its name takes the picture column too and stays on one line; the share ("11 of 14 pass") prints once, in the frame head beside "Checks" with its bar, and the "All checks" row is gone, as /update does; the figure column prints in one case, numerals and capitals ("WHOLE PLAN", "BRIEF L5"), as /update. Tests for each.
- The page's picture is now the scorecard, in the grammar of the outcome scorecard on dacard.ai/update: one frame of HTML rows split by hairlines. The first row is a share bar of the checks that pass ("11 of 14 pass", with the verdict word); then one row per check, holds first, then the note, then the passes, each with its line references as the figure and HOLD in ink or NOTE and PASS muted as text. Labels and words render 12px Geist Mono, names 14px Geist; no text in any SVG, no viewBox, no boxed chip. The page outline drawing (wide and tall SVGs) is gone.
- The verdict above the lede is a word in ink, no longer a filled chip.
- svgkit 1.2.0, vendored byte-identical from landing-loop 78784ef (the commit that last changed `tools/svgkit.py`; rollout recipe at c6c47e7) and pinned in `scripts/VENDORED.json`.
- Tests copied from the rollout recipe: no text inside an SVG, no scaled picture, only the 12px and 14px sizes in the frame, no box in the frame and no chip before the engineers' fold, no legacy svgkit primitive (rendered with DeprecationWarning as an error), one frame with the share row and one row per check in order with each line reference printed exactly, the aria-label equal to the verdict, and nothing drawn that the page does not print.
- Plain words in the README and SKILL.md: target (not bar), pass mark, the project file, and the landing brief defined once as a one-page plan: what good looks like, by when, at what cost. SKILL.md tells Claude to use the user's own word if they say bet. Keys, file names and flags (`--bet`) are unchanged.

## 0.3.2, 2026-11-27

- The HTML page follows the Landing Loop sample anatomy, built like did-it-land's and eval-kit's: the shared header (mark, DACARD, skill, date, version, blue Illustrative tag) in place of the report's rail, an h1 verdict ("Hold: two checks stop this build plan."), the verdict mark with what to fix, the signature picture, one next step for the person the landing brief names (brass) and when, then the findings with the passes folded, and the landing brief beside the lines the holds cite. Check codes, files and flags fold under "For your engineers". No call to action: the page is the skill's own output.
- The signature picture: the build plan drawn as a page outline, one stroke per line and its headings marked, with each check ticked down the edge at the first line it rests on. A hold is solid ink with its line numbers ("Hold L48, L50") and its cited lines drawn heavy; a pass is an outlined tick; a note is a ring. Checks on the landing brief sit above the page, checks on the whole plan below it. A 640 wide variant beside the next step on desktop and a 340 wide one for phones; its aria-label states the answer. Drawn with svgkit, vendored byte-identical from landing-loop 5d01756 and pinned in `scripts/VENDORED.json` under `landing-loop`.
- Plain words in the page and the Markdown twin: build plan, target, quality tests, when to undo it, release stages, group of customers. The page takes the vendored template's whole stylesheet; the template file itself is unchanged. The report, the JSON and the `spec` key keep their words apart from the version.
- Design fix round 2: no text below 11px at any width (the page raises the vendored template's and svgkit's 10 and 10.5px labels as it writes its CSS; both files stay byte-identical). The header, the tab title and the footer print the plain name, Spec auditor; the code name moves to the engineers' fold. A plan titled "PRD: ..." reads "Build plan: ..." in the intro and the outline, and the outline glosses the plan's own headings: Eval plan (quality test plan), Rollout (release stages), Rollback (when you'd undo it). Public copy, on the page and in the Markdown twin, prints none of record, bet, the bar, PRD, ARR or tokens. Tests for each.
- Tests: the picture draws only figures the page prints, one solid mark per hold, no status colour, the aria-label states the answer, public copy uses the plain words, the page follows the anatomy, and the vendored svgkit matches its pin.

## 0.3.1, 2026-11-26

- README: install through the Landing Loop bundle (`/plugin marketplace add darrencard/landing-loop`, then `/plugin install spec-auditor@landing-loop`), with the paste-in prompt kept for a standalone install.
- README: the repository is public, so the private-until-review notes are gone, and the loop is counted as eleven skills plus the Product & Technology Leader Report.
- README: one trademark line for Claude and Claude Code.
- Acme fixtures name people by role (Head of Product, Quoting squad; Quoting squad tech lead), as the loop briefs do.
- No change to what the skill computes. The version in the sample record's `tool` field moves with the release.
- A hold prints in ink, not brass; brass is kept for the owner's name. Text selection and the focus ring print in ink, not the template's green.
- `spec_audit.py` checks for Python 3.11 or later first, before it reads or writes anything, and stops with a plain message on anything older.
