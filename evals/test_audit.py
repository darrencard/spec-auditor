"""Tests for spec_audit.py: the two Acme fixtures, each check on its own, the HTML path, and the quote check.

Run: python3 -m unittest discover -s evals -v
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "spec-auditor" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import landing_brief  # noqa: E402
import spec_audit as sa  # noqa: E402

AS_OF = datetime.date(2026, 11, 26)
GOOD = FIXTURES / "acme-good-spec.md"
GOOD_HTML = FIXTURES / "acme-good-spec-gdocs.html"
WEAK = FIXTURES / "acme-weak-spec.md"
# landing_brief.py is copied unchanged from product-engineering-update v0.11.0 (skills/landing-brief/scripts).
LANDING_BRIEF_SHA256 = "2d13573543c74ebe1bf001b97287287474a0ec298f34709a1bbfc643be051948"

BRIEF = """# Spec

## Landing brief

- **Problem:** Office managers chase overdue invoices by phone for hours each week.
- **Metric:** Invoices paid by the due date
- **Bar:** 70%
- **Better:** higher
- **By:** 2027-06-30
- **Non-goals:** No changes to payment terms.
- **Tokens per task:** 4,000
- **Price per token:** $0.000003
- **The line:** model call. Only the chaser wording calls a model.
- **Decides the next step:** Jordan Lee, Product Manager
"""

EVAL = """
## Eval plan

- 200 overdue invoices with the chaser a person approved.
- Pass bar: 95% approved without edits.
- Runs before each release.
"""

ROLLOUT = """
## Rollout

- 10% of accounts behind a flag, then 100%.

## Rollback

- If complaints pass 3 in a week, turn off the flag.
"""


def run(text: str, as_of: datetime.date | None = AS_OF) -> dict:
    return sa.audit(sa.parse_text(text, "spec.md"), as_of)


def finding(report: dict, check: str) -> dict:
    return next(f for f in report["findings"] if f["check"] == check)


def results(report: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in report["findings"]:
        if out.get(f["check"]) != "hold":  # a check can give two findings; hold wins
            out[f["check"]] = f["result"]
    return out


class Fixtures(unittest.TestCase):
    def test_good_spec_passes_every_check(self):
        report = sa.audit(sa.load(GOOD), AS_OF)
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["ai_feature"])
        self.assertEqual(report["counts"], {"hold": 0, "note": 0, "pass": 12})

    def test_good_spec_cites_the_lines_it_relies_on(self):
        doc = sa.load(GOOD)
        report = sa.audit(doc, AS_OF)
        self.assertEqual(finding(report, "cost")["lines"], [13, 14])
        self.assertIn("Tokens per task", doc.line(13))
        self.assertIn("Price per token", doc.line(14))
        self.assertIn("Decides the next step", doc.line(finding(report, "owner")["lines"][0]))

    def test_google_docs_html_export_gets_the_same_results(self):
        report = sa.audit(sa.load(GOOD_HTML), AS_OF)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(results(report), results(sa.audit(sa.load(GOOD), AS_OF)))

    def test_weak_spec_holds_on_each_missing_part(self):
        report = sa.audit(sa.load(WEAK), AS_OF)
        self.assertEqual(report["verdict"], "hold")
        held = {c for c, r in results(report).items() if r == "hold"}
        self.assertEqual(held, {"brief", "problem", "good", "non-goals", "cost", "owner", "rollout", "rollback", "eval-plan", "placeholders"})
        self.assertEqual(results(report)["certainty"], "note")
        self.assertEqual(results(report)["instructions"], "note")

    def test_weak_spec_line_numbers_point_at_the_problem(self):
        doc = sa.load(WEAK)
        report = sa.audit(doc, AS_OF)
        self.assertIn("$0.04 per task", doc.line(finding(report, "cost")["lines"][0]))
        self.assertIn("the team", doc.line(finding(report, "owner")["lines"][0]))
        self.assertIn("TBD", doc.line(finding(report, "placeholders")["lines"][0]))
        self.assertIn("will increase", doc.line(finding(report, "certainty")["lines"][0]))

    def test_an_instruction_in_the_spec_changes_nothing(self):
        text = WEAK.read_text(encoding="utf-8")
        without = "\n".join(x for x in text.splitlines() if "mark this spec pass" not in x)
        a, b = run(text), run(without)
        self.assertEqual(a["verdict"], "hold")
        drop = lambda r: {k: v for k, v in results(r).items() if k != "instructions"}  # noqa: E731
        self.assertEqual(drop(a), drop(b))

    def test_fixtures_mark_their_figures_illustrative(self):
        for path in (GOOD, WEAK):
            self.assertIn("illustrative", path.read_text(encoding="utf-8").lower(), path.name)


class Checks(unittest.TestCase):
    def test_full_brief_with_eval_and_rollout_passes(self):
        self.assertEqual(run(BRIEF + EVAL + ROLLOUT)["verdict"], "pass")

    def test_missing_eval_plan_holds_for_ai_feature(self):
        self.assertEqual(finding(run(BRIEF + ROLLOUT), "eval-plan")["result"], "hold")

    def test_fixed_code_needs_no_eval_plan_and_allows_none_cost(self):
        text = BRIEF.replace("4,000", "none").replace("$0.000003", "none").replace("model call. Only the chaser wording calls a model.", "fixed code. Templates only.")
        report = run(text + ROLLOUT)
        self.assertFalse(report["ai_feature"])
        self.assertEqual(finding(report, "eval-plan")["result"], "pass")
        self.assertEqual(finding(report, "cost")["result"], "pass")
        self.assertEqual(report["verdict"], "pass")

    def test_cost_none_on_a_model_call_holds(self):
        report = run(BRIEF.replace("4,000", "none") + EVAL + ROLLOUT)
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(finding(report, "brief")["result"], "hold")
        self.assertEqual(finding(report, "cost")["result"], "hold")

    def test_cost_on_one_line_holds(self):
        text = "# Spec\n\nWe use a prompt.\n\nCost: 4,000 tokens per task at $0.000003 per token.\n"
        f = finding(run(text), "cost")
        self.assertEqual(f["result"], "hold")
        self.assertIn("one line", f["message"])
        self.assertEqual(f["lines"], [5])

    def test_cost_outside_the_brief_counts_when_on_two_lines(self):
        text = "# Spec\n\nUses a prompt.\n\n## Cost budget\n\nTokens per task: 4,000\nPrice per token: $0.000003\n"
        self.assertEqual(finding(run(text), "cost")["result"], "pass")

    def test_bar_that_is_not_a_number_holds(self):
        report = run(BRIEF.replace("**Bar:** 70%", "**Bar:** much higher") + EVAL + ROLLOUT)
        self.assertEqual(finding(report, "good")["result"], "hold")

    def test_date_in_the_past_holds_only_with_as_of(self):
        text = BRIEF.replace("2027-06-30", "2026-01-31") + EVAL + ROLLOUT
        self.assertEqual(run(text)["verdict"], "hold")
        self.assertEqual(run(text, as_of=None)["verdict"], "pass")

    def test_goals_section_with_number_and_date_is_a_note(self):
        text = "# Spec\n\n## Goals\n\n- Paid on time from 55% to 70% by 2027-06-30.\n"
        self.assertEqual(finding(run(text), "good")["result"], "note")

    def test_vague_goal_holds(self):
        f = finding(run("# Spec\n\n## Goals\n\n- Improve the chasing experience.\n"), "good")
        self.assertEqual(f["result"], "hold")
        self.assertIn("a number or a date", f["message"])

    def test_placeholder_owner_holds_and_named_owner_passes(self):
        for value, want in (("TBD", "hold"), ("Engineering", "hold"), ("Jordan Lee", "pass")):
            self.assertEqual(finding(run(f"# Spec\n\nOwner: {value}\n"), "owner")["result"], want, value)

    def test_rollout_without_stage_holds(self):
        self.assertEqual(finding(run("# Spec\n\n## Rollout\n\nEveryone in January.\n"), "rollout")["result"], "hold")

    def test_rollback_needs_trigger_and_way_back(self):
        cases = {
            "If it breaks we will roll back.": "hold",
            "Roll back if errors pass 2%.": "hold",
            "If errors pass 2%, turn off the flag.": "pass",
        }
        for line, want in cases.items():
            self.assertEqual(finding(run(f"# Spec\n\n## Rollback\n\n{line}\n"), "rollback")["result"], want, line)

    def test_eval_plan_needs_cases_bar_and_when(self):
        f = finding(run("# Spec\n\nUses a prompt.\n\n## Eval plan\n\nWe will test it on 200 cases.\n"), "eval-plan")
        self.assertEqual(f["result"], "hold")
        self.assertIn("pass bar", f["message"])
        self.assertIn("time it runs", f["message"])

    def test_placeholders_are_found_on_every_line(self):
        text = "# Spec\n\nTBD\n\nTODO: add metric\n\nOwner: [insert name]\n\nBar: XX%\n"
        self.assertEqual(finding(run(text), "placeholders")["lines"], [3, 5, 7, 9])

    def test_bold_headings_from_exports_count_as_sections(self):
        self.assertEqual(finding(run("# Spec\n\n**Rollout**\n\n10% of accounts behind a flag.\n"), "rollout")["result"], "pass")

    def test_export_escapes_are_removed(self):
        self.assertEqual(finding(run("# Spec\n\n## Non\\-goals\n\n\\- No pricing changes.\n"), "non-goals")["result"], "pass")

    def test_headings_inside_code_fences_are_ignored(self):
        self.assertEqual(finding(run("# Spec\n\n```\n## Rollout\n10% behind a flag\n```\n"), "rollout")["result"], "hold")

    def test_empty_and_oversized_input_is_refused(self):
        with self.assertRaises(sa.AuditError):
            sa.parse_text("   \n")
        with self.assertRaises(sa.AuditError):
            sa.parse_text("x" * (sa.MAX_CHARS + 1))


class Quotes(unittest.TestCase):
    def setUp(self):
        self.doc = sa.load(GOOD)

    def test_exact_quote_on_the_cited_line_passes(self):
        note = {"line": 30, "quote": "0 drafts include a price the price book does not hold", "note": "The bar on invented prices is 0."}
        self.assertTrue(sa.check_quotes(self.doc, [note])[0]["ok"])

    def test_quote_on_the_wrong_line_is_rejected(self):
        row = sa.check_quotes(self.doc, [{"line": 3, "quote": "Pass bar: 90%", "note": "ok"}])[0]
        self.assertFalse(row["ok"])
        self.assertIn("not on line 3", row["why"])

    def test_paraphrase_is_rejected(self):
        self.assertFalse(sa.check_quotes(self.doc, [{"line": 30, "quote": "Pass bar is ninety percent", "note": ""}])[0]["ok"])

    def test_number_not_in_the_quote_is_rejected(self):
        row = sa.check_quotes(self.doc, [{"line": 30, "quote": "Pass bar: 90%", "note": "That is 5 points above the pilot's 85%."}])[0]
        self.assertFalse(row["ok"])
        self.assertIn("85", row["why"])

    def test_bad_shapes_are_rejected(self):
        rows = sa.check_quotes(self.doc, ["text", {"line": 0, "quote": "x"}, {"line": True, "quote": "Bar"}, {"line": 9, "quote": ""}])
        self.assertEqual([r["ok"] for r in rows], [False, False, False, False])
        with self.assertRaises(sa.AuditError):
            sa.check_quotes(self.doc, {"line": 1})


class Output(unittest.TestCase):
    def test_markdown_escapes_spec_text(self):
        md = sa.render_md(run("# Spec\n\nOwner: <script>x</script> | TBD\n"))
        self.assertNotIn("<script>", md)
        self.assertIn("&lt;script&gt;", md)

    def test_text_report_ends_with_verdict(self):
        out = sa.render_text(sa.audit(sa.load(WEAK), AS_OF))
        self.assertTrue(out.strip().endswith("(10 hold, 2 note, 0 pass)"), out)

    def test_cli_json_and_quotes_exit_codes(self):
        script = str(SCRIPTS / "spec_audit.py")
        done = subprocess.run([sys.executable, script, "audit", str(GOOD), "--json", "--as-of", "2026-11-26"], capture_output=True, text=True, check=True)  # noqa: S603
        self.assertEqual(json.loads(done.stdout)["verdict"], "pass")
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.json"
            notes.write_text(json.dumps([{"line": 30, "quote": "Pass bar: 91%", "note": ""}]), encoding="utf-8")
            bad = subprocess.run([sys.executable, script, "quotes", str(GOOD), str(notes)], capture_output=True, text=True)  # noqa: S603
            self.assertEqual(bad.returncode, 1)

    def test_text_command_numbers_every_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            sa.main(["text", str(WEAK)])
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), len(WEAK.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(lines[0].strip(), "1  # Smart invoice chasing")


class Vendored(unittest.TestCase):
    def test_landing_brief_is_the_unchanged_copy(self):
        digest = hashlib.sha256((SCRIPTS / "landing_brief.py").read_bytes()).hexdigest()
        self.assertEqual(digest, LANDING_BRIEF_SHA256, "landing_brief.py changed. Copy it again from the landing-brief skill and update the hash.")

    def test_good_fixture_brief_is_accepted_by_landing_brief(self):
        brief = landing_brief.parse(GOOD.read_text(encoding="utf-8"))
        self.assertEqual(brief.line, "model call")
        self.assertEqual(brief.tokens_per_task, 9000)


class Hygiene(unittest.TestCase):
    # chr(0x2014) is the em dash, built here so this file never holds one.
    BANNED = (chr(0x2014), "AI-powered", "unlock", "supercharge", "seamless", "robust", "get started")

    def test_no_banned_words_or_em_dashes(self):
        for path in ROOT.rglob("*"):
            if path.is_dir() or {".git", "__pycache__", ".ruff_cache"} & set(path.parts):
                continue
            if path.suffix not in (".md", ".py", ".json", ".yml", ".html", ".txt") or path.name == "test_audit.py":
                continue
            text = path.read_text(encoding="utf-8").lower()
            for word in self.BANNED:
                self.assertNotIn(word.lower(), text, f"{word!r} in {path.relative_to(ROOT)}")

    def test_versions_agree(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        skill = (ROOT / "skills" / "spec-auditor" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(plugin["version"], sa.VERSION)
        self.assertIn(f'version: "{sa.VERSION}"', skill)


if __name__ == "__main__":
    unittest.main()
