"""The audit as one self-contained HTML page, in the Leader Report style guide and the Landing Loop's one visual family,
and its Markdown twin.

The page takes the whole stylesheet of assets/template.html (vendored byte-identical from the Leader Report) and draws
its picture with svgkit (scripts/vendor/svgkit.py, vendored byte-identical from landing-loop). Only a few rules for
this page's layout are added.

It reads top down for someone who has never seen the loop: the shared header, the verdict as the heading, the
checks as scorecard rows (a share bar of the checks that pass, then one row per check, holds first, with the lines it
rests on and its result word), then one thing to do next. The findings follow as a scorecard, with the passes folded, then the
landing brief beside the lines the holds cite. Check codes, file paths, flags and the record key sit in a fold for
engineers. Public copy uses plain words: build plan, landing brief (defined at first use), target, quality tests,
when to undo it, release stages.

Green, grey-white and red are kept for landed, watch and stalled, which only did-it-land computes, so this page does
not use them: HOLD is a word in ink, NOTE and PASS muted, never a boxed chip. Brass is kept for the person who
decides. The scorecard follows the scorecard grammar (svgkit 1.2.0): HTML rows split by hairlines, Geist Mono 12px for
labels, figures and words, Geist 14px for names, a fixed-height share bar with no text in it. It draws only figures the
page prints, and its aria-label states the answer. Every piece of spec
text is escaped. Nothing here computes a figure; every count comes from the report.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import svgkit as sk  # noqa: E402  (vendored, unchanged; see VENDORED.json)

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.html"
STYLE = re.compile(r"<style>(.*?)</style>", re.S)
NAME = "Spec auditor"  # the page prints its plain name; the code name sits in the engineers' fold
MIN_FONT_PX = 11  # no text on the page prints smaller, at any width
ORDER = ("hold", "note", "pass")
Json = dict[str, Any]
NUMBER_WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen")

# Each check in plain words, short enough to sit beside its tick at 11px. The codes print in the engineers' fold.
LABELS = {
    "brief": "Landing brief",
    "brief-match": "Brief copy",
    "date": "Brief date",
    "outcome": "Result, not work",
    "owner": "Owner",
    "rollout": "Release stages",
    "rollback": "When to undo it",
    "eval-plan": "Quality tests",
    "placeholders": "Placeholders",
    "guardrail": "Guardrail",
    "baseline": "Today's number",
    "assumptions": "Assumptions",
    "certainty": "Certainty",
    "instructions": "Notes to reviewer",
}
RULES = {
    "brief": "The landing brief has every part, read by the parser the whole Landing Loop shares.",
    "brief-match": "A copy of the landing brief inside the build plan must say what the brief says.",
    "date": "The landing brief's date is not before the audit date.",
    "outcome": "The target is a result for the customer or the business, not work shipped.",
    "owner": "One named person decides the next step.",
    "rollout": "Release stages: a percentage, a switch, a group of customers or a pilot.",
    "rollback": "A number that triggers the undo (a number with a unit, or a comparison) and a way back.",
    "eval-plan": "For an AI feature: how many test cases, a pass mark as a number, and when the quality tests run.",
    "placeholders": "No TBD, TODO, ??? or [insert ...] left.",
    "guardrail": "A number that must not get worse, with its limit. A note; never holds.",
    "baseline": "The number's value today, with its source. A note; never holds.",
    "assumptions": "The riskiest assumption and the test that checks it. A note; never holds.",
    "certainty": "No forecast stated as certain. A note; never holds.",
    "instructions": "Text addressed to the reviewer is read as data. A note; never holds.",
}
# What to do about each check that can hold, as the heading says it.
FIXES = {
    "brief": "complete the landing brief",
    "brief-match": "make the brief copy match the landing brief",
    "date": "date the landing brief",
    "outcome": "make the target a result, not work",
    "owner": "name one owner",
    "rollout": "plan the release stages",
    "rollback": "set the number that triggers an undo",
    "eval-plan": "complete the quality test plan",
    "placeholders": "fill in the placeholders",
}
GROUPS = {"hold": "Hold: must change before build starts", "note": "Note: worth fixing, never blocks", "pass": "Pass"}

# The audit's sentences in the page's words. The report and the record keep the original text.
WORDS = (
    (r"\bThe eval plan has no time it runs\.", "The quality test plan does not say when the tests run."),
    (r"\bThe rollback plan has no trigger threshold\.", "The plan for undoing it has no number that triggers the undo."),
    (r"\brollback plan\b", "plan for undoing it"),
    (r"\b[Rr]ollback\b", "undo"),
    (r"\btrigger threshold\b", "number that triggers it"),
    (r"\bRollout plan with (\d+) staged lines\.", r"Release stages planned, on \1 lines."),
    (r"\b[Rr]ollout\b", "release"),
    (r"\bpass bar\b", "pass mark"),
    (r"\beval plan\b", "quality test plan"),
    (r"\bEval plan\b", "Quality test plan"),
    (r"\bevals\b", "quality tests"),
    (r"\beval\b", "quality test"),
    (r"\bcohort\b", "group of customers"),
    (r"\bThe landing brief parses, with every part present\.", "The landing brief is complete: every part is there."),
    (r"\bthe spec's\b", "the build plan's"),
    (r"\bThe spec's\b", "The build plan's"),
    (r"\bspec\b", "build plan"),
    (r"\bthe bar\b", "the target"),
    (r"\bbar\b", "target"),
    (r"\bThe metric\b", "The number"),
    (r"\bthe metric\b", "the number"),
    (r"\bguardrail metric\b", "guardrail number"),
)

# Layout for this page only, on top of the Leader Report stylesheet and svgkit.CSS, as did-it-land's page does.
# The template paints selection and the focus ring green, a status colour; this page sets both to ink.
# In the scorecard, a row with no picture gives its name the picture column too, so names stay on one line, and the
# figure column prints in one case, numerals and capitals, as /update does. The share that pass prints once, in the
# frame head with its bar (.sc-hb), not again as a row.
PAGE_CSS = """
::selection{background:var(--t1);color:var(--bg)}
:focus-visible{outline-color:var(--t1)}
main.solo{margin-left:0}
.solo .slide{min-height:0}
.solo .slide.cover{min-height:0;padding-top:40px;padding-bottom:48px;justify-content:flex-start}
.solo h1{font-size:clamp(34px,4.6vw,60px);line-height:1;letter-spacing:-.04em;text-wrap:balance;margin-bottom:20px}
.solo .lede{margin-bottom:28px}
.solo .lede b{color:var(--t1);font-weight:500}
.vd{font:500 12px/20px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--t2)}
.vd.hold{color:var(--t1)}
.kicker{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 18px;font-size:13.5px;color:var(--t2)}
.cols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px 48px;align-items:start}
.cover .cols{margin-top:28px;grid-template-columns:minmax(0,1fr)}
.next{display:grid;gap:10px;border:1px solid var(--brass);border-radius:12px;padding:20px 22px;background:var(--brass-bg)}
.next>b{font:400 11px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brass)}
.next p{margin:0;font-size:16px;line-height:1.5;color:var(--t1)}
.next p span{color:var(--t2)}
.whom{display:flex;flex-wrap:wrap;gap:4px 24px;font:400 11.5px/18px var(--mono);color:var(--brass)}
.whom i{font-style:normal;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);margin-right:8px}
.whom .d{color:var(--t2)}
.figs{margin:0;display:grid}
.figs>div{display:grid;grid-template-columns:120px minmax(0,1fr);gap:4px 16px;border-top:1px solid var(--line);padding:10px 0}
.figs dt{font:400 11px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.figs dd{margin:0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.figs dd b{color:var(--t1);font-weight:500}
.figs .own dd{color:var(--brass);font:400 12.5px/22px var(--mono)}
.st.hold{color:var(--t1)}.st.pass{color:var(--t1)}.st.note{color:var(--t2)}
.st.note::before{width:8px;height:8px;border-radius:50%;background:none;border:1.5px solid currentColor}
.st.pass::before{background:none;border:1.5px solid currentColor;width:8px;height:8px}
.sc-r.hold .sc-n>span:first-child{color:var(--t1)}
.sc-q{display:block;font:400 12px/1.6 var(--mono);color:var(--t2);white-space:pre-wrap;word-break:break-word}
.sc-q+.sc-q{margin-top:4px}
.sc-f{display:block;font-size:12.5px;line-height:1.5;color:var(--t2);margin-top:8px}
.sc-f::before{content:"FIX";font:400 11px/16px var(--mono);letter-spacing:.1em;color:var(--t1);margin-right:8px}
.sc-r .rule{grid-column:1/-1;font-size:12px;color:var(--t3);margin:0}
.solo details{margin-top:16px}
.solo details>.card,.solo details>.tablewrap{margin-top:12px}
.cite{display:grid;grid-template-columns:84px minmax(0,1fr);gap:16px;border-top:1px solid var(--line);padding:10px 0;font:400 12.5px/1.6 var(--mono);color:var(--t2)}
.cite:first-child{border-top:0;padding-top:0}
.cite b{font-weight:400;color:var(--t1);white-space:nowrap}
.note{font-size:12.5px;line-height:1.6;color:var(--t2);margin:12px 0 0}
.eng td{font-size:12px;vertical-align:top}
h3.sub{font:400 11px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3);margin:0 0 12px}
.foot{max-width:1120px;margin:0 auto;padding:28px 40px 64px;color:var(--t3);font-size:12px}
@media (max-width:1100px){.cols,.cols.even{grid-template-columns:minmax(0,1fr)}}
@media (max-width:980px){.foot{padding:24px 16px 48px}.solo .slide.cover{padding-top:24px}.card{padding:18px 16px}.sc{padding:0}.sc-r{gap:10px;padding:16px 0}}
@media (max-width:560px){.figs>div,.cite{grid-template-columns:1fr;gap:0}}
.scg .sc-l{text-transform:uppercase;letter-spacing:.06em}
.scg .sc-hb{display:inline-block;width:120px}
@container sc (min-width:800px){.scg .sc-r:has(>.sc-p:empty)>.sc-n{grid-column:1/3}.scg .sc-r:has(>.sc-p:empty)>.sc-p{display:none}}
/* Full column (site rule since 2026-11-25): every title and text block runs the content column, the scorecard frame's width. */
.solo h1,.solo h2,.solo h3,.solo .lede,.solo .next,.solo p,.solo li,.solo .sk figcaption{max-width:none}
.solo h1{text-wrap:balance}.solo .lede,.solo p,.solo li,.solo .sk figcaption{text-wrap:pretty}
"""


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def plain(text: str) -> str:
    """The audit's words in the page's words."""
    for pattern, to in WORDS:
        text = re.sub(pattern, to, text)
    return text


def count_word(n: int) -> str:
    return NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)


def and_join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def refs(lines: list[int], file: str = "spec") -> str:
    if not lines:
        return "-"
    return ("brief " if file == "brief" else "") + "L" + ", L".join(str(n) for n in lines)


MARKUP = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+)|\*\*|__|`")


def _is_heading(n: int, lines: list[str]) -> bool:
    return 1 <= n <= len(lines) and lines[n - 1].lstrip().startswith("#")


def _quote(n: int, lines: list[str]) -> str:
    """The line as a person reads it: the words and figures as written, without Markdown marks (#, -, **, `)."""
    return MARKUP.sub("", lines[n - 1]).strip()[:200] if 1 <= n <= len(lines) else ""


def stylesheet() -> str:
    """The report template's whole stylesheet, fonts included."""
    try:
        found = STYLE.search(TEMPLATE.read_text(encoding="utf-8"))
    except OSError:
        found = None
    return found.group(1) if found else ""


def floor_fonts(css: str) -> str:
    """Every font size in the page's CSS at MIN_FONT_PX or more. The vendored template and svgkit stay byte-identical;
    their smaller label sizes are raised here, as the page is written. A line height (after the slash) is left alone."""

    def raise_px(decl: re.Match[str]) -> str:
        return re.sub(r"(?<![/\d.])(\d+(?:\.\d+)?)px", lambda m: f"{MIN_FONT_PX}px" if float(m.group(1)) < MIN_FONT_PX else m.group(0), decl.group(0))

    return re.sub(r"font(?:-size)?:[^;}]*", raise_px, css)


def plain_title(text: str) -> str:
    """The plan's title in the page's words: a leading "PRD:" reads "Build plan:"."""
    return re.sub(r"^\s*PRDs?\b:?\s*", "Build plan: ", text)


def verdict_parts(report: Json) -> tuple[str, str]:
    """The heading (the verdict and how many checks hold) and the sentence that says what to do."""
    holds = [f for f in report["findings"] if f["result"] == "hold"]
    if not holds:
        return "Pass: every check that can stop this build plan is met.", "Ready to build."
    n = len(holds)
    todo = and_join([FIXES.get(f["check"], f"fix {LABELS.get(f['check'], f['check']).lower()}") for f in holds])
    head = f"Hold: {count_word(n).lower()} check{'s' if n != 1 else ''} stop{'s' if n == 1 else ''} this build plan."
    return head, f"{todo[:1].upper() + todo[1:]} before build starts."


def verdict_line(report: Json) -> str:
    return " ".join(verdict_parts(report))


def decider(brief: list[str] | None, spec: list[str]) -> str:
    """The person the landing brief names to decide the next step, read by the shared parser."""
    import landing_brief  # a sibling script, vendored unchanged

    try:
        return landing_brief.parse("\n".join(brief if brief is not None else spec)).decides
    except landing_brief.BriefError:
        return "the build plan's owner"


# The scorecard: one row per check, holds first, under a share bar of the checks that pass.

WORDS_FOR = {"hold": ("hold", True), "note": ("note", False), "pass": ("pass", False)}


def check_row(f: Json) -> str:
    """One check: its name, the lines it rests on, and its result as a word (HOLD in ink, NOTE and PASS muted)."""
    where = refs(f["lines"], f.get("file", "spec")) if f["lines"] else "whole plan"
    word, ink = WORDS_FOR[f["result"]]
    return sk.sc_row(LABELS.get(f["check"], f["check"]), figure=sk.figure_line(where), word=sk.check_word(word, ink=ink))


def scorecard_frame(report: Json, illustrative: bool) -> str:
    """The checks as scorecard rows: the share that pass once, in the frame head with its bar; then each check, holds first, then notes, then passes."""
    c = report["counts"]
    total = c["hold"] + c["note"] + c["pass"]
    rows = [check_row(f) for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"]))]
    return sk.sc_frame(
        rows,
        label=verdict_line(report),
        title="Checks",
        legend=f'<span>{c["pass"]} of {total} pass</span><span class="sc-hb">{sk.share_bar(c["pass"], total)}</span>',
        head=["Check", "", "Lines", "Result"],
        caption="The head shows the share of checks that pass. Then one row per check, holds first: L is a line of the build plan, brief L a line of the landing brief.",
        illustrative=illustrative,
    )


# Sections


def _row(f: Json, spec: list[str], brief: list[str] | None) -> str:
    source = brief if f.get("file") == "brief" and brief is not None else spec
    body = [n for n in f["lines"] if not _is_heading(n, source)] or f["lines"]
    quotes = [q for q in (_quote(n, source) for n in body[:2]) if q]
    value = "".join(f'<span class="sc-q">{esc(q)}</span>' for q in quotes) or '<span class="sc-l">No line to cite</span>'
    fix = f'<span class="sc-f">{esc(plain(f["fix"]))}</span>' if f["fix"] and f["result"] != "pass" else ""
    where = f'<span class="sc-x">{esc(refs(f["lines"], f.get("file", "spec")))}</span>' if f["lines"] else ""
    return (
        f'<div class="sc-r {esc(f["result"])}"><div class="sc-n"><span>{esc(LABELS.get(f["check"], f["check"]))}</span>'
        f'<span class="sc-d">{esc(plain(f["message"]))}</span>{fix}{where}</div>'
        f'<div class="sc-v">{value}</div>'
        f'<div class="sc-s"><span class="st {esc(f["result"])}">{esc(f["result"])}</span></div>'
        f'<p class="rule">{esc(RULES.get(f["check"], ""))}</p></div>'
    )


def scorecard(report: Json, spec: list[str], brief: list[str] | None, results: tuple[str, ...]) -> str:
    out = ['<div class="sc-h"><span>Check</span><span>What the build plan says</span><span>Result</span></div>']
    for result in results:
        rows = [f for f in report["findings"] if f["result"] == result]
        if rows:
            out.append(f'<div class="sc-g">{esc(GROUPS[result])} · {len(rows)}</div>')
            out += [_row(f, spec, brief) for f in rows]
    return f'<div class="card"><div class="sc">{"".join(out)}</div></div>'


def brief_rows(brief: list[str] | None, spec: list[str]) -> str:
    """The landing brief's parts as the shared parser read them, each with its line. Shown only when the brief parses."""
    import landing_brief  # a sibling script, vendored unchanged

    text = brief if brief is not None else spec
    try:
        b = landing_brief.parse("\n".join(text))
    except landing_brief.BriefError:
        return ""
    where = "brief" if brief is not None else "spec"
    found: dict[str, int] = {}
    for n, line in enumerate(text, 1):
        m = landing_brief.LINE.match(line.strip())
        key = landing_brief.KEYS.get(m.group(1).strip().lower()) if m else None
        if key and key not in found:
            found[key] = n
    parts = (
        ("Problem", b.problem, "problem", ""),
        ("Number", b.metric, "metric", ""),
        ("Target", f"{b.bar_text} or {'higher' if b.higher_is_better else 'lower'} by {b.by}", "bar", ""),
        ("Out of scope", b.non_goals, "non_goals", ""),
        ("Cost budget", "AI usage per task and AI price per unit, two lines. cost-budget-check owns the figures.", "tokens_per_task", ""),
        ("Who does what", f"{b.line}. {b.line_note}".strip(), "line", ""),
        ("Decides next", b.decides, "decides", "own"),
    )
    rows = "".join(f'<div class="{cls}"><dt>{esc(k)}</dt><dd>{esc(v)} <span class="t3 mono">{esc(refs([found[key]], where) if key in found else "")}</span></dd></div>' for k, v, key, cls in parts)
    return f'<dl class="figs">{rows}</dl>'


def engineers(report: Json, source: Json) -> str:
    rows = "".join(
        f'<tr><td class="mono">{esc(f["check"])}</td><td>{esc(f["result"])}</td><td class="mono">{esc(refs(f["lines"], f.get("file", "spec")))}</td><td>{esc(f["message"])}</td></tr>'
        for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"]))
    )
    where = source.get("location") or source.get("file") or report["spec"]
    note = (
        f'<p class="note">Skill: <code>spec-auditor</code> {esc(report["version"])}. It read <code>{esc(where)}</code>'
        + (f" and the landing brief <code>{esc(report['brief'])}</code>" if report.get("brief") else "")
        + f". AI feature: {'yes' if report['ai_feature'] else 'no'}, so the quality test check {'applies' if report['ai_feature'] else 'does not apply'}. "
        "Line numbers refer to the text as read. With <code>--bet</code> and <code>--landing</code>, the audit adds its page to the project file: "
        "the <code>spec</code> key of <code>landing/&lt;slug&gt;.json</code>, and no other key. <code>--fail-on-hold</code> exits 2 for CI on a hold.</p>"
    )
    head = "<tr><th>Check code</th><th>Result</th><th>Lines</th><th>Finding, as recorded</th></tr>"
    return f'<details><summary>For your engineers</summary><div class="tablewrap eng"><table>{head}{rows}</table></div>{note}</details>'


def page(report: Json, lines: list[str], source: Json, brief: list[str] | None = None, illustrative: bool = False) -> str:
    c = report["counts"]
    title = plain_title(source.get("title") or Path(report["spec"]).name)
    verdict = report["verdict"]
    header = sk.page_header(NAME, date=f"Audit {report.get('as_of') or 'undated'}", version=f"v{report['version']}", illustrative=illustrative)
    lede = (
        f"{esc(title)}. The <b>build plan</b> is checked against its <b>landing brief</b>, a one-page plan: what good looks like, by when, "
        "at what cost. A hold must change before build starts; a note is worth fixing and never blocks."
    )
    head, todo = verdict_parts(report)
    kicker = f'<p class="kicker"><span class="vd {esc(verdict)}">{esc(verdict)}</span><span>{esc(todo)}</span></p>'
    pic = scorecard_frame(report, illustrative)
    holds = [f for f in report["findings"] if f["result"] == "hold"]
    who = decider(brief, lines)
    if holds:
        f = holds[0]
        step = f"<p>{esc(LABELS.get(f['check'], f['check']))}. <span>{esc(plain(f['fix']))}</span></p>"
        if len(holds) > 1:
            step += f"<p><span>Then {esc(and_join([LABELS.get(h['check'], h['check']).lower() for h in holds[1:]]))}, as the findings say.</span></p>"
        when = "before build starts"
    else:
        step, when = "<p>Start the build. Then run the quality tests and cost check the landing brief names.</p>", "now"
    nxt = f'<div class="next"><b>What to do next</b>{step}<span class="whom"><span class="o"><i>Decides</i>{esc(who)}</span><span class="d"><i>When</i>{esc(when)}</span></span></div>'
    facts = [
        ("Hold", f"<b>{c['hold']}</b> must change"),
        ("Note", f"<b>{c['note']}</b> worth fixing"),
        ("Pass", f"<b>{c['pass']}</b> met"),
        ("Build plan", f"<b>{len(lines)}</b> lines, read {esc(report.get('as_of') or 'undated')}"),
        ("AI feature", "yes, so the quality tests are checked" if report["ai_feature"] else "no"),
    ]
    glance = '<dl class="figs">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in facts) + "</dl>"
    cover = f'<section class="slide cover">{header}<h1>{esc(head)}</h1>{kicker}<p class="lede">{lede}</p>{pic}<div class="cols">{nxt}{glance}</div></section>'
    passes = ""
    if c["pass"]:
        passes = f"<details><summary>{c['pass']} checks pass</summary>{scorecard(report, lines, brief, ('pass',))}</details>"
    findings = (
        f'<section class="slide"><div class="meta"><span>Findings</span></div><h2>What stops the build plan, and the lines it rests on</h2>'
        f"{scorecard(report, lines, brief, ('hold', 'note'))}{passes}</section>"
    )
    hold_lines = sorted({(f.get("file", "spec"), n) for f in holds for n in f["lines"]})
    cites = "".join(
        f'<div class="cite"><b>{esc(refs([n], file))}</b><span>{esc(_quote(n, brief if file == "brief" and brief is not None else lines))}</span></div>'
        for file, n in hold_lines
        if _quote(n, brief if file == "brief" and brief is not None else lines) and not _is_heading(n, brief if file == "brief" and brief is not None else lines)
    )
    brief_html = brief_rows(brief, lines)
    left = f'<div><h3 class="sub">The landing brief it is checked against</h3>{brief_html}</div>' if brief_html else ""
    right = f'<div><h3 class="sub">The lines the holds cite</h3><div class="card">{cites}</div></div>' if cites else ""
    evidence = f'<section class="slide"><div class="meta"><span>Evidence</span></div><h2>The plan and the lines</h2><div class="cols even">{left}{right}</div></section>' if left or right else ""
    detail = f'<section class="slide"><div class="meta"><span>Detail</span></div>{engineers(report, source)}</section>'
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(f"{NAME}: {title}")}</title><style>{floor_fonts(stylesheet() + sk.CSS + sk.SCORECARD_CSS + PAGE_CSS)}</style></head><body><main class="solo">'
        f"{cover}{findings}{evidence}{detail}"
        f'<p class="foot">{NAME} {esc(report["version"])}. Every check runs in code; line numbers refer to the text as read. '
        "A pass means the build plan is complete enough to build against, not that the project will land.</p></main></body></html>\n"
    )


def md_cell(text: str) -> str:
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def markdown(report: Json, source: Json | None = None) -> str:
    c = report["counts"]
    source = source or {}
    ai = "yes" if report["ai_feature"] else "no"
    where = source.get("location") or source.get("file") or Path(report["spec"]).name
    brief = f" The landing brief is {md_cell(str(report['brief']))}." if report.get("brief") else ""
    out = [
        f"## Spec audit: **{report['verdict']}**",
        "",
        f"**{verdict_line(report)}**",
        "",
        f"{c['hold']} hold, {c['note']} note, {c['pass']} pass. AI feature: {ai}. As of {report.get('as_of') or 'not given'}. "
        f"The build plan is checked against its landing brief, a one-page plan: what good looks like, by when, at what cost. Line numbers refer to {md_cell(str(where))}.{brief}",
        "",
        "| Result | Check | Lines | Finding | Fix |",
        "|---|---|---|---|---|",
    ]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        fix = plain(f["fix"]) if f["result"] != "pass" else ""
        out.append(f"| {f['result']} | {LABELS.get(f['check'], f['check'])} | {refs(f['lines'], f.get('file', 'spec'))} | {md_cell(plain(f['message']))} | {md_cell(fix)} |")
    out += ["", "For your engineers: check codes " + ", ".join(f"{LABELS.get(f['check'], f['check'])} = {f['check']}" for f in report["findings"]) + "."]
    return "\n".join(out) + "\n"
