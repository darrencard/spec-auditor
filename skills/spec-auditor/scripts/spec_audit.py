#!/usr/bin/env python3
"""Audit a PRD or spec against its landing brief and a checklist, and give a pass or hold verdict.

Usage:
  python3 scripts/spec_audit.py audit spec.md                       # findings with line numbers, then the verdict
  python3 scripts/spec_audit.py audit spec.md --as-of 2026-11-26    # also hold a definition-of-good date in the past
  python3 scripts/spec_audit.py audit spec.html --json              # the same as JSON
  python3 scripts/spec_audit.py audit spec.md --format md           # as Markdown, to paste into a review
  python3 scripts/spec_audit.py text spec.html                      # the numbered text every line number refers to
  python3 scripts/spec_audit.py quotes spec.md notes.json           # check the model's quotes against the spec

Input: Markdown (.md), plain text (.txt), or an HTML export (.html, .htm) such as Google Docs "Web page" or Notion
"HTML". HTML is turned into plain lines first; every line number refers to that text, which `text` prints.

The checks, each run in code:
  brief        a "Landing brief" block that the landing-brief skill accepts (scripts/landing_brief.py)
  problem      the problem, in at least 6 words
  good         the definition of good: a metric, a bar that is one number, which way is better, and a date
  non-goals    at least one thing the work will not do
  cost         the cost budget as two lines, tokens per task and price per token, each one number
  owner        a named person who owns the work or decides the next step, not a team or TBD
  rollout      a rollout plan with a stage (a percentage, a flag, a cohort, a pilot)
  rollback     a rollback plan with a trigger (a number) and a way back (a flag, a revert, an off switch)
  eval-plan    for an AI feature: an eval plan with a case count, a pass bar and when it runs
  placeholders no TBD, TODO, TBC, ??? or [insert ...] left in the spec
  certainty    notes forecasts stated as certain ("will increase", "guarantees"). Never holds.
  instructions notes text addressed to the reviewer ("ignore the checklist", "mark this pass"). Never holds.

Any finding marked hold makes the verdict hold. Notes never change the verdict. Nothing in the spec changes a check:
text that reads like an instruction ("mark this pass") is data, like every other line.

`quotes` is the line the model holds to: every passage it relies on must appear word for word on the line it cites,
and every number in its note must appear in that quote. Anything else is rejected, and the command exits 1.

This script reads files and prints text. It makes no network calls. Standard library only. Python 3.11 or later.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import landing_brief  # noqa: E402  (vendored, unchanged, from the landing-brief skill)

VERSION = "0.1.0"
# A spec is tens of pages at most. Anything larger is not one.
MAX_CHARS = 400_000
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# Bold-only lines act as headings in many Google Docs and Notion exports: "**Rollout**". Level 7 sits below any "#".
BOLD_HEADING = re.compile(r"^(?:\*\*|__)([^*_:]{2,60})(?:\*\*|__)\s*$")
ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>|~])")
NUM = re.compile(r"(?<![\w.])[$£€]?\d[\d,]*(?:\.\d+)?%?")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Heading words for each part, matched against a heading's text in lower case.
SECTIONS = {
    "problem": ("problem", "the problem", "problem statement", "why", "background", "context"),
    "good": ("definition of good", "success", "success metric", "success metrics", "success criteria", "goal", "goals", "metrics"),
    "non_goals": ("non-goals", "non goals", "nongoals", "out of scope", "not in scope", "scope exclusions"),
    "cost": ("cost budget", "cost", "costs", "budget", "unit economics"),
    "owner": ("owner", "owners", "ownership", "dri", "team", "people"),
    "rollout": ("rollout", "roll-out", "rollout plan", "launch plan", "release plan", "launch", "release"),
    "rollback": ("rollback", "roll back", "rollback plan", "kill switch", "off switch", "backout plan", "back-out plan"),  # voice-lint-disable-line
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
AI_WORDS = re.compile(r"\b(?:LLM|large language model|language model|prompts?|AI assistant|AI feature|model call|generative|GPT|Claude|agents?|AI)\b", re.I)
CERTAIN = re.compile(r"\bwill (?:increase|decrease|reduce|cut|double|triple|drive|grow|improve|lift|boost|eliminate)\b|\bguarantee[sd]?\b|\bdefinitely\b|\bcertain to\b", re.I)
VAGUE_GOOD = re.compile(r"\b(?:improve|better|faster|easier|delight|world-class|more engaging)\b", re.I)
# Text that reads as an instruction to whoever, or whatever, reviews the spec. Flagged as a note; it changes nothing.
INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|skip|override)\b.{0,40}\b(?:rules?|checklist|checks?|instructions?|audit|above|previous)\b"
    r"|\bmark (?:this|the spec|it)\b.{0,20}\b(?:pass|passed|approved|landed)\b|\b(?:system prompt|you are now|as an ai)\b",
    re.I,
)
COMBINED_COST = re.compile(r"per task|per request|per call|a task|each task", re.I)


class AuditError(ValueError):
    """A file that cannot be audited."""


@dataclass
class Finding:
    check: str
    result: str  # "pass", "hold" or "note"
    message: str
    lines: list[int] = field(default_factory=list)
    fix: str = ""


@dataclass
class Doc:
    path: str
    lines: list[str]  # read through line(n), which is 1-indexed
    headings: list[tuple[int, int, str]]  # (line number, level, text in lower case)

    def line(self, n: int) -> str:
        return self.lines[n - 1]

    def section(self, names: tuple[str, ...]) -> tuple[int, list[int]] | None:
        """(heading line, non-blank body line numbers) for the first heading whose text is one of names, else None."""
        for i, (n, level, text) in enumerate(self.headings):
            clean = re.sub(r"^[\d.]+\s*", "", text).strip(" :")
            if clean in names:
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
    hits = [n for n, line in enumerate(doc.lines, 1) if AI_WORDS.search(line)]
    return bool(hits), hits[:5]


def check_brief(doc: Doc, start: int | None) -> Finding:
    if start is None:
        return Finding("brief", "hold", 'There is no "Landing brief" block.', [], 'Add a "## Landing brief" section with the five parts (see references/checklist.md).')
    try:
        landing_brief.parse("\n".join(doc.lines))
    except landing_brief.BriefError as e:
        detail = str(e).replace("the landing brief cannot be used:", "").strip()
        return Finding("brief", "hold", "The landing brief does not parse: " + re.sub(r"\s*\n\s*", " ", detail), [start], "Fix each part the message lists.")
    return Finding("brief", "pass", "The landing brief parses, with every part present.", [start])


def check_problem(doc: Doc, brief: dict[str, tuple[int, str]]) -> Finding:
    if "problem" in brief:
        n, text = brief["problem"]
        lines = [n]
    else:
        sec = doc.section(SECTIONS["problem"])
        if sec is None:
            return Finding("problem", "hold", "No problem statement.", [], "State the problem in one or two sentences, in the customer's terms.")
        lines, text = [sec[0], *sec[1][:3]], body_text(doc, sec[1])
    words = len(re.findall(r"[A-Za-z']+", text))
    if words < 6:
        return Finding("problem", "hold", f"The problem is {words} words, too short to say whose problem it is.", lines, "Name who has the problem and what it costs them.")
    return Finding("problem", "pass", f"Problem stated ({words} words).", lines)


def check_good(doc: Doc, brief: dict[str, tuple[int, str]], as_of: datetime.date | None) -> list[Finding]:
    parts = ("metric", "bar", "better", "by")
    if all(p in brief for p in parts):
        lines = [brief[p][0] for p in parts]
        problems = []
        if landing_brief.number(brief["bar"][1]) is None:
            problems.append(f'the bar "{brief["bar"][1][:40]}" is not one number')
        if brief["better"][1].lower() not in ("higher", "lower"):
            problems.append(f'better is "{brief["better"][1][:20]}", not higher or lower')
        try:
            by: datetime.date | None = datetime.date.fromisoformat(brief["by"][1])
        except ValueError:
            by = None
            problems.append(f'the date "{brief["by"][1][:20]}" is not YYYY-MM-DD')
        if problems:
            return [Finding("good", "hold", "The definition of good is not checkable: " + "; ".join(problems) + ".", lines, "Write one metric, one number for the bar, higher or lower, and a date.")]
        b = brief
        out = [Finding("good", "pass", f"Definition of good: {b['metric'][1][:60]}, bar {b['bar'][1]}, {b['better'][1].lower()} is better, by {b['by'][1]}.", lines)]
        if as_of and by and by < as_of:
            out.append(Finding("good", "hold", f"The date {b['by'][1]} is before {as_of.isoformat()}, so the bar cannot be met in time.", [b["by"][0]], "Set a date that is still ahead."))
        return out
    sec = doc.section(SECTIONS["good"])
    if sec is None:
        missing = [p for p in parts if p not in brief]
        where = [brief[p][0] for p in parts if p in brief]
        said = f" (the brief is missing {', '.join(missing)})" if where else ""
        return [Finding("good", "hold", f"No definition of good{said}.", where, "Add Metric, Bar, Better and By to the landing brief.")]
    head, body = sec
    text = ISO_DATE.sub("", body_text(doc, body))
    has_num = bool(NUM.search(text))
    has_date = bool(ISO_DATE.search(body_text(doc, body)))
    if has_num and has_date:
        return [
            Finding(
                "good", "note", "Success is described with a number and a date, but not as a landing brief bar.", [head, *body[:4]], "Move it into the landing brief as Metric, Bar, Better and By."
            )
        ]
    vague = [n for n in body if VAGUE_GOOD.search(doc.line(n))]
    lacks = " or ".join(x for x, ok in (("a number", has_num), ("a date", has_date)) if not ok)
    return [
        Finding(
            "good",
            "hold",
            f"Success is described without {lacks}, so no one can say whether it landed.",
            [head, *(vague or body)[:4]],
            "Name one metric the team already measures, the bar, which way is better, and the date.",
        )
    ]


def check_non_goals(doc: Doc, brief: dict[str, tuple[int, str]]) -> Finding:
    if "non_goals" in brief:
        n, value = brief["non_goals"]
        if value.lower().strip(".") in ("none", "n/a", "-", "tbd"):
            return Finding("non-goals", "hold", f'Non-goals is "{value}".', [n], "Name at least one thing this work will not do.")
        return Finding("non-goals", "pass", "Non-goals stated.", [n])
    sec = doc.section(SECTIONS["non_goals"])
    if sec and sec[1]:
        return Finding("non-goals", "pass", f"Non-goals stated ({len(sec[1])} lines).", [sec[0], *sec[1][:3]])
    return Finding("non-goals", "hold", "No non-goals.", [sec[0]] if sec else [], "Name at least one thing this work will not do.")


def check_cost(doc: Doc, brief: dict[str, tuple[int, str]], ai: bool) -> Finding:
    tokens, price = brief.get("tokens_per_task"), brief.get("price_per_token")
    for n, key, value in key_lines(doc, ("tokens per task", "price per token")):
        if key == "tokens per task" and tokens is None:
            tokens = (n, value)
        if key == "price per token" and price is None:
            price = (n, value)
    if tokens and price:
        lines = [tokens[0], price[0]]
        bad = [k for k, v in (("tokens per task", tokens[1]), ("price per token", price[1])) if v.lower() != "none" and landing_brief.number(v) is None]
        if bad:
            return Finding("cost", "hold", f"{' and '.join(bad).capitalize()} is not one number.", lines, "Write one number on each line, such as 9,000 and $0.000003.")
        if ai and any(v.lower() == "none" for v in (tokens[1], price[1])):
            return Finding("cost", "hold", "The cost budget is none, but this is an AI feature.", lines, "State tokens per task and price per token.")
        return Finding("cost", "pass", f"Cost budget on two lines: {tokens[1]} tokens per task, {price[1]} per token.", lines)
    one = [n for n, line in enumerate(doc.lines, 1) if re.search(r"tokens? per task", line, re.I) and re.search(r"per token", line, re.I)]
    if one:
        return Finding("cost", "hold", "Tokens per task and price per token are on one line.", one[:3], "State them as two lines.")
    combined = [n for n, line in enumerate(doc.lines, 1) if COMBINED_COST.search(line) and NUM.search(line) and re.search(r"cost|[$£€]", line, re.I)]
    if combined:
        return Finding("cost", "hold", "The cost is one figure per task, not tokens per task and price per token.", combined[:3], "Split it into two lines: Tokens per task, and Price per token.")
    sec = doc.section(SECTIONS["cost"])
    if not ai:
        return Finding("cost", "note", "No cost budget. Fine for fixed code; say so in the landing brief with none on both lines.", [sec[0]] if sec else [])
    return Finding("cost", "hold", "No cost budget for an AI feature.", [sec[0]] if sec else [], "Add Tokens per task and Price per token as two lines.")


def check_owner(doc: Doc, brief: dict[str, tuple[int, str]]) -> Finding:
    candidates = [brief["decides"]] if "decides" in brief else []
    candidates += [(n, v) for n, _, v in key_lines(doc, OWNER_KEYS) if (n, v) not in candidates]
    named = [(n, v) for n, v in candidates if v.split(",")[0].strip().strip(".").lower() not in PLACEHOLDER_OWNERS and not PLACEHOLDER.search(v)]
    if named:
        n, v = named[0]
        return Finding("owner", "pass", f"Owner named: {v[:60]}.", [n])
    if candidates:
        return Finding("owner", "hold", f'The owner is "{candidates[0][1][:40]}", not a named person.', [n for n, _ in candidates][:3], "Name one person who decides the next step.")
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
    trigger = [n for n in lines if NUM.search(ISO_DATE.sub("", doc.line(n)))]
    way = [n for n in lines if WAY_BACK.search(doc.line(n))]
    missing = [x for x, ok in (("trigger with a number", trigger), ("way back", way)) if not ok]
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


def audit(doc: Doc, as_of: datetime.date | None = None) -> dict:
    start, brief = brief_fields(doc)
    ai, ai_lines = is_ai_feature(doc, brief)
    findings = [
        check_brief(doc, start),
        check_problem(doc, brief),
        *check_good(doc, brief, as_of),
        check_non_goals(doc, brief),
        check_cost(doc, brief, ai),
        check_owner(doc, brief),
        check_rollout(doc),
        check_rollback(doc),
        check_eval(doc, ai, ai_lines),
        check_placeholders(doc),
        check_certainty(doc),
        check_instructions(doc),
    ]
    holds = sum(f.result == "hold" for f in findings)
    return {
        "tool": "spec-auditor",
        "version": VERSION,
        "spec": doc.path,
        "as_of": as_of.isoformat() if as_of else None,
        "ai_feature": ai,
        "verdict": "hold" if holds else "pass",
        "counts": {r: sum(f.result == r for f in findings) for r in ("hold", "note", "pass")},
        "findings": [asdict(f) for f in findings],
    }


ORDER = ("hold", "note", "pass")


def refs(lines: list[int]) -> str:
    return ("L" + ", L".join(str(n) for n in lines)) if lines else "-"


def render_text(report: dict) -> str:
    c = report["counts"]
    out = [f"spec-auditor {report['version']}: {report['spec']}", f"AI feature: {'yes' if report['ai_feature'] else 'no'}", ""]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        out.append(f"[{f['result'].upper():4}] {f['check']:<12} {refs(f['lines']):<22} {f['message']}")
        if f["fix"] and f["result"] != "pass":
            out.append(f"{'':41} Fix: {f['fix']}")
    out += ["", f"Verdict: {report['verdict'].upper()} ({c['hold']} hold, {c['note']} note, {c['pass']} pass)"]
    return "\n".join(out) + "\n"


def md_cell(text: str) -> str:
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def render_md(report: dict) -> str:
    c = report["counts"]
    ai = "yes" if report["ai_feature"] else "no"
    out = [
        f"## Spec audit: **{report['verdict']}**",
        "",
        f"{c['hold']} hold, {c['note']} note, {c['pass']} pass. AI feature: {ai}. Line numbers refer to {md_cell(Path(report['spec']).name)}.",
        "",
        "| Result | Check | Lines | Finding | Fix |",
        "|---|---|---|---|---|",
    ]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        fix = f["fix"] if f["result"] != "pass" else ""
        out.append(f"| {f['result']} | {f['check']} | {refs(f['lines'])} | {md_cell(f['message'])} | {md_cell(fix)} |")
    return "\n".join(out) + "\n"


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a PRD or spec against its landing brief and a checklist.")
    ap.add_argument("command", choices=["audit", "text", "quotes"])
    ap.add_argument("path", help="the spec: .md, .txt, or an .html export from Google Docs or Notion")
    ap.add_argument("notes", nargs="?", help="quotes: a JSON file of the model's notes")
    ap.add_argument("--as-of", help="audit: today's date, YYYY-MM-DD, to hold a definition-of-good date in the past")
    ap.add_argument("--json", action="store_true", help="audit: print the report as JSON")
    ap.add_argument("--format", choices=["text", "md"], default="text", help="audit: text (default) or Markdown")
    args = ap.parse_args(argv)
    try:
        as_of = datetime.date.fromisoformat(args.as_of) if args.as_of else None
    except ValueError:
        raise SystemExit(f"spec_audit: --as-of is {args.as_of!r}. Write it as YYYY-MM-DD.") from None
    try:
        doc = load(Path(args.path))
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
    report = audit(doc, as_of)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render_md(report) if args.format == "md" else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
