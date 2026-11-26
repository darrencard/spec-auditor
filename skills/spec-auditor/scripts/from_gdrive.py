#!/usr/bin/env python3
"""Turn a Google Drive file list into the docs source: document, kind, updated_at, location.

Usage:
  python3 scripts/from_gdrive.py --files files.json --kind "risk register" --drive acme --run run

Input: Drive API v3 files.list results, or the Claude Google Drive connector's search_files or
list_recent_files results, saved as they stand, one file per page ({"files": [...], "nextPageToken": ...}).
The API names a file's title and link `name` and `webViewLink`; the connector names them `title` and
`viewUrl`. Both are read. From the API, ask for fields
nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink); without them Drive returns only id,
name and mimeType, and updated_at and location stay empty.

--kind says what the documents are; it is the user's word, applied to every file in the run.
Trashed files and folders are left out. To quote a document in an `intake.py propose` draft, export or
download it as text or Markdown first and quote that file word for word.

This script reads files and writes a file. It makes no network calls.

Standard library only. Runs on Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect  # noqa: E402  (sibling scripts, found through the path above)
import convert  # noqa: E402

TOOL = "from_gdrive"
FOLDER = "application/vnd.google-apps.folder"


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn a Google Drive file list into the docs source.")
    ap.add_argument("--files", nargs="+", required=True, help="files.list results as Drive returns them, one file per page")
    ap.add_argument("--kind", required=True, help="what these documents are, for example strategy or risk register")
    ap.add_argument("--drive", required=True, help="the drive or folder, for the ledger")
    ap.add_argument("--retrieved-at", help="YYYY-MM-DD; defaults to the first file's modified date")
    ap.add_argument("--run", default="run")
    args = ap.parse_args()
    rows = []
    for f in convert.pages(args.files, TOOL, "files"):
        # The Drive API says name and webViewLink; the Claude Drive connector says title and viewUrl.
        title = f.get("name") or f.get("title")
        if f.get("trashed") or f.get("mimeType") == FOLDER or not title:
            continue
        modified = convert.when(f.get("modifiedTime"))
        link = f.get("webViewLink") or f.get("viewUrl") or ""
        rows.append({"document": title, "kind": args.kind, "updated_at": modified.isoformat() if modified else "", "location": link})
    if not rows:
        raise convert.fail(TOOL, "found no files. The docs source stays Unknown; no file was written.")
    what = "Google Drive file list (title, modifiedTime, link)"
    out = convert.write(
        "docs",
        rows,
        f"Google Drive ({args.drive})",
        what,
        collect.retrieved_date(args.retrieved_at, args.files[0]),
        Path(args.files[0]).name,
        args.run,
        keep_other="document",
    )
    print(f"{TOOL}: {len(rows)} document(s) of kind {args.kind}, written to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
