"""The audit as one self-contained HTML page in the Leader Report style guide, and its Markdown twin.

The page takes its fonts, colours and type from assets/template.html (vendored unchanged from the Leader Report) and
follows its references/design.md: mono capital labels, hairline rows, one frame for cards side by side, colour for
meaning only. Green, grey-white and red are kept for landed, watch and stalled, so this page does not use them: a
hold is brass, because the spec's owner owes a fix; a pass is ink; a note is a dashed chip. Every piece of spec text
is escaped. Nothing here computes a figure; the counts come from the report.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.html"
ORDER = ("hold", "note", "pass")
HEAD = "<tr><th>Result</th><th>Check</th><th>Lines</th><th>Finding</th><th>Fix</th></tr>"
Json = dict[str, Any]

EXTRA_CSS = """
.page{max-width:1120px;margin:0 auto;padding:56px 40px 64px}
.page section{margin-top:44px}
.page .grid{margin-bottom:8px}
.chip.hold{color:var(--brass);border-color:var(--brass);background:var(--brass-bg)}
.chip.pass{color:var(--t1);border-color:var(--line3)}
.chip.note{border-style:dashed;color:var(--t2)}
.verdict{display:inline-block;font:400 12px/20px var(--mono);letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--line3);border-radius:4px;padding:2px 10px;color:var(--t1)}
.verdict.hold{color:var(--brass);border-color:var(--brass);background:var(--brass-bg)}
td.lines{font:400 11.5px var(--mono);white-space:nowrap;color:var(--t2)}
.cite{font:400 12px/1.6 var(--mono);color:var(--t2);white-space:pre-wrap;word-break:break-word}
.cite b{color:var(--t3);font-weight:400;margin-right:12px}
.foot{font:400 10px/18px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--t3);margin-top:48px;border-top:1px solid var(--line);padding-top:16px}
@media (max-width:760px){.page{padding:28px 16px 40px}.g3{grid-template-columns:1fr}.tablewrap td,.tablewrap th{padding:10px 12px}}
"""


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def style() -> str:
    """The template's own style block: fonts, tokens and type, as the Leader Report ships them."""
    found = re.search(r"<style>(.*?)</style>", TEMPLATE.read_text(encoding="utf-8"), re.S)
    if not found:
        raise RuntimeError(f"{TEMPLATE} has no <style> block. Copy it again from the Leader Report.")
    return found.group(1)


def refs(lines: list[int]) -> str:
    return ("L" + ", L".join(str(n) for n in lines)) if lines else "-"


def page(report: Json, lines: list[str], source: Json) -> str:
    c = report["counts"]
    title = source.get("title") or Path(report["spec"]).name
    rows = []
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        fix = esc(f["fix"]) if f["result"] != "pass" else ""
        rows.append(
            f'<tr><td><span class="chip {f["result"]}">{f["result"]}</span></td><td class="mono">{esc(f["check"])}</td>'
            f'<td class="lines">{refs(f["lines"])}</td><td>{esc(f["message"])}</td><td>{fix}</td></tr>'
        )
    cited = sorted({n for f in report["findings"] if f["result"] == "hold" for n in f["lines"] if 1 <= n <= len(lines)})
    cite = "".join(f'<div class="cite"><b>L{n}</b>{esc(lines[n - 1].strip()[:240])}</div>' for n in cited if lines[n - 1].strip())
    where = source.get("location") or source.get("file") or report["spec"]
    reads = source.get("leader_report_reads_brief")
    reads_line = "" if reads is None else f" · Leader Report reads the brief: {'yes' if reads else 'no'}"
    tiles = "".join(
        f'<div class="card"><h3>{label}</h3><div class="big">{c[key]}</div><div class="sub">{sub}</div></div>'
        for key, label, sub in (
            ("hold", "Hold", "Block the spec until it changes"),
            ("note", "Note", "Worth fixing; never block"),
            ("pass", "Pass", "Checks met"),
        )
    )
    lede = (
        f"{c['hold']} finding{'s' if c['hold'] != 1 else ''} hold this spec. Each names the lines it relies on and the fix."
        if report["verdict"] == "hold"
        else "Every check that can hold a spec is met. Notes, if any, are worth fixing and do not block."
    )
    ai = "yes" if report["ai_feature"] else "no"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spec audit: {esc(title)}</title>
<meta name="description" content="spec-auditor {esc(report["version"])}: {esc(report["verdict"])}, {c["hold"]} hold, {c["note"]} note, {c["pass"]} pass.">
<style>{style()}{EXTRA_CSS}</style>
</head>
<body>
<div class="page">
<div class="meta"><span>Spec audit</span><span>{esc(source.get("kind", "file"))}</span><span>As of {esc(report.get("as_of") or "not given")}</span><span>AI feature: {ai}</span></div>
<h2>{esc(title)}</h2>
<p class="lede"><span class="verdict {esc(report["verdict"])}">{esc(report["verdict"])}</span> {esc(lede)}</p>
<div class="grid g3">{tiles}</div>
<section><h3>Findings</h3><div class="tablewrap"><table><thead>{HEAD}</thead><tbody>{"".join(rows)}</tbody></table></div></section>
{f'<section><h3>The lines the holds cite</h3><div class="card">{cite}</div></section>' if cite else ""}
<div class="foot">spec-auditor {esc(report["version"])} · source: {esc(where)}{esc(reads_line)} · every check runs in code; line numbers refer to the spec text as read</div>
</div>
</body>
</html>
"""


def md_cell(text: str) -> str:
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def markdown(report: Json, source: Json | None = None) -> str:
    c = report["counts"]
    source = source or {}
    ai = "yes" if report["ai_feature"] else "no"
    where = source.get("location") or source.get("file") or Path(report["spec"]).name
    out = [
        f"## Spec audit: **{report['verdict']}**",
        "",
        f"{c['hold']} hold, {c['note']} note, {c['pass']} pass. AI feature: {ai}. As of {report.get('as_of') or 'not given'}. Line numbers refer to {md_cell(str(where))}.",
        "",
        "| Result | Check | Lines | Finding | Fix |",
        "|---|---|---|---|---|",
    ]
    for f in sorted(report["findings"], key=lambda f: ORDER.index(f["result"])):
        fix = f["fix"] if f["result"] != "pass" else ""
        out.append(f"| {f['result']} | {f['check']} | {refs(f['lines'])} | {md_cell(f['message'])} | {md_cell(fix)} |")
    return "\n".join(out) + "\n"
