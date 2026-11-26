"""Write fixtures/acme-good-spec-gdocs.html from fixtures/acme-good-spec.md, in the shape of a Google Docs "Web page" export.

Run: python3 evals/make_html_fixture.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent / "fixtures"
HEAD = (
    '<html><head><meta content="text/html; charset=UTF-8" http-equiv="content-type">'
    '<style type="text/css">.c1{font-weight:700}.c2{color:#000000}</style><title>Quote drafts from job notes</title></head>'
    '<body class="c2 doc-content">'
)


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r'<span class="c1">\1</span>', text)
    text = re.sub(r"`(.+?)`", r"<span>\1</span>", text)
    return f'<span class="c2">{text}</span>'


def convert(md: str) -> str:
    out, open_list = [HEAD], None
    for line in md.splitlines():
        head = re.match(r"^(#+)\s+(.*)", line)
        item = re.match(r"^(?:-|\d+\.)\s+(.*)", line)
        if open_list and not item:
            out.append(f"</{open_list}>")
            open_list = None
        if head:
            n = len(head.group(1))
            out.append(f'<h{n} class="c2"><span>{html.escape(head.group(2))}</span></h{n}>')
        elif item:
            if not open_list:
                open_list = "ol" if line[0].isdigit() else "ul"
                out.append(f'<{open_list} class="lst-kix_list_1-0 start">')
            out.append(f'<li class="c2 li-bullet-0">{inline(item.group(1))}</li>')
        elif line.strip():
            out.append(f'<p class="c2">{inline(line)}</p>')
        else:
            out.append('<p class="c2"><span class="c2"></span></p>')
    if open_list:
        out.append(f"</{open_list}>")
    out.append("</body></html>")
    return "".join(out) + "\n"


if __name__ == "__main__":
    (HERE / "acme-good-spec-gdocs.html").write_text(convert((HERE / "acme-good-spec.md").read_text(encoding="utf-8")), encoding="utf-8")
