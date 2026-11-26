"""The audit as one self-contained HTML page in the Leader Report style guide, and its Markdown twin.

The page is assets/template.html, vendored byte-identical from the Leader Report, with its slots filled: the rail
(brand mark, wordmark, contents), the bar, and the body. It follows that skill's references/design.md: scorecard rows,
mono capital labels, hairlines, one frame for cards side by side, and the result word always printed beside its mark.
Green, grey-white and red are kept for landed, watch and stalled, which only did-it-land computes, so this page does
not use them: a hold is brass (the spec's owner owes a fix), a pass is ink, a note is a ring. Every piece of spec text
is escaped. Nothing here computes a figure; every count comes from the report.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.html"
ORDER = ("hold", "note", "pass")
Json = dict[str, Any]

LABELS = {
    "brief": "Landing brief",
    "brief-match": "Brief copy",
    "date": "Brief date",
    "outcome": "Outcome bar",
    "owner": "Owner",
    "rollout": "Rollout",
    "rollback": "Rollback",
    "eval-plan": "Eval plan",
    "placeholders": "Placeholders",
    "guardrail": "Guardrail",
    "baseline": "Baseline",
    "assumptions": "Assumptions",
    "certainty": "Certainty",
    "instructions": "Text to the reviewer",
}
RULES = {
    "brief": "landing_brief.py, the parser the whole Landing Loop shares, decides whether the brief is complete.",
    "brief-match": "A copy of the brief inside the spec must say what the brief says.",
    "date": "The brief's date is not before the audit date.",
    "outcome": "The bar is a result for the customer or the business, not work shipped.",
    "owner": "One named person decides the next step.",
    "rollout": "Stages: a percentage, a flag, a cohort or a pilot.",
    "rollback": "A trigger threshold (a number with a unit or a comparison) and a way back.",
    "eval-plan": "For an AI feature: a case count, a pass bar as a number, and when the evals run.",
    "placeholders": "No TBD, TODO, ??? or [insert ...] left.",
    "guardrail": "A metric that must not get worse, with its limit. A note; never holds.",
    "baseline": "The metric's value today, with its source. A note; never holds.",
    "assumptions": "The riskiest assumption and the test that checks it. A note; never holds.",
    "certainty": "No forecast stated as certain. A note; never holds.",
    "instructions": "Text addressed to the reviewer is data. A note; never holds.",
}
GROUPS = {"hold": "Hold: blocks the spec until it changes", "note": "Note: worth fixing, never blocks", "pass": "Pass"}

# Added inside the body, so the vendored template stays byte-identical. Result marks reuse the template's .st shape.
EXTRA_CSS = """<style>
.slide{min-height:0;padding-top:64px;padding-bottom:56px}
.st.hold{color:var(--brass)}.st.pass{color:var(--t1)}.st.note{color:var(--t2)}
.st.note::before{width:8px;height:8px;border-radius:50%;background:none;border:1.5px solid currentColor}
.sc-r.hold .sc-n>span:first-child{color:var(--brass)}
.sc-q{display:block;font:400 12px/1.6 var(--mono);color:var(--t2);white-space:pre-wrap;word-break:break-word}
.sc-q+.sc-q{margin-top:4px}
.sc-f{display:block;font-size:12.5px;line-height:1.5;color:var(--t2);margin-top:8px}
.sc-f::before{content:"FIX";font:400 10px/16px var(--mono);letter-spacing:.1em;color:var(--brass);margin-right:8px}
.sc-r .guide{grid-column:1/-1;margin-top:0}
.sc .sc-g:nth-child(2){border-top:0;padding-top:20px}
.vd{display:inline-flex;align-items:center;gap:10px;font:400 12px/20px var(--mono);letter-spacing:.12em;text-transform:uppercase}
.vd{border:1px solid var(--line3);border-radius:4px;padding:4px 12px;color:var(--t1)}
.vd.hold{color:var(--brass);border-color:var(--brass);background:var(--brass-bg)}
.facts b.hold{color:var(--brass)}
.kv{display:grid;grid-template-columns:200px minmax(0,1fr) 96px;gap:8px 32px;align-items:baseline;border-top:1px solid var(--line);padding:16px 0;font-size:14px;color:var(--t1)}
.kv:first-child{border-top:0;padding-top:4px}
.kv .k{font:400 10px/20px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.kv .l{font:400 11.5px/20px var(--mono);color:var(--t3);text-align:right;white-space:nowrap}
.kv .own{color:var(--brass)}
.cite{display:grid;grid-template-columns:96px minmax(0,1fr);gap:20px;border-top:1px solid var(--line);padding:12px 0;font:400 12.5px/1.6 var(--mono);color:var(--t2)}
.cite:first-child{border-top:0;padding-top:0}
.cite b{font-weight:400;color:var(--t3);white-space:nowrap}
@media (max-width:980px){.card{padding:18px 16px}.sc{padding:0}.sc-r{gap:10px;padding:16px 0}}
@media (max-width:980px){.kv{grid-template-columns:1fr;gap:4px}.kv .l{text-align:left}.cite{grid-template-columns:1fr;gap:4px}.facts{gap:16px 32px}}
</style>"""


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


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


def _row(f: Json, spec: list[str], brief: list[str] | None) -> str:
    source = brief if f.get("file") == "brief" and brief is not None else spec
    body = [n for n in f["lines"] if not _is_heading(n, source)] or f["lines"]
    quotes = [q for q in (_quote(n, source) for n in body[:2]) if q]
    value = "".join(f'<span class="sc-q">{esc(q)}</span>' for q in quotes) or '<span class="sc-l">No line to cite</span>'
    fix = f'<span class="sc-f">{esc(f["fix"])}</span>' if f["fix"] and f["result"] != "pass" else ""
    where = f'<span class="sc-x">{esc(refs(f["lines"], f.get("file", "spec")))}</span>' if f["lines"] else ""
    return (
        f'<div class="sc-r {esc(f["result"])}"><div class="sc-n"><span>{esc(LABELS.get(f["check"], f["check"]))}</span>'
        f'<span class="sc-d">{esc(f["message"])}</span>{fix}{where}</div>'
        f'<div class="sc-v">{value}</div>'
        f'<div class="sc-s"><span class="st {esc(f["result"])}">{esc(f["result"])}</span></div>'
        f'<div class="guide">{esc(RULES.get(f["check"], ""))}</div></div>'
    )


def scorecard(report: Json, spec: list[str], brief: list[str] | None) -> str:
    out = ['<div class="sc-h"><span>Check</span><span>What the spec says</span><span>Result</span></div>']
    for result in ORDER:
        rows = [f for f in report["findings"] if f["result"] == result]
        if rows:
            out.append(f'<div class="sc-g">{esc(GROUPS[result])} · {len(rows)}</div>')
            out += [_row(f, spec, brief) for f in rows]
    return f'<div class="card"><div class="sc">{"".join(out)}</div></div>'


def brief_rows(report: Json, brief: list[str] | None, spec: list[str]) -> str:
    """The brief's parts as the parser read them, each with its line. Shown only when the brief parses."""
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
        ("Metric", b.metric, "metric", ""),
        ("Bar", f"{b.bar_text}, {'higher' if b.higher_is_better else 'lower'} is better, by {b.by}", "bar", ""),
        ("Non-goals", b.non_goals, "non_goals", ""),
        ("Cost budget", "Two lines in the brief. cost-budget-check owns the figures.", "tokens_per_task", ""),
        ("The line", f"{b.line}. {b.line_note}".strip(), "line", ""),
        ("Decides the next step", b.decides, "decides", "own"),
    )
    rows = "".join(
        f'<div class="kv"><span class="k">{esc(k)}</span><span class="{cls}">{esc(v)}</span><span class="l">{esc(refs([found[key]], where) if key in found else "-")}</span></div>'
        for k, v, key, cls in parts
    )
    return f'<div class="card">{rows}</div>'


def page(report: Json, lines: list[str], source: Json, brief: list[str] | None = None, illustrative: bool = False) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    c = report["counts"]
    title = source.get("title") or Path(report["spec"]).name
    verdict = report["verdict"]
    lede = (
        f"{c['hold']} check{'s' if c['hold'] != 1 else ''} hold this spec. Each names the lines it relies on and the fix. Notes are worth fixing and never block."
        if verdict == "hold"
        else "Every check that can hold a spec is met. Notes, if any, are worth fixing and never block."
    )
    where = source.get("location") or source.get("file") or report["spec"]
    brief_note = f" Brief: {report['brief']}." if report.get("brief") else ""
    ill = '<span class="ill">Illustrative</span>' if illustrative else ""
    notice = (
        f'<div class="notice">{ill}<span>Acme is an invented company. Every figure in this sample is illustrative.</span></div>'
        if illustrative
        else f'<div class="notice"><span>Spec: {esc(where)}.{esc(brief_note)}</span></div>'
    )
    facts = "".join(f'<span><b class="{key if key == "hold" and c[key] else ""}">{c[key]}</b>{label}</span>' for key, label in (("hold", "Hold"), ("note", "Note"), ("pass", "Pass")))
    hold_lines = sorted({(f.get("file", "spec"), n) for f in report["findings"] if f["result"] == "hold" for n in f["lines"]})
    cites = "".join(
        f'<div class="cite"><b>{esc(refs([n], file))}</b><span>{esc(_quote(n, brief if file == "brief" and brief is not None else lines))}</span></div>'
        for file, n in hold_lines
        if _quote(n, brief if file == "brief" and brief is not None else lines) and not _is_heading(n, brief if file == "brief" and brief is not None else lines)
    )
    brief_html = brief_rows(report, brief, lines)
    meta = f'<div class="meta"><span>Spec audit</span><span>As of {esc(report.get("as_of") or "not given")}</span><span>AI feature: {"yes" if report["ai_feature"] else "no"}</span></div>'
    slides = [
        f'<section class="slide" id="a1" data-act="Audit" data-nav="Verdict" data-aud="L">{meta}'
        f"<h2>{esc(title)}</h2>"
        f'<p class="lede"><span class="vd {esc(verdict)}">{esc(verdict)}</span></p><p class="lede">{esc(lede)}</p>'
        f'<div class="facts">{facts}</div></section>',
        f'<section class="slide" id="a2" data-act="Audit" data-nav="Findings" data-aud="L"><div class="meta"><span>Findings</span><span>{len(report["findings"])} checks</span></div>'
        f"<h2>What holds the spec, and the lines it rests on</h2>{scorecard(report, lines, brief)}</section>",
    ]
    if brief_html:
        slides.append(
            f'<section class="slide" id="a3" data-act="Audit" data-nav="The brief" data-aud="L"><div class="meta"><span>Landing brief</span><span>Read by landing_brief.py</span></div>'
            f"<h2>The brief the spec is checked against</h2>{brief_html}</section>"
        )
    if cites:
        slides.append(
            f'<section class="slide" id="a4" data-act="Audit" data-nav="Cited lines" data-aud="L"><div class="meta"><span>Evidence</span><span>In the spec&#39;s own words</span></div>'
            f'<h2>The lines the holds cite</h2><div class="card">{cites}</div></section>'
        )
    foot = (
        '<footer class="slide" style="min-height:0;padding-top:28px;padding-bottom:40px;border:0" data-skip>'
        f'<p class="t3" style="font-size:11.5px;margin:0">spec-auditor {esc(report["version"])}. Every check runs in code; line numbers refer to the text as read. '
        f"Source: {esc(where)}.{esc(brief_note)}</p></footer>"
    )
    body = "\n".join(
        [
            EXTRA_CSS,
            '<div class="bar"><span class="count">Landing Loop · step 2 of 5</span><span class="count" id="count" hidden></span>'
            '<label><input type="checkbox" id="g"> Show what each check needs</label></div>',
            notice,
            *slides,
            foot,
        ]
    )
    slots = (
        ("{{TITLE}}", esc(f"Spec audit: {title}")),
        ("{{DESCRIPTION}}", esc(f"spec-auditor {report['version']}: {verdict}, {c['hold']} hold, {c['note']} note, {c['pass']} pass.")),
        ("{{BRAND}}", "Dacard"),
        ("{{PRODUCT}}", "Spec auditor"),
        ("{{BODY}}", body),
    )
    for key, value in slots:
        template = template.replace(key, value, 1)
    return template


def md_cell(text: str) -> str:
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def markdown(report: Json, source: Json | None = None) -> str:
    c = report["counts"]
    source = source or {}
    ai = "yes" if report["ai_feature"] else "no"
    where = source.get("location") or source.get("file") or Path(report["spec"]).name
    brief = f" The brief is {md_cell(str(report['brief']))}." if report.get("brief") else ""
    out = [
        f"## Spec audit: **{report['verdict']}**",
        "",
        f"{c['hold']} hold, {c['note']} note, {c['pass']} pass. AI feature: {ai}. As of {report.get('as_of') or 'not given'}. Line numbers refer to {md_cell(str(where))}.{brief}",
        "",
        "| Result | Check | Lines | Finding | Fix |",
        "|---|---|---|---|---|",
    ]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        fix = f["fix"] if f["result"] != "pass" else ""
        out.append(f"| {f['result']} | {f['check']} | {refs(f['lines'], f.get('file', 'spec'))} | {md_cell(f['message'])} | {md_cell(fix)} |")
    return "\n".join(out) + "\n"
