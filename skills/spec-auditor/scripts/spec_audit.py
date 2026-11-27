#!/usr/bin/env python3
"""Audit a PRD or spec against its landing brief and a checklist, and give a pass or hold verdict.

Usage:
  python3 scripts/spec_audit.py audit spec.md                       # findings with line numbers, then the verdict
  python3 scripts/spec_audit.py audit spec.md --as-of 2026-11-26    # also hold a definition-of-good date in the past
  python3 scripts/spec_audit.py audit spec.html --json              # the same as JSON
  python3 scripts/spec_audit.py audit spec.md --format md           # as Markdown, to paste into a review
  python3 scripts/spec_audit.py audit spec.md --fail-on-hold        # exit 2 on hold, to gate a pull request
  python3 scripts/spec_audit.py text spec.html                      # the numbered text every line number refers to
  python3 scripts/spec_audit.py quotes spec.md notes.json           # check the model's quotes against the spec

Input: Markdown (.md), plain text (.txt), or an HTML export (.html, .htm) such as Google Docs "Web page" or Notion
"HTML". HTML is turned into plain lines first; every line number refers to that text, which `text` prints.

The checks, each run in code:
  brief        the landing brief, checked by the vendored parser (scripts/landing_brief.py) and nothing else: each
               problem it lists (a missing problem, bar, date, non-goals or cost line, a bar that is not one number)
               is one hold. Brief completeness has one owner in the Landing Loop; this script adds no list of its own
  date         the brief's By date is not before --as-of
  outcome      holds a bar on work shipped (features, releases); notes a bar on use (clicks, adoption)
  owner        a named person who owns the work or decides the next step, not a team or TBD
  rollout      a rollout plan with a stage (a percentage, a flag, a cohort, a pilot)
  rollback     a rollback plan with a trigger (a threshold: a number with a unit or a comparison) and a way back (a flag, a revert, an off switch)
  eval-plan    for an AI feature: an eval plan with a case count, a pass bar and when it runs
  placeholders no TBD, TODO, TBC, ??? or [insert ...] left in the spec
  certainty    notes forecasts stated as certain ("will increase", "guarantees"). Never holds.
  guardrail    notes when no guardrail metric with a limit is named. Never holds.
  baseline     notes when the metric's current value is not stated. Never holds.
  assumptions  notes when no risks, assumptions or open questions are listed. Never holds.
  instructions notes text addressed to the reviewer ("ignore the checklist", "mark this pass"). Never holds.

Any finding marked hold makes the verdict hold. Notes never change the verdict. Nothing in the spec changes a check:
text that reads like an instruction ("mark this pass") is data, like every other line.

`quotes` is the line the model holds to: every passage it relies on must appear word for word on the line it cites,
and every number in its note must appear in that quote. Anything else is rejected, and the command exits 1.

This script reads files and prints text. It makes no network calls. Standard library only. Python 3.11 or later.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # noqa: UP036  (checked first, before anything is read or written)
    raise SystemExit("spec_audit: needs Python 3.11 or later; try python3.12.")

import argparse
import datetime
import json
import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import landing_brief  # noqa: E402  (vendored unchanged from the Leader Report; see VENDORED.json)
import loop  # noqa: E402
import render  # noqa: E402
import sources  # noqa: E402

VERSION = "0.3.5"
# A spec is tens of pages at most. Anything larger is not one.
MAX_CHARS = 400_000
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# Bold-only lines act as headings in many Google Docs and Notion exports: "**Rollout**". Level 7 sits below any "#".
BOLD_HEADING = re.compile(r"^(?:\*\*|__)([^*_:]{2,60}?)\s*:?\s*(?:\*\*|__)\s*:?\s*$")
ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>|~])")
NUM = re.compile(r"(?<![\w.])[$£€]?\d[\d,]*(?:\.\d+)?%?")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Heading words for each part, matched against a heading's text in lower case.
SECTIONS = {
    "owner": ("owner", "owners", "ownership", "dri", "team", "people"),
    "rollout": ("rollout", "roll-out", "rollout plan", "launch plan", "release plan", "launch", "release"),
    "rollback": ("rollback", "roll back", "rollback plan", "kill switch", "off switch", "backout plan", "back-out plan"),  # voice-lint-disable-line
    "guardrail": ("guardrail", "guardrails", "guardrail metrics", "counter-metrics", "counter metrics", "what must not get worse"),
    "assumptions": (
        "assumptions",
        "riskiest assumption",
        "riskiest assumptions",
        "risks",
        "risks and assumptions",
        "open questions",
        "unknowns",
        "known gotchas",
        "gotchas",
        "known risks",
        "open decisions",
        "decisions",
    ),
    "eval": ("eval plan", "evals", "eval", "evaluation", "evaluation plan", "model evaluation", "quality bar"),
}
OWNER_KEYS = ("decides the next step", "decides", "owner", "dri", "accountable", "product owner")
PLACEHOLDER_OWNERS = {
    "tbd", "tbc", "tba", "n/a", "na", "none", "?", "todo", "the team", "team", "everyone", "product", "engineering",
    "product team", "engineering team", "design", "leadership", "us", "we",
}  # fmt: skip
PLACEHOLDER = re.compile(r"\b(TBD|TBC|TBA|TODO|FIXME)\b|\?\?\?|\[(?:insert|add|fill)[^\]]*\]|\bXX+%?", re.I)
STAGE = re.compile(r"\d+\s?%|\bflag\b|feature flag|cohort|pilot|internal|staff|beta|waitlist|staged|canary|percent|wave|phase", re.I)
WAY_BACK = re.compile(r"\bflag\b|revert|kill switch|off switch|switch off|turn off|turned off|disable|roll back to|previous version|fallback", re.I)  # voice-lint-disable-line
ROLLBACK_WORDS = re.compile(r"roll ?back|kill switch|off switch|back ?out", re.I)  # voice-lint-disable-line
CASES = re.compile(
    r"\b\d[\d,]*\s+(?:\w+\s+){0,3}(?:cases|examples|samples|items|conversations|prompts|transcripts|quotes|invoices|tasks|records|notes|jobs|emails|messages|documents|tickets|questions|pairs)\b", re.I
)
PASS_BAR = re.compile(r"\d+(?:\.\d+)?\s?%|\b\d+\s?(?:of|/)\s?\d+\b", re.I)
WHEN = re.compile(
    r"before (?:launch|release|each|every|rollout|ship)|every (?:change|release|merge|deploy|pull request|prompt change|model change|week|night)"
    r"|\bci\b|nightly|weekly|daily|on each|per release|pre-launch",
    re.I,
)
# Signs that the work itself calls a model. Bare "AI" and "prompt" are left out: the real run showed them in domains
# (dacard.ai), in template headers ("AI-optimized", "Product Requirements Prompt") and in prose about the market.
AI_WORDS = re.compile(
    r"\b(?:LLMs?|large language models?|language models?|model calls?|calls? (?:a|the) model|model outputs?|system prompts?|prompt templates?|prompt changes?"
    r"|AI (?:assistant|feature|agent|model|summar\w*|draft\w*)|AI-(?:generated|drafted|written)|generative|GPT-?\d*|Claude|Gemini|embeddings?|fine-tun\w+|inference)\b",
    re.I,
)
DOMAIN = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.ai\b", re.I)
CERTAIN = re.compile(r"\bwill (?:increase|decrease|reduce|cut|double|triple|drive|grow|improve|lift|boost|eliminate)\b|\bguarantee[sd]?\b|\bdefinitely\b|\bcertain to\b", re.I)
# Text that reads as an instruction to whoever, or whatever, reviews the spec. Flagged as a note; it changes nothing.
INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|skip|override)\b.{0,40}\b(?:rules?|checklist|checks?|instructions?|audit|above|previous)\b"
    r"|\bmark (?:this|the spec|it)\b.{0,20}\b(?:pass|passed|approved|landed)\b|\b(?:system prompt|you are now|as an ai)\b",
    re.I,
)
# A rollback trigger is a threshold: a number with a unit or a comparison, not a stage label such as "Stage 2".
TRIGGER = re.compile(
    r"\d[\d,.]*\s?(?:%|ms|s\b|seconds?|minutes?|hours?|days?|errors?|complaints?|tickets?|incidents?|x\b)"
    r"|(?:below|above|over|under|pass(?:es)?|reach(?:es)?|hits?|more than|less than|fewer than|exceeds?|drops? (?:below|under)|rises? (?:above|over)|>|<|>=|<=)\s*[$£€]?\d",
    re.I,
)
# Metrics that count work done, not what changed for the customer. A bar on one of these cannot show the work landed.
OUTPUT_METRIC = re.compile(
    r"\b(?:features?|tickets?|stories|story points|epics?|releases?|launch(?:es)?|pull requests?|prs?|commits?|deploys?|deployments?|velocity|throughput)\b"
    r"|\b(?:shipped|launched|delivered|released|completed|built|rolled out)\b",
    re.I,
)
# Metrics that count use, not the outcome use was meant to cause. Fine as a leading signal, weak as the bar.
ACTIVITY_METRIC = re.compile(r"\b(?:generated|created|clicks?|page ?views?|sessions?|logins?|sign-?ins?|opens?|impressions?|tried|used|usage|adoption|active users|DAU|MAU|WAU)\b", re.I)
GUARDRAIL_KEYS = ("guardrail", "guardrails", "counter-metric", "counter metric", "must not get worse")
BASELINE = re.compile(r"\b(?:today|currently|baseline|at present|as of now|now at|is now)\b[^.]{0,80}?\d|\d[^.]{0,60}\b(?:today|currently|baseline)\b", re.I)
TESTED = re.compile(r"\b(?:test|tested|tests|validate[ds]?|interviews?|prototype|experiment|measure[sd]?|pilot|spike|check(?:ed)? by)\b", re.I)


class AuditError(ValueError):
    """A file that cannot be audited."""


@dataclass
class Finding:
    check: str
    result: str  # "pass", "hold" or "note"
    message: str
    lines: list[int] = field(default_factory=list)
    fix: str = ""
    file: str = "spec"  # which file the lines are in: "spec", or "brief" when --brief names a separate brief


@dataclass
class Doc:
    path: str
    lines: list[str]  # read through line(n), which is 1-indexed
    headings: list[tuple[int, int, str]]  # (line number, level, text in lower case)

    def line(self, n: int) -> str:
        return self.lines[n - 1]

    def section(self, names: tuple[str, ...], prefix: bool = False) -> tuple[int, list[int]] | None:
        """(heading line, non-blank body line numbers) for the first heading whose text is one of names, else None.
        With prefix, a heading that starts with a name and a space also counts ("Decisions for the owner")."""
        for i, (n, level, text) in enumerate(self.headings):
            clean = re.sub(r"^[\d.]+\s*", "", text).strip(" :")
            if clean in names or (prefix and any(clean.startswith(x + " ") for x in names)):
                end = len(self.lines) + 1
                for m, lv, _ in self.headings[i + 1 :]:
                    if lv <= level:
                        end = m
                        break
                return n, [k for k in range(n + 1, end) if self.line(k).strip()]
        return None


class _Text(HTMLParser):
    """HTML to plain lines: headings keep a Markdown marker, list items a dash, block elements a line break."""

    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "section", "article", "header", "footer", "blockquote", "pre"}
    SKIP = {"script", "style", "head", "title", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip += 1
            return
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(text: str) -> str:
    parser = _Text()
    parser.feed(text)
    parser.close()
    out: list[str] = []
    for line in (re.sub(r"\s+", " ", x).strip() for x in "".join(parser.out).splitlines()):
        if line or (out and out[-1]):  # collapse runs of blank lines to one
            out.append(line)
    return "\n".join(out).strip() + "\n"


def normalise(line: str) -> str:
    """One line as a person reads it: export escapes removed ("\\-" to "-"), non-breaking spaces made plain."""
    return ESCAPED.sub(r"\1", line.replace(" ", " ").replace("​", "")).rstrip()


def load(path: Path) -> Doc:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise AuditError(f"cannot read {path} ({e}). Export the spec as Markdown, plain text or HTML, in UTF-8.") from None
    return parse_text(raw, str(path), is_html=path.suffix.lower() in (".html", ".htm"))


def parse_text(raw: str, name: str = "<text>", is_html: bool = False) -> Doc:
    if not raw.strip():
        raise AuditError(f"{name} is empty.")
    if len(raw) > MAX_CHARS:
        raise AuditError(f"{name} is over {MAX_CHARS:,} characters, so it is not one spec. Audit one document at a time.")
    if is_html or re.match(r"\s*(?:<!doctype html|<html)", raw, re.I):
        raw = html_to_text(raw)
    lines = [normalise(x) for x in raw.splitlines()]
    headings: list[tuple[int, int, str]] = []
    fence = False
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = HEADING.match(s)
        if m:
            headings.append((n, len(m.group(1)), m.group(2).strip("*_ ").lower()))
            continue
        b = BOLD_HEADING.match(s)
        if b:
            headings.append((n, 7, b.group(1).strip().lower()))
    return Doc(path=name, lines=lines, headings=headings)


def brief_fields(doc: Doc) -> tuple[int | None, dict[str, tuple[int, str]]]:
    """The landing brief's heading line, and each key it holds as (line number, value), read with the brief's own rules."""
    start = next(((n, lv) for n, lv, text in doc.headings if text == "landing brief"), None)
    if start is None:
        return None, {}
    head, level = start
    end = next((n for n, lv, _ in doc.headings if n > head and lv <= level), len(doc.lines) + 1)
    found: dict[str, tuple[int, str]] = {}
    for n in range(head + 1, end):
        m = landing_brief.LINE.match(doc.line(n).strip())
        key = landing_brief.KEYS.get(m.group(1).strip().lower()) if m else None
        if key and key not in found:
            found[key] = (n, m.group(2).strip().strip("*_").strip())
    return head, found


def key_lines(doc: Doc, keys: tuple[str, ...]) -> list[tuple[int, str, str]]:
    """Every "Key: value" line in the spec whose key is one of keys, as (line number, key, value)."""
    out = []
    for n, line in enumerate(doc.lines, 1):
        m = landing_brief.LINE.match(line.strip())
        if m and m.group(1).strip().lower() in keys:
            out.append((n, m.group(1).strip().lower(), m.group(2).strip().strip("*_").strip()))
    return out


def body_text(doc: Doc, lines: list[int]) -> str:
    return " ".join(doc.line(n) for n in lines)


def is_ai_feature(doc: Doc, brief: dict[str, tuple[int, str]]) -> tuple[bool, list[int]]:
    """True when the brief's line is a model call, or (with no line stated) the spec names a model, a prompt or an AI feature."""
    if "line" in brief:
        n, value = brief["line"]
        if value.lower().startswith("model call"):
            return True, [n]
        if value.lower().startswith("fixed code"):
            return False, [n]
    hits = [n for n, line in enumerate(doc.lines, 1) if AI_WORDS.search(DOMAIN.sub("", line))]
    return bool(hits), hits[:5]


def check_brief(doc: Doc, start: int | None, fields: dict[str, tuple[int, str]]) -> list[Finding]:
    """Brief completeness is landing_brief.parse's call (Landing Loop contract, one owner per figure). Each problem the
    parser lists becomes one finding, cited to the line of the part it names when that part is in the brief."""
    if start is None:
        return [Finding("brief", "hold", 'There is no "Landing brief" block.', [], 'Add a "## Landing brief" section with the five parts (see references/checklist.md).')]
    try:
        landing_brief.parse("\n".join(doc.lines))
    except landing_brief.BriefError as e:
        out = []
        problems = [x.strip() for x in str(e).splitlines()[1:] if x.strip()] or [str(e)]
        for problem in problems:
            named = [n for key, (n, _) in fields.items() if re.search(rf"\b{re.escape(key.replace('_', ' '))}\b", problem, re.I)]
            out.append(Finding("brief", "hold", f"Landing brief: {problem}", named[:1] or [start], "Fix it in the brief (see references/checklist.md)."))
        return out
    return [Finding("brief", "pass", "The landing brief parses, with every part present.", [start, *sorted(n for n, _ in fields.values())][:1])]


def check_date(parsed: landing_brief.Brief, fields: dict[str, tuple[int, str]], as_of: datetime.date | None) -> Finding:
    lines = [fields["by"][0]] if "by" in fields else []
    if as_of and datetime.date.fromisoformat(parsed.by) < as_of:
        return Finding("date", "hold", f"The brief's date {parsed.by} is before {as_of.isoformat()}, so the bar cannot be met in time.", lines, "Set a date that is still ahead.")
    return Finding("date", "pass", f"The brief's date, {parsed.by}, is still ahead." if as_of else f"The brief's date is {parsed.by}; pass --as-of to check it is ahead.", lines)


def check_owner(doc: Doc, brief: dict[str, tuple[int, str]], brief_file: str = "spec") -> Finding:
    candidates = [brief["decides"]] if "decides" in brief else []
    candidates += [(n, v) for n, _, v in key_lines(doc, OWNER_KEYS) if (n, v) not in candidates]
    named = [(n, v) for n, v in candidates if v.split(",")[0].strip().strip(".").lower() not in PLACEHOLDER_OWNERS and not PLACEHOLDER.search(v)]
    if named:
        n, v = named[0]
        return Finding("owner", "pass", f"Owner named: {v[:60]}.", [n], file=brief_file if "decides" in brief and brief["decides"] == (n, v) else "spec")
    if candidates:
        first = candidates[0]
        where = brief_file if "decides" in brief and brief["decides"] == first else "spec"
        return Finding("owner", "hold", f'The owner is "{first[1][:40]}", not a named person.', [first[0]], "Name one person who decides the next step.", file=where)
    sec = doc.section(SECTIONS["owner"])
    return Finding("owner", "hold", "No named owner.", [sec[0]] if sec else [], 'Add "Decides the next step: <name>, <role>" to the landing brief.')


def check_rollout(doc: Doc) -> Finding:
    sec = doc.section(SECTIONS["rollout"])
    if sec is None or not sec[1]:
        return Finding("rollout", "hold", "No rollout plan.", [sec[0]] if sec else [], "Say who gets it first, in what stages, and what moves it to the next stage.")
    staged = [n for n in sec[1] if STAGE.search(doc.line(n))]
    if not staged:
        return Finding("rollout", "hold", "The rollout plan names no stage.", [sec[0], *sec[1][:3]], "Name the stages: a percentage, a flag, a cohort or a pilot group.")
    return Finding("rollout", "pass", f"Rollout plan with {len(staged)} staged line{'s' if len(staged) != 1 else ''}.", [sec[0], *staged[:4]])


def check_rollback(doc: Doc) -> Finding:
    sec = doc.section(SECTIONS["rollback"])
    if sec and sec[1]:
        head, lines = [sec[0]], sec[1]
    else:
        head, lines = [], [n for n, line in enumerate(doc.lines, 1) if ROLLBACK_WORDS.search(line)]
    if not lines:
        return Finding("rollback", "hold", "No rollback plan.", [], "Say what number triggers a rollback, and how it is done (a flag, a revert, an off switch).")
    trigger = [n for n in lines if TRIGGER.search(ISO_DATE.sub("", doc.line(n)))]
    way = [n for n in lines if WAY_BACK.search(doc.line(n))]
    missing = [x for x, ok in (("trigger threshold", trigger), ("way back", way)) if not ok]
    if missing:
        return Finding(
            "rollback", "hold", f"The rollback plan has no {' and no '.join(missing)}.", [*head, *lines[:3]], "Say what number triggers it (such as an error rate over 2%) and how it is done."
        )
    return Finding("rollback", "pass", "Rollback plan with a trigger and a way back.", sorted({*head, *trigger[:2], *way[:2]}))


def check_eval(doc: Doc, ai: bool, ai_lines: list[int]) -> Finding:
    if not ai:
        return Finding("eval-plan", "pass", "Not an AI feature, so no eval plan is needed.", ai_lines[:1])
    sec = doc.section(SECTIONS["eval"])
    if sec is None or not sec[1]:
        return Finding("eval-plan", "hold", "This is an AI feature with no eval plan.", [sec[0]] if sec else ai_lines[:3], "Add an eval plan: how many cases, the pass bar, and when it runs.")
    body = sec[1]
    cases = [n for n in body if CASES.search(doc.line(n))]
    bar = [n for n in body if PASS_BAR.search(doc.line(n))]
    when = [n for n in body if WHEN.search(doc.line(n))]
    missing = [x for x, ok in (("case count", cases), ("pass bar", bar), ("time it runs", when)) if not ok]
    if missing:
        return Finding("eval-plan", "hold", f"The eval plan has no {', no '.join(missing)}.", [sec[0], *body[:3]], "State the number of cases, the pass bar as a number, and when the evals run.")
    return Finding("eval-plan", "pass", "Eval plan with a case count, a pass bar and when it runs.", sorted({sec[0], cases[0], bar[0], when[0]}))


def check_placeholders(doc: Doc) -> Finding:
    hits = [n for n, line in enumerate(doc.lines, 1) if PLACEHOLDER.search(line)]
    if hits:
        lines_hold = "1 line still holds" if len(hits) == 1 else f"{len(hits)} lines still hold"
        return Finding("placeholders", "hold", f"{lines_hold} a placeholder (TBD, TODO, ??? or similar).", hits, "Fill each one, or move it to an open question with an owner and a date.")
    return Finding("placeholders", "pass", "No placeholders left.")


def check_certainty(doc: Doc) -> Finding:
    hits = [n for n, line in enumerate(doc.lines, 1) if CERTAIN.search(line)]
    if hits:
        return Finding("certainty", "note", "Forecasts stated as certain. A spec can set a bar; it cannot promise the result.", hits, 'Write "the bar is", not "this will increase".')
    return Finding("certainty", "pass", "No forecast stated as certain.")


def check_outcome(doc: Doc, brief: dict[str, tuple[int, str]]) -> Finding:
    if "metric" not in brief:
        return Finding("outcome", "pass", "No brief metric to classify; the brief finding holds on that.")
    n, metric = brief["metric"]
    if OUTPUT_METRIC.search(metric):
        return Finding("outcome", "hold", f'The metric "{metric[:60]}" counts work shipped, not what changed for the customer.', [n], "Pick the customer or business result the work is meant to move.")
    if ACTIVITY_METRIC.search(metric):
        return Finding(
            "outcome", "note", f'The metric "{metric[:60]}" counts use. It can rise while the outcome does not.', [n], "Keep it as a leading signal; make the bar the result use is meant to cause."
        )
    return Finding("outcome", "pass", "The metric is a result, not a count of work or use.", [n])


def check_guardrail(doc: Doc) -> Finding:
    found = key_lines(doc, GUARDRAIL_KEYS)
    sec = doc.section(SECTIONS["guardrail"])
    lines = [n for n, _, v in found if v] + (sec[1] if sec else [])
    with_num = [n for n in lines if NUM.search(ISO_DATE.sub("", doc.line(n)))]
    if with_num:
        return Finding("guardrail", "pass", "A guardrail metric with a limit is named.", sorted({*([sec[0]] if sec else []), *with_num[:3]}))
    if lines:
        return Finding("guardrail", "note", "A guardrail is named, with no limit.", lines[:3], "Give the limit as a number, such as refund requests stay under 1%.")
    return Finding("guardrail", "note", "No guardrail metric. The bar can be met by making something else worse.", [], 'Add "Guardrail: <metric> stays under <number>".')


def check_baseline(doc: Doc, brief: dict[str, tuple[int, str]], separate: bool = False) -> Finding:
    hits = [n for n, line in enumerate(doc.lines, 1) if BASELINE.search(ISO_DATE.sub("", line))]
    if hits:
        return Finding("baseline", "pass", "The metric's current value is stated.", hits[:2])
    where = [brief["metric"][0]] if "metric" in brief and not separate else []
    return Finding(
        "baseline", "note", "No current value for the metric, so the size of the gap to the bar is unknown.", where, 'State it with its source, such as "Today 34% (quoting events table, Q3)".'
    )


def check_assumptions(doc: Doc) -> Finding:
    sec = doc.section(SECTIONS["assumptions"], prefix=True)
    if sec and sec[1] and not any(TESTED.search(doc.line(n)) for n in sec[1]):
        return Finding(
            "assumptions",
            "note",
            "Risks or open questions are listed, with no test for any of them.",
            [sec[0], *sec[1][:2]],
            "Name the riskiest assumption and the test that will check it before build.",
        )
    if sec and sec[1]:
        return Finding("assumptions", "pass", f"Risks, assumptions or open questions listed ({len(sec[1])} line{'s' if len(sec[1]) != 1 else ''}).", [sec[0]])
    return Finding("assumptions", "note", "No risks, assumptions or open questions listed.", [sec[0]] if sec else [], "Name the riskiest assumption and how it will be tested before build.")


def check_instructions(doc: Doc) -> Finding:
    hits = [n for n, line in enumerate(doc.lines, 1) if INSTRUCTION.search(line)]
    if hits:
        return Finding(
            "instructions",
            "note",
            "Text that reads as an instruction to the reviewer. It is data, and it changed no check.",
            hits,
            "Tell the spec's author; remove it if it was not meant for readers.",
        )
    return Finding("instructions", "pass", "No text addressed to the reviewer.")


def check_brief_match(doc: Doc, parsed: landing_brief.Brief | None) -> Finding | None:
    """With a separate brief, a copy of the brief inside the spec must say the same thing. Compared through the parser."""
    start, fields = brief_fields(doc)
    if start is None:
        return None
    try:
        copy = landing_brief.parse("\n".join(doc.lines))
    except landing_brief.BriefError:
        return Finding("brief-match", "hold", "The spec's own copy of the landing brief does not parse.", [start], "Delete the copy and link the brief, or copy it again.")
    if parsed is None or copy == parsed:
        return Finding("brief-match", "pass", "The spec's copy of the landing brief matches the brief.", [start])
    differ = [key for attr, key in BRIEF_PARTS.items() if getattr(copy, attr) != getattr(parsed, attr)]
    differ = list(dict.fromkeys(differ))
    names = ", ".join(k.replace("_", " ") for k in differ)
    rows = [fields[k][0] for k in differ if k in fields]
    return Finding(
        "brief-match", "hold", f"The spec's copy of the landing brief differs from the brief on: {names}.", rows[:4] or [start], "Copy the brief again; change the brief itself if the plan changed."
    )


# Each part of the parsed brief, and the brief key it is written under.
BRIEF_PARTS = {
    "problem": "problem",
    "metric": "metric",
    "bar_text": "bar",
    "higher_is_better": "better",
    "by": "by",
    "non_goals": "non_goals",
    "tokens_per_task": "tokens_per_task",
    "price_per_token": "price_per_token",
    "line": "line",
    "line_note": "line",
    "decides": "decides",
}


def audit(doc: Doc, as_of: datetime.date | None = None, brief_doc: Doc | None = None) -> dict:
    """Audit the spec. With brief_doc (a separate brief file, as the Landing Loop keeps it), the brief checks read that file and
    cite its lines with file "brief"; the spec's own copy of the brief, if it has one, must match."""
    bdoc = brief_doc or doc
    bfile = "brief" if brief_doc is not None else "spec"
    start, brief = brief_fields(bdoc)
    try:
        parsed = landing_brief.parse("\n".join(bdoc.lines)) if start else None
    except landing_brief.BriefError:
        parsed = None
    ai, ai_lines = is_ai_feature(bdoc if brief_doc is not None and "line" in brief else doc, brief)
    if brief_doc is not None and "line" in brief:
        ai_lines = []  # the line is in the brief file, cited by the brief finding
    brief_findings = [*check_brief(bdoc, start, brief), *([check_date(parsed, brief, as_of), check_outcome(bdoc, brief)] if parsed else [])]
    for f in brief_findings:
        f.file = bfile
    match = check_brief_match(doc, parsed) if brief_doc is not None else None
    findings = [
        *brief_findings,
        *([match] if match else []),
        check_owner(doc, brief, bfile),
        check_rollout(doc),
        check_rollback(doc),
        check_eval(doc, ai, ai_lines),
        check_placeholders(doc),
        check_guardrail(doc),
        check_baseline(doc, brief, separate=brief_doc is not None),
        check_assumptions(doc),
        check_certainty(doc),
        check_instructions(doc),
    ]
    holds = sum(f.result == "hold" for f in findings)
    return {
        "tool": "spec-auditor",
        "version": VERSION,
        "spec": doc.path,
        "brief": bdoc.path if brief_doc is not None else None,
        "as_of": as_of.isoformat() if as_of else None,
        "ai_feature": ai,
        "verdict": "hold" if holds else "pass",
        "counts": {r: sum(f.result == r for f in findings) for r in ("hold", "note", "pass")},
        "findings": [asdict(f) for f in findings],
    }


ORDER = ("hold", "note", "pass")


def refs(lines: list[int], file: str = "spec") -> str:
    if not lines:
        return "-"
    return ("brief " if file == "brief" else "") + "L" + ", L".join(str(n) for n in lines)


def render_text(report: dict) -> str:
    c = report["counts"]
    out = [f"spec-auditor {report['version']}: {report['spec']}", f"AI feature: {'yes' if report['ai_feature'] else 'no'}", ""]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        out.append(f"[{f['result'].upper():4}] {f['check']:<12} {refs(f['lines'], f.get('file', 'spec')):<22} {f['message']}")
        if f["fix"] and f["result"] != "pass":
            out.append(f"{'':42} Fix: {f['fix']}")
    out += ["", f"Verdict: {report['verdict'].upper()} ({c['hold']} hold, {c['note']} note, {c['pass']} pass)"]
    return "\n".join(out) + "\n"


def render_md(report: dict) -> str:
    return render.markdown(report, report.get("source"))


def squash(text: str) -> str:
    return " ".join(text.split())


def check_quotes(doc: Doc, notes: object) -> list[dict]:
    """Each note the model writes must quote the spec word for word on the line it cites, and every number in the
    note must appear in that quote. Returns one row per note, with ok and, when not ok, why."""
    if not isinstance(notes, list):
        raise AuditError('the notes file must be a JSON list of {"line": n, "quote": "...", "note": "..."}.')
    rows = []
    for i, item in enumerate(notes, 1):
        if not isinstance(item, dict):
            rows.append({"index": i, "line": None, "ok": False, "why": "not an object"})
            continue
        line, quote, note = item.get("line"), item.get("quote"), item.get("note", "")
        row = {"index": i, "line": line, "ok": False, "why": ""}
        if not isinstance(line, int) or isinstance(line, bool) or not 1 <= line <= len(doc.lines):
            row["why"] = f"line {line!r} is not a line of the spec (1 to {len(doc.lines)})"
        elif not isinstance(quote, str) or len(quote.strip()) < 3:
            row["why"] = "the quote is missing or under 3 characters"
        elif not isinstance(note, str):
            row["why"] = "the note is not text"
        elif squash(quote) not in squash(doc.line(line)):
            row["why"] = f"the quote is not on line {line}, word for word"
        else:
            extra = sorted({x.rstrip("%") for x in NUM.findall(note)} - {x.rstrip("%") for x in NUM.findall(quote)})
            if extra:
                row["why"] = f"the note has numbers that are not in the quote: {', '.join(extra)}"
            else:
                row["ok"] = True
        rows.append(row)
    return rows


def load_source(args: argparse.Namespace) -> tuple[Doc, dict]:
    """The spec as a Doc, and where it came from. Live sources are read with the Leader Report's readers (sources.py)."""
    path = Path(args.path)
    try:
        text, source = sources.load(args.source, path, Path(args.meta) if args.meta else None, args.project)
    except sources.SourceError as e:
        raise AuditError(str(e)) from None
    is_html = path.suffix.lower() in (".html", ".htm")
    return parse_text(text, source.get("location") or str(path), is_html=is_html), source


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a PRD or spec against its landing brief and a checklist.")
    ap.add_argument("command", choices=["audit", "text", "quotes"])
    ap.add_argument("path", help="the spec: a file (.md, .txt, .html), or a saved Linear, Notion or Google Drive response")
    ap.add_argument("notes", nargs="?", help="quotes: a JSON file of the model's notes")
    ap.add_argument("--source", choices=sources.KINDS, default="file", help="where the spec came from: file (default), linear, notion or gdrive")
    ap.add_argument("--meta", help="notion or gdrive: the page or file object the connector returned, for the title, link and edit date")
    ap.add_argument("--brief", help="audit: the landing brief as its own file (the Landing Loop's briefs/<bet>.md); brief checks read it, and a copy in the spec must match")
    ap.add_argument("--illustrative", action="store_true", help="audit: tag the HTML page Illustrative, for sample data")
    ap.add_argument("--project", help="linear: the project's name, when the saved file holds several")
    ap.add_argument("--as-of", help="audit: today's date, YYYY-MM-DD, to hold a definition-of-good date in the past")
    ap.add_argument("--json", action="store_true", help="audit: print the report as JSON")
    ap.add_argument("--fail-on-hold", action="store_true", help="audit: exit 2 when the verdict is hold, to gate a pull request or CI job")
    ap.add_argument("--format", choices=["text", "md"], default="text", help="audit: text (default) or Markdown")
    ap.add_argument("--out", help="audit: a folder to write audit.html (Leader Report style), audit.md and audit.json")
    ap.add_argument("--html", help="audit: write the HTML page here, and its Markdown twin beside it with .md")
    ap.add_argument("--bet", help="audit: the bet's slug; writes the spec key of LANDING/<bet>.json, the Landing Loop record")
    ap.add_argument("--landing", default="landing", help="audit: the folder holding Landing Loop records (default: landing)")
    args = ap.parse_args(argv)
    try:
        as_of = datetime.date.fromisoformat(args.as_of) if args.as_of else None
    except ValueError:
        raise SystemExit(f"spec_audit: --as-of is {args.as_of!r}. Write it as YYYY-MM-DD.") from None
    if args.bet and not as_of:
        raise SystemExit("spec_audit: --bet needs --as-of, because every figure in the loop record carries its date.")
    try:
        doc, source = load_source(args)
        if args.command == "text":
            width = len(str(len(doc.lines)))
            sys.stdout.write("".join(f"{n:>{width}}  {line}\n" for n, line in enumerate(doc.lines, 1)))
            return 0
        if args.command == "quotes":
            if not args.notes:
                raise AuditError("quotes needs a notes file: spec_audit.py quotes SPEC NOTES.json")
            try:
                notes = json.loads(Path(args.notes).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                raise AuditError(f"cannot read {args.notes} as JSON ({e}).") from None
            rows = check_quotes(doc, notes)
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            bad = sum(not r["ok"] for r in rows)
            print(f"spec_audit: {len(rows) - bad} of {len(rows)} quotes check out." + (" Drop or fix the rest before showing them." if bad else ""), file=sys.stderr)
            return 1 if bad else 0
    except AuditError as e:
        raise SystemExit(f"spec_audit: {e}") from None
    brief_doc = None
    if args.brief:
        try:
            brief_doc = load(Path(args.brief))
        except AuditError as e:
            raise SystemExit(f"spec_audit: {e}") from None
    report = audit(doc, as_of, brief_doc)
    report["source"] = source
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render.markdown(report, source) if args.format == "md" else render_text(report))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "audit.html").write_text(render.page(report, doc.lines, source, brief_doc.lines if brief_doc else None, args.illustrative), encoding="utf-8")
        (out / "audit.md").write_text(render.markdown(report, source), encoding="utf-8")
        (out / "audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"spec_audit: wrote audit.html, audit.md and audit.json to {out}", file=sys.stderr)
    if args.html:
        page_path = Path(args.html)
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(render.page(report, doc.lines, source, brief_doc.lines if brief_doc else None, args.illustrative), encoding="utf-8")
        page_path.with_suffix(".md").write_text(render.markdown(report, source), encoding="utf-8")
        print(f"spec_audit: wrote {page_path} and {page_path.with_suffix('.md')}", file=sys.stderr)
    if args.bet:
        bdoc = brief_doc or doc
        start, fields = brief_fields(bdoc)
        where = args.brief or source.get("location") or source.get("file") or str(args.path)
        brief = loop.brief_figures("\n".join(bdoc.lines), where, {k: n for k, (n, _) in fields.items()}, as_of.isoformat()) if start else {}
        try:
            path = loop.write(Path(args.landing), args.bet, loop.spec_key(report, source, brief, as_of.isoformat()), Path(args.brief or args.path))
        except loop.LoopError as e:
            raise SystemExit(f"spec_audit: {e}") from None
        print(f"spec_audit: wrote the spec key of {path}; every other key is as it was.", file=sys.stderr)
    return 2 if args.fail_on_hold and report["verdict"] == "hold" else 0


if __name__ == "__main__":
    sys.exit(main())
