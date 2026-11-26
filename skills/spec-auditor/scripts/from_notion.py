#!/usr/bin/env python3
"""Turn Notion pages into the docs source: document, kind, updated_at, location.

Usage:
  python3 scripts/from_notion.py --pages search.json --kind strategy --workspace acme --run run
  python3 scripts/from_notion.py --markdown run/notion-export --kind "decision log" --workspace acme --run run

Inputs, saved as they stand:
  --pages     page objects from the Notion API (GET /v1/pages/{id}, or search or data source query
              results with {"results": [...]}), or the Notion connector. The title is the property
              whose type is title; updated_at is last_edited_time; location is the page url.
  --markdown  a folder from Notion's "Export as Markdown & CSV". Each .md file is a document; its
              title is its first "# " heading, or the file name. The export does not record when a
              page was last edited, so updated_at is left empty.

--kind says what the documents are (strategy, decision log, risk register, roadmap, ...). It is the
user's word, applied to every document in the run; the script does not classify pages.

The same Markdown export is what the agent quotes in `intake.py propose` drafts: each proposal's source
is the exported file and heading, and its quote must appear in that file word for word. Nothing is
inferred from a page.

This script reads files and writes a file. It makes no network calls.

Standard library only. Runs on Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect  # noqa: E402  (sibling scripts, found through the path above)
import convert  # noqa: E402

TOOL = "from_notion"


def title_of(page: dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title") or []).strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn Notion pages into the docs source.")
    given = ap.add_mutually_exclusive_group(required=True)
    given.add_argument("--pages", nargs="+", help="page objects or search results as the Notion API returns them")
    given.add_argument("--markdown", help="a folder from Notion's Export as Markdown & CSV")
    ap.add_argument("--kind", required=True, help="what these documents are, for example strategy or decision log")
    ap.add_argument("--workspace", required=True, help="the Notion workspace, for the ledger")
    ap.add_argument("--retrieved-at", help="YYYY-MM-DD; defaults to the first file's modified date")
    ap.add_argument("--run", default="run")
    args = ap.parse_args()
    rows, untitled = [], 0
    if args.pages:
        for p in convert.pages(args.pages, TOOL, "results"):
            if p.get("object", "page") != "page" or p.get("in_trash") or p.get("archived"):
                continue
            title = title_of(p)
            if not title:
                untitled += 1
                continue
            edited = convert.when(p.get("last_edited_time"))
            rows.append({"document": title, "kind": args.kind, "updated_at": edited.isoformat() if edited else "", "location": p.get("url") or ""})
        origin, what = args.pages[0], "Notion API page objects (title, last_edited_time, url)"
    else:
        folder = Path(args.markdown)
        files = sorted(folder.rglob("*.md")) if folder.is_dir() else []
        if not files:
            raise convert.fail(TOOL, f"{folder} holds no .md files. Unzip Notion's Markdown export there first.")
        for f in files:
            lines = f.read_text(encoding="utf-8").splitlines()
            heading = next((x[2:].strip() for x in lines if x.startswith("# ")), "")
            rows.append({"document": heading or f.stem, "kind": args.kind, "updated_at": "", "location": str(f.relative_to(folder))})
        origin, what = str(files[0]), "Notion Markdown export (title from the first heading; no edit dates in the export)"
    if untitled:
        print(f"{TOOL}: {untitled} page(s) have no title and are left out.")
    if not rows:
        raise convert.fail(TOOL, "found no pages. The docs source stays Unknown; no file was written.")
    out = convert.write(
        "docs", rows, f"Notion ({args.workspace})", what, collect.retrieved_date(args.retrieved_at, origin), Path(origin).name, args.run, keep_other="document"
    )
    print(f"{TOOL}: {len(rows)} document(s) of kind {args.kind}, written to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
