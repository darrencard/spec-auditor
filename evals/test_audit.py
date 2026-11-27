"""Tests for spec_audit.py: the two Acme fixtures, each check on its own, the HTML path, and the quote check.

Run: python3 -m unittest discover -s evals -v
"""

from __future__ import annotations

import datetime
import hashlib
import html as html_lib
import io
import json
import re
import shutil
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
sys.path.insert(0, str(SCRIPTS / "vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import landing_brief  # noqa: E402
import loop  # noqa: E402
import render  # noqa: E402
import sources  # noqa: E402
import spec_audit as sa  # noqa: E402
import svgkit  # noqa: E402

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
        self.assertEqual(report["counts"], {"hold": 0, "note": 0, "pass": 13})

    def test_good_spec_cites_the_lines_it_relies_on(self):
        doc = sa.load(GOOD)
        report = sa.audit(doc, AS_OF)
        self.assertIn("Landing brief", doc.line(finding(report, "brief")["lines"][0]))
        self.assertIn("**By:**", doc.line(finding(report, "date")["lines"][0]))
        self.assertIn("Decides the next step", doc.line(finding(report, "owner")["lines"][0]))

    def test_google_docs_html_export_gets_the_same_results(self):
        report = sa.audit(sa.load(GOOD_HTML), AS_OF)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(results(report), results(sa.audit(sa.load(GOOD), AS_OF)))

    def test_weak_spec_holds_on_each_missing_part(self):
        report = sa.audit(sa.load(WEAK), AS_OF)
        self.assertEqual(report["verdict"], "hold")
        held = {c for c, r in results(report).items() if r == "hold"}
        self.assertEqual(held, {"brief", "owner", "rollout", "rollback", "eval-plan", "placeholders"})
        self.assertEqual(results(report)["certainty"], "note")
        self.assertEqual(results(report)["instructions"], "note")
        self.assertEqual(results(report)["guardrail"], "note")
        self.assertEqual(results(report)["baseline"], "note")

    def test_weak_spec_line_numbers_point_at_the_problem(self):
        doc = sa.load(WEAK)
        report = sa.audit(doc, AS_OF)
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
        self.assertEqual(finding(report, "brief")["result"], "pass")
        self.assertEqual(report["verdict"], "pass")

    def test_cost_none_on_a_model_call_holds_through_the_parser(self):
        report = run(BRIEF.replace("4,000", "none") + EVAL + ROLLOUT)
        self.assertEqual(report["verdict"], "hold")
        f = finding(report, "brief")
        self.assertIn("model call", f["message"])
        self.assertIn("Tokens per task", sa.parse_text(BRIEF).line(f["lines"][0]))

    def test_no_keyword_checks_of_its_own_for_brief_parts(self):
        # Brief completeness has one owner, landing_brief.py: with no brief, only the brief finding speaks for its parts.
        text = "# Spec\n\n## Goals\n\n- Improve chasing.\n\n## Non-goals\n\n- None.\n\nCost: $0.04 per task.\n"
        checks = {f["check"] for f in run(text)["findings"]}
        self.assertFalse(checks & {"problem", "good", "non-goals", "cost"}, checks)
        self.assertEqual(finding(run(text), "brief")["result"], "hold")

    def test_each_parser_problem_is_one_finding_on_its_line(self):
        text = BRIEF.replace("**Bar:** 70%", "**Bar:** much higher").replace("2027-06-30", "June") + EVAL + ROLLOUT
        held = [f for f in run(text)["findings"] if f["check"] == "brief"]
        self.assertEqual(len(held), 2)
        doc = sa.parse_text(text)
        self.assertEqual({doc.line(f["lines"][0]).split(":")[0].strip("-* ") for f in held}, {"Bar", "By"})

    def test_date_in_the_past_holds_only_with_as_of(self):
        text = BRIEF.replace("2027-06-30", "2026-01-31") + EVAL + ROLLOUT
        self.assertEqual(finding(run(text), "date")["result"], "hold")
        self.assertEqual(run(text)["verdict"], "hold")
        self.assertEqual(run(text, as_of=None)["verdict"], "pass")

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

    def test_stage_label_is_not_a_rollback_trigger(self):
        text = "# Spec\n\n## Rollback\n\nIn stage 2, turn off the flag.\n"
        self.assertEqual(finding(run(text), "rollback")["result"], "hold")
        text = "# Spec\n\n## Rollback\n\nIf acceptance drops below 70, turn off the flag.\n"
        self.assertEqual(finding(run(text), "rollback")["result"], "pass")

    def test_output_metric_holds_and_activity_metric_is_a_note(self):
        for metric, want in (("Features shipped", "hold"), ("Pull requests merged", "hold"), ("Drafts generated", "note"), ("Invoices paid by the due date", "pass")):
            report = run(BRIEF.replace("Invoices paid by the due date", metric) + EVAL + ROLLOUT)
            self.assertEqual(finding(report, "outcome")["result"], want, metric)

    def test_guardrail_needs_a_limit(self):
        self.assertEqual(finding(run("# Spec\n\nGuardrail: refund requests\n"), "guardrail")["result"], "note")
        self.assertEqual(finding(run("# Spec\n\nGuardrail: refund requests stay under 1%.\n"), "guardrail")["result"], "pass")
        self.assertEqual(finding(run("# Spec\n\n## Guardrails\n\n- Churn stays under 2% a month.\n"), "guardrail")["result"], "pass")

    def test_baseline_and_assumptions_are_notes_only(self):
        report = run(BRIEF + EVAL + ROLLOUT)
        self.assertEqual(finding(report, "baseline")["result"], "note")
        self.assertEqual(finding(report, "assumptions")["result"], "note")
        self.assertEqual(report["verdict"], "pass")
        report = run(BRIEF + EVAL + ROLLOUT + "\nToday 55% are paid by the due date.\n\n## Risks\n\n- Customers may mark chasers as spam.\n")
        self.assertEqual(finding(report, "baseline")["result"], "pass")
        self.assertEqual(finding(report, "assumptions")["result"], "note")
        report = run(BRIEF + EVAL + ROLLOUT + "\n## Risks\n\n- Customers may mark chasers as spam. Test: a 2-week pilot measures spam reports.\n")
        self.assertEqual(finding(report, "assumptions")["result"], "pass")

    def test_eval_plan_needs_cases_bar_and_when(self):
        f = finding(run("# Spec\n\nEach draft is a model call.\n\n## Eval plan\n\nWe will test it on 200 cases.\n"), "eval-plan")
        self.assertEqual(f["result"], "hold")
        self.assertIn("pass bar", f["message"])
        self.assertIn("time it runs", f["message"])

    def test_placeholders_are_found_on_every_line(self):
        text = "# Spec\n\nTBD\n\nTODO: add metric\n\nOwner: [insert name]\n\nBar: XX%\n"
        self.assertEqual(finding(run(text), "placeholders")["lines"], [3, 5, 7, 9])

    def test_bold_headings_from_exports_count_as_sections(self):
        self.assertEqual(finding(run("# Spec\n\n**Rollout**\n\n10% of accounts behind a flag.\n"), "rollout")["result"], "pass")

    def test_export_escapes_are_removed(self):
        self.assertEqual(finding(run("# Spec\n\n## Roll\\-out\n\n\\- 10% behind a flag.\n"), "rollout")["result"], "pass")

    def test_headings_inside_code_fences_are_ignored(self):
        self.assertEqual(finding(run("# Spec\n\n```\n## Rollout\n10% behind a flag\n```\n"), "rollout")["result"], "hold")

    def test_empty_and_oversized_input_is_refused(self):
        with self.assertRaises(sa.AuditError):
            sa.parse_text("   \n")
        with self.assertRaises(sa.AuditError):
            sa.parse_text("x" * (sa.MAX_CHARS + 1))


class RealRunRegressions(unittest.TestCase):
    """Patterns the first real run (2026-11-26, three internal specs) got wrong. The text here is invented, in the same shape."""

    def test_a_domain_ending_in_ai_is_not_an_ai_feature(self):
        report = run("# Spec\n\nThe page at acme.ai gets a new pricing table.\n")
        self.assertFalse(report["ai_feature"])

    def test_template_header_words_are_not_an_ai_feature(self):
        text = "# PRP: Pricing table\n# Product Requirements Prompt -- AI-optimized implementation blueprint\n\nA static table.\n"
        self.assertFalse(run(text)["ai_feature"])

    def test_real_ai_signals_still_count(self):
        for line in ("Drafts are AI-generated from job notes.", "The AI assistant replies.", "Each reply calls a model.", "Uses Claude to summarise."):
            self.assertTrue(run(f"# Spec\n\n{line}\n")["ai_feature"], line)

    def test_bold_heading_with_colon_is_a_section(self):
        text = "# Spec\n\n**Rollout:**\n\n- 10% of accounts behind a flag.\n"
        self.assertEqual(finding(run(text), "rollout")["result"], "pass")

    def test_gotchas_and_decisions_sections_count_as_assumptions(self):
        for head in ("Known gotchas", "Decisions for the owner"):
            text = f"# Spec\n\n## {head}\n\n- The tracker API pages at 50 items. Test: a spike before build.\n"
            self.assertEqual(finding(run(text), "assumptions")["result"], "pass", head)


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

    def test_example_notes_file_is_accepted(self):
        notes = json.loads((FIXTURES / "acme-good-notes.json").read_text(encoding="utf-8"))
        self.assertEqual([r["ok"] for r in sa.check_quotes(self.doc, notes)], [True, True])

    def test_model_arithmetic_in_a_note_is_rejected(self):
        # 20 is 90 minus 70: a figure the model worked out, which the quote does not hold.
        note = {"line": 47, "quote": "draft line-item acceptance below 70% for 3 days", "note": "The trigger sits 20 points under the eval pass bar."}
        row = sa.check_quotes(self.doc, [note])[0]
        self.assertFalse(row["ok"])
        self.assertIn("20", row["why"])

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
        self.assertTrue(out.strip().endswith("(6 hold, 5 note, 0 pass)"), out)

    def test_cli_json_and_quotes_exit_codes(self):
        script = str(SCRIPTS / "spec_audit.py")
        done = subprocess.run([sys.executable, script, "audit", str(GOOD), "--json", "--as-of", "2026-11-26"], capture_output=True, text=True, check=True)  # noqa: S603
        self.assertEqual(json.loads(done.stdout)["verdict"], "pass")
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.json"
            notes.write_text(json.dumps([{"line": 30, "quote": "Pass bar: 91%", "note": ""}]), encoding="utf-8")
            bad = subprocess.run([sys.executable, script, "quotes", str(GOOD), str(notes)], capture_output=True, text=True)  # noqa: S603
            self.assertEqual(bad.returncode, 1)
        held = subprocess.run([sys.executable, script, "audit", str(WEAK), "--fail-on-hold"], capture_output=True, text=True)  # noqa: S603
        self.assertEqual(held.returncode, 2)
        passed = subprocess.run([sys.executable, script, "audit", str(GOOD), "--fail-on-hold"], capture_output=True, text=True)  # noqa: S603
        self.assertEqual(passed.returncode, 0)

    def test_html_fixture_is_up_to_date(self):
        import make_html_fixture

        want = make_html_fixture.convert(GOOD.read_text(encoding="utf-8"))
        self.assertEqual(GOOD_HTML.read_text(encoding="utf-8"), want, "Run python3 evals/make_html_fixture.py")

    def test_text_command_numbers_every_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            sa.main(["text", str(WEAK)])
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), len(WEAK.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(lines[0].strip(), "1  # Smart invoice chasing")


class Vendored(unittest.TestCase):
    def test_every_vendored_file_matches_its_pinned_hash(self):
        pins = json.loads((SCRIPTS / "VENDORED.json").read_text(encoding="utf-8"))
        self.assertRegex(pins["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(pins["files"]["scripts/landing_brief.py"]["sha256"], LANDING_BRIEF_SHA256)
        for rel, pin in pins["files"].items():
            digest = hashlib.sha256((SCRIPTS.parent / rel).read_bytes()).hexdigest()
            self.assertEqual(digest, pin["sha256"], f"{rel} changed. Copy it again from the Leader Report at a pinned commit and update VENDORED.json.")

    def test_good_fixture_brief_is_accepted_by_landing_brief(self):
        brief = landing_brief.parse(GOOD.read_text(encoding="utf-8"))
        self.assertEqual(brief.line, "model call")
        self.assertEqual(brief.tokens_per_task, 9000)


class Sources(unittest.TestCase):
    def audit_cli(self, *args: str) -> dict:
        buf = io.StringIO()
        with redirect_stdout(buf):
            sa.main(["audit", *args, "--json", "--as-of", "2026-11-26"])
        return json.loads(buf.getvalue())

    def test_linear_project_is_read_with_the_leader_report_reader(self):
        report = self.audit_cli(str(FIXTURES / "acme-linear-project.json"), "--source", "linear")
        self.assertEqual(report["verdict"], "pass")
        src = report["source"]
        self.assertEqual((src["kind"], src["title"], src["updated_at"]), ("linear", "Quote drafts from job notes", "2026-11-20"))
        self.assertTrue(src["leader_report_reads_brief"])
        self.assertEqual(results(report), results(sa.audit(sa.load(GOOD), AS_OF)))

    def test_linear_list_needs_a_project_name(self):
        with self.assertRaises(SystemExit) as e:
            self.audit_cli(str(FIXTURES / "acme-linear-projects.json"), "--source", "linear")
        self.assertIn("--project", str(e.exception))
        weak = self.audit_cli(str(FIXTURES / "acme-linear-projects.json"), "--source", "linear", "--project", "invoice chasing")
        self.assertEqual(weak["verdict"], "hold")
        self.assertFalse(weak["source"]["leader_report_reads_brief"])

    def test_notion_page_takes_title_link_and_date_from_the_page_object(self):
        text, src = sources.load("notion", GOOD, FIXTURES / "acme-notion-page.json")
        self.assertEqual(src["title"], "Quote drafts from job notes")
        self.assertEqual(src["updated_at"], "2026-11-21")
        self.assertTrue(src["location"].startswith("https://www.notion.so/"))
        self.assertEqual(text, GOOD.read_text(encoding="utf-8"))

    def test_gdrive_file_takes_connector_field_names(self):
        _, src = sources.load("gdrive", GOOD_HTML, FIXTURES / "acme-gdrive-file.json")
        self.assertEqual((src["title"], src["updated_at"]), ("Quote drafts from job notes", "2026-11-22"))
        self.assertIn("docs.google.com", src["location"])
        report = self.audit_cli(str(GOOD_HTML), "--source", "gdrive", "--meta", str(FIXTURES / "acme-gdrive-file.json"))
        self.assertEqual(report["verdict"], "pass")

    def test_connector_json_with_content_field_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.json"
            page.write_text(json.dumps({"content": GOOD.read_text(encoding="utf-8")}), encoding="utf-8")
            self.assertEqual(sources.load("notion", page)[0], GOOD.read_text(encoding="utf-8"))
            page.write_text(json.dumps({"id": "x"}), encoding="utf-8")
            with self.assertRaises(sources.SourceError):
                sources.load("notion", page)


class LoopRecord(unittest.TestCase):
    def run_bet(self, folder: Path, spec: Path = GOOD, bet: str = "quote-drafting-assistant") -> dict:
        with redirect_stdout(io.StringIO()):
            sa.main(["audit", str(spec), "--as-of", "2026-11-26", "--bet", bet, "--landing", str(folder)])
        return json.loads((folder / f"{bet}.json").read_text(encoding="utf-8"))

    def test_new_record_gets_only_schema_bet_and_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = self.run_bet(Path(tmp))
        self.assertEqual(list(rec), ["schema", "bet", "spec"])
        self.assertEqual(rec["schema"], "landing-loop/1")
        self.assertEqual(rec["spec"]["brief_file"]["sha256"], hashlib.sha256(GOOD.read_bytes()).hexdigest())
        self.assertEqual(rec["spec"]["verdict"], "pass")

    def test_only_the_spec_key_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            other = {"schema": "landing-loop/1", "bet": "quote-drafting-assistant", "brief": {"path": "x", "sha256": "y"}, "portfolio": {"rank": 1}, "evals": {"tasks": 400}, "spec": {"old": True}}
            (folder / "quote-drafting-assistant.json").write_text(json.dumps(other), encoding="utf-8")
            rec = self.run_bet(folder, WEAK)
        for key in ("schema", "bet", "brief", "portfolio", "evals"):
            self.assertEqual(rec[key], other[key], key)
        self.assertEqual(rec["spec"]["verdict"], "hold")
        self.assertNotIn("old", rec["spec"])

    def test_every_figure_carries_value_unit_source_window_and_as_of(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self.run_bet(Path(tmp))["spec"]
        for f in [*spec["counts"].values(), spec["brief"]["bar"]]:
            self.assertEqual(set(f), {"value", "unit", "source", "window", "as_of"})
            self.assertEqual(set(f["window"]), {"from", "to"})
            self.assertTrue(f["source"])
        self.assertEqual((spec["brief"]["bar"]["value"], spec["brief"]["bar"]["unit"]), (60.0, "%"))
        self.assertIn("line 9", spec["brief"]["bar"]["source"])

    def test_cost_figures_are_left_to_cost_budget_check(self):
        # The contract gives tokens per task and price per token one owner: cost-budget-check.
        with tempfile.TemporaryDirectory() as tmp:
            spec = self.run_bet(Path(tmp))["spec"]
        self.assertNotIn("tokens_per_task", spec["brief"])
        self.assertNotIn("price_per_token", spec["brief"])

    def test_brief_completeness_is_the_parsers_call(self):
        report = run(BRIEF.replace("**Bar:** 70%", "**Bar:** much higher") + EVAL + ROLLOUT)
        self.assertIn("not one number", finding(report, "brief")["message"])
        self.assertNotIn("date", {f["check"] for f in report["findings"]})

    def test_no_status_word_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = json.dumps(self.run_bet(Path(tmp), WEAK)["spec"]).lower()
        for word in ('"landed"', '"watch"', '"stalled"', '"status"'):
            self.assertNotIn(word, text)

    def test_refuses_a_record_for_another_bet_or_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "quote-drafting-assistant.json").write_text(json.dumps({"schema": "landing-loop/1", "bet": "other"}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_bet(folder)
            (folder / "quote-drafting-assistant.json").write_text(json.dumps({"schema": "v0", "bet": "quote-drafting-assistant"}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_bet(folder)
            with self.assertRaises(loop.LoopError):
                loop.write(folder, "Bad Slug", {}, GOOD)

    def test_bet_needs_as_of(self):
        with self.assertRaises(SystemExit):
            sa.main(["audit", str(GOOD), "--bet", "x"])


class PythonFloor(unittest.TestCase):
    def test_the_entry_script_checks_the_version_before_anything_else(self):
        text = Path(sa.__file__).read_text(encoding="utf-8")
        body = text[text.index("from __future__ import annotations") :]
        guard = body.index("if sys.version_info < (3, 11):")
        self.assertIn("needs Python 3.11 or later; try python3.12", body)
        first_other_import = re.search(r"^(import (?!sys\b)|from (?!__future__))", body, re.M).start()
        self.assertLess(guard, first_other_import)


class Html(unittest.TestCase):
    def test_page_uses_the_leader_report_style_and_escapes_spec_text(self):
        doc = sa.parse_text("# Spec\n\nOwner: <script>alert(1)</script>\n\n## Rollout\n\nEveryone.\n", "spec.md")
        report = sa.audit(doc, AS_OF)
        out = render.page(report, doc.lines, {"kind": "file", "title": "<b>x</b>", "location": "spec.md"})
        self.assertIn("--brass:#E3A948", out)
        self.assertIn('font-family:"Geist"', out)
        self.assertNotIn("<script>alert", out)
        self.assertNotIn("<b>x</b>", out)
        self.assertNotIn("--landed)", out.split("</style>")[1])
        self.assertIn('class="vd hold"', out)
        css = out.split("</style>")[-2]
        self.assertIn(".vd.hold{color:var(--t1)}", css, "the verdict is a word in ink, not a filled chip")
        self.assertIn(".st.hold{color:var(--t1)}", css)
        self.assertNotIn("hold{color:var(--brass)", css, "a hold prints in ink; brass is for a person's call")
        self.assertIn("::selection{background:var(--t1)", css)
        self.assertIn(":focus-visible{outline-color:var(--t1)}", css)
        template = render.TEMPLATE.read_text(encoding="utf-8")
        style = template[template.index("<style>") + len("<style>") : template.index("</style>")]
        self.assertIn(render.floor_fonts(style), out, "the page carries the vendored template's whole stylesheet, its sizes raised to 11px")
        self.assertIn('<span translate="no">DACARD</span>', out)
        for word in ("hold", "note", "pass"):
            self.assertIn(f'<span class="st {word}">{word}</span>', out)

    def test_out_writes_html_and_markdown_twin(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                sa.main(["audit", str(WEAK), "--as-of", "2026-11-26", "--out", tmp])
            page = (Path(tmp) / "audit.html").read_text(encoding="utf-8")
            md = (Path(tmp) / "audit.md").read_text(encoding="utf-8")
            data = json.loads((Path(tmp) / "audit.json").read_text(encoding="utf-8"))
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("The lines the holds cite", page)
        self.assertIn("## Spec audit: **hold**", md)
        self.assertEqual(data["verdict"], "hold")
        for f in data["findings"]:
            self.assertIn(f["check"], md)


class Page(unittest.TestCase):
    """The sample page follows the Landing Loop sample anatomy and draws in its one visual family."""

    def setUp(self):
        self.page = (ROOT / "examples" / "acme" / "spec-auditor.html").read_text(encoding="utf-8")
        self.body = self.page.split("</style>", 1)[1]
        self.report = sa.audit(sa.load(ROOT / "examples/acme/specs/quote-drafting.md"), datetime.date(2026, 8, 3), sa.load(ROOT / "examples/acme/briefs/quote-drafting.md"))

    def test_the_page_follows_the_sample_anatomy(self):
        body = self.body.split('<main class="solo">', 1)[1]
        order = ['class="sk-hdr"', "<h1>", 'class="vd hold"', 'role="img"', "What to do next", "What stops the build plan", "The lines the holds cite", "For your engineers"]
        at = [body.index(x) for x in order]
        self.assertEqual(at, sorted(at))
        self.assertEqual(body.count("<h1>"), 1)
        self.assertIn("<h1>Hold: two checks stop this build plan.</h1>", body)
        self.assertIn("<span>Spec auditor</span><span>Audit 2026-08-03</span><span>v" + sa.VERSION + "</span>", body, "the shared header")
        self.assertIn('<span class="o"><i>Decides</i>Head of Product, Quoting squad</span><span class="d"><i>When</i>before build starts</span>', body)
        self.assertEqual(body.count('<div class="next">'), 1)
        self.assertIn("<details><summary>11 checks pass</summary>", body, "the passes fold")
        self.assertNotIn("Book a call", body, "a sample is the skill's own output: no call to action")

    def test_illustrative_tag_is_blue(self):
        self.assertIn('<span class="sk-ill">Illustrative</span>', self.body)
        self.assertIn(":root{--ill:#74A5DA}", self.page)

    def test_the_visual_draws_only_figures_the_page_prints(self):
        self.assertEqual(svgkit.unprinted(self.page), [])
        self.assertEqual(len(svgkit.svgs_in(svgkit.frames_in(self.page)[0])), 1, "one share bar; the check rows have no picture")

    def test_the_scorecard_is_one_frame_with_one_row_per_check_holds_first(self):
        frames = svgkit.frames_in(self.page)
        self.assertEqual(len(frames), 1, "one frame per visual")
        frame = frames[0]
        c = self.report["counts"]
        self.assertEqual((c["pass"], c["hold"], c["note"]), (11, 2, 1))
        self.assertEqual(frame.count('<div class="sc-r">'), len(self.report["findings"]) + 1, "the share row, then one row per check")
        self.assertIn('<span class="sc-n">All checks</span><span class="sc-p"><svg class="sc-sh"', frame)
        self.assertIn('<span class="sc-l"><b>11 of 14 pass</b></span>', frame)
        words = re.findall(r'<span class="sc-s"><span class="(sc-w(?: ink)?)">(\w+)</span></span>', frame)[1:]
        self.assertEqual([w for _, w in words], ["hold", "hold", "note"] + ["pass"] * 11, "holds first")
        self.assertEqual({cls for cls, w in words if w == "hold"}, {"sc-w ink"})
        self.assertEqual({cls for cls, w in words if w != "hold"}, {"sc-w"})
        self.assertIn('<span class="sc-n">When to undo it</span><span class="sc-p"></span><span class="sc-l"><b>L48, L50</b></span>', frame)
        self.assertIn('<span class="sc-n">Quality tests</span><span class="sc-p"></span><span class="sc-l"><b>L37, L39, L40</b></span>', frame)
        for f in self.report["findings"]:
            where = render.refs(f["lines"], f.get("file", "spec")) if f["lines"] else "whole plan"
            self.assertIn(f'<span class="sc-l"><b>{where}</b></span>', frame, f["check"])

    def test_no_text_inside_a_picture_and_no_picture_scales(self):
        self.assertEqual(svgkit.svgs_with_text(self.page), [])
        self.assertEqual(svgkit.scaled_svgs_in(self.page), [])

    def test_labels_render_12px_and_names_14px(self):
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertEqual(set(svgkit.font_sizes(css)), {"var(--sc-m)", "var(--sc-n)"})
        self.assertIn("--sc-m:calc(12px / var(--sc-z))", css)
        self.assertIn("--sc-n:calc(14px / var(--sc-z))", css)
        self.assertIn(".scg{--sc-z:1;", css, "a sample page has no zoom")

    def test_no_box_inside_the_scorecard_and_no_overlap(self):
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertEqual(svgkit.boxes_in_frames(self.page, css), [])
        self.assertNotIn('class="chip"', self.page.split("For your engineers", 1)[0])
        self.assertNotIn("position:absolute", svgkit.SCORECARD_CSS)

    def test_no_legacy_svgkit_primitive_draws_on_the_page(self):
        import warnings

        self.assertEqual(svgkit.legacy_in(self.page), [])
        doc = sa.load(ROOT / "examples/acme/specs/quote-drafting.md")
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            render.page(self.report, doc.lines, {"kind": "file", "location": "spec.md"}, illustrative=True)

    def test_no_status_colour(self):
        for word in ("landed", "stalled", "watch"):
            self.assertNotIn(f"var(--{word})", self.body)
            self.assertNotIn(f'class="st {word}"', self.body)

    def test_the_scorecard_states_its_answer(self):
        labels = re.findall(r'role="img" aria-label="([^"]+)"', self.page)
        self.assertEqual(labels, [render.verdict_line(self.report)])
        self.assertEqual(labels[0], "Hold: two checks stop this build plan. Set the number that triggers an undo and complete the quality test plan before build starts.")

    def test_public_copy_uses_plain_words(self):
        public = self.body.split("For your engineers", 1)[0]
        for svg in svgkit.svgs_in(public):
            public = public.replace(svg, " ")
        public = re.sub(r'<span class="sc-q">.*?</span>|<div class="cite">.*?</div>|<dd>[^<]*<span class="t3 mono">', " ", public)
        text = html_lib.unescape(re.sub(r"<[^>]+>", " ", public)).lower()
        for word in ("rollback", "rollout", "eval plan", " evals", "eval-plan", "the bar", "cohort", "spec's", ".json", "--fail"):
            self.assertNotIn(word, text, word)
        self.assertIn("<b>landing brief</b>, a one-page plan", self.body)
        md = (ROOT / "examples" / "acme" / "spec-auditor.md").read_text(encoding="utf-8").split("For your engineers", 1)[0].lower()
        for word in ("rollback", "eval plan", "eval-plan", "the bar"):
            self.assertNotIn(word, md, word)

    def test_no_text_smaller_than_11px(self):
        css = "".join(re.findall(r"<style>(.*?)</style>", self.page, re.S))
        decls = re.findall(r"font(?:-size)?:[^;}]*", css)
        self.assertTrue(decls)
        sizes = [float(n) for d in decls for n in re.findall(r"(?<![/\d.])(\d+(?:\.\d+)?)px", d)]
        self.assertGreaterEqual(min(sizes), 11, "a font size below 11px")
        self.assertNotRegex(self.page, r'font-size="(\d|10)(\.\d+)?"', "an SVG label below 11px")
        template = (SCRIPTS.parent / "assets" / "template.html").read_text(encoding="utf-8")
        self.assertIn("font:400 10px/16px var(--mono)", template, "the template stays as vendored; the page raises its sizes")

    def test_header_prints_the_plain_name_and_the_fold_the_code_name(self):
        header = re.search(r'<header class="sk-hdr">.*?</header>', self.page, re.S).group(0)
        self.assertNotIn("spec-auditor", header)
        public = self.body.split("<summary>For your engineers</summary>", 1)
        self.assertNotIn("spec-auditor", public[0])
        self.assertIn(f"Skill: <code>spec-auditor</code> {sa.VERSION}.", public[1])
        self.assertIn("<title>Spec auditor: Build plan: Quote drafting assistant</title>", self.page)

    def test_no_internal_words_in_public_copy(self):
        banned = re.compile(r"\b(records?|bets?|the bar|PRDs?|ARR|tokens?)\b", re.I)
        public = re.sub(r"<details><summary>For your engineers</summary>.*?</details>", " ", self.body, flags=re.S)
        self.assertIsNone(banned.search(svgkit.page_text(public)), "internal word on the page")
        for svg in svgkit.visuals_in(self.page):
            self.assertIsNone(banned.search(" ".join(svgkit.texts_in(svg))), "internal word in the picture")
        self.assertIn("Build plan: Quote drafting assistant. The <b>build plan</b>", self.body)
        md = (ROOT / "examples" / "acme" / "spec-auditor.md").read_text(encoding="utf-8").split("For your engineers", 1)[0]
        self.assertIsNone(banned.search(md), "internal word in the Markdown twin")

    def test_the_title_reads_build_plan(self):
        self.assertEqual(render.plain_title("PRD: Quote drafting assistant"), "Build plan: Quote drafting assistant")

    def test_svgkit_matches_its_landing_loop_pin(self):
        pin = json.loads((SCRIPTS / "VENDORED.json").read_text(encoding="utf-8"))["landing-loop"]
        self.assertEqual(pin["commit"], "78784efd2ecd5282f6ec264e545ce2075e459be2")
        self.assertEqual(set(pin["files"]), {"scripts/vendor/svgkit.py"})
        for rel, info in pin["files"].items():
            digest = hashlib.sha256((SCRIPTS.parent / rel).read_bytes()).hexdigest()
            self.assertEqual(digest, info["sha256"], f"{rel} changed. Copy it again from landing-loop at the pinned commit and update VENDORED.json.")


class Sample(unittest.TestCase):
    """The committed sample for the /skills page is what the README's command makes, byte for byte."""

    def command(self) -> list[str]:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme[readme.index("## Sample") :]
        block = section[section.index("```bash") + len("```bash") : section.index("```", section.index("```bash") + 7)]
        line = block.strip()
        self.assertNotIn("\n", line, "the Sample command must be one line, so a chain script can call it")
        return line.split()

    def test_readme_command_reproduces_the_committed_sample(self):
        args = self.command()
        self.assertEqual(args[:2], ["python3", "skills/spec-auditor/scripts/spec_audit.py"])
        committed = {rel: (ROOT / rel).read_bytes() for rel in ("examples/acme/spec-auditor.html", "examples/acme/spec-auditor.md", "examples/acme/landing/quote-drafting.json")}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copytree(ROOT / "skills", work / "skills")
            shutil.copytree(ROOT / "examples" / "acme" / "briefs", work / "examples" / "acme" / "briefs")
            shutil.copytree(ROOT / "examples" / "acme" / "specs", work / "examples" / "acme" / "specs")
            subprocess.run([sys.executable, *args[1:]], cwd=work, check=True, capture_output=True, text=True)  # noqa: S603
            for rel, want in committed.items():
                self.assertEqual((work / rel).read_bytes(), want, f"{rel} differs. Run the README Sample command and commit the result.")

    def test_sample_briefs_are_the_canonical_copies(self):
        # The canonical briefs live in the landing-loop repository; this checks the copies still parse and the bet is there.
        brief = landing_brief.parse((ROOT / "examples/acme/briefs/quote-drafting.md").read_text(encoding="utf-8"))
        self.assertEqual(brief.metric, "Quote draft acceptance rate")

    def test_sample_record_holds_only_the_spec_key(self):
        rec = json.loads((ROOT / "examples/acme/landing/quote-drafting.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(rec), ["bet", "schema", "spec"])
        self.assertEqual(rec["spec"]["verdict"], "hold")
        self.assertEqual({h["check"] for h in rec["spec"]["holds"]}, {"rollback", "eval-plan"})


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
