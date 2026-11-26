"""Where a spec comes from: Linear, Notion, Google Drive, or a file. Each returns the spec's text and a source record.

Live data first. The agent fetches the spec with the connector in its session and saves the response as it stands;
this module reads that file with the Leader Report's own readers (from_linear.py, from_notion.py, from_gdrive.py and
convert.py, vendored unchanged at the commit in VENDORED.json). A Markdown or text file is the fallback.

  linear   the project as Linear returns it (get_project, list_projects, or the GraphQL API). The spec is the
           project's content and description. --project picks one when the file holds several.
  notion   the page text (the connector's fetch result, or one file from "Export as Markdown & CSV"), with
           --meta for the page object, which gives the title, the url and last_edited_time.
  gdrive   the file's text (the connector's read_file_content result, or a download as .md, .txt or .html), with
           --meta for the file object or files.list page, which gives the name, the link and modifiedTime.
  file     a Markdown, text or HTML file. Its modified time is when it was last changed.

This module reads files. It makes no network calls.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import convert
import from_gdrive
import from_linear
import from_notion

KINDS = ("file", "linear", "notion", "gdrive")
Json = dict[str, Any]


class SourceError(ValueError):
    """A source that cannot be read as a spec."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SourceError(f"cannot read {path} as JSON ({e}). Save the connector's response as it stands.") from None


def _text(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise SourceError(f"cannot read {path} ({e}). Save the spec as UTF-8 Markdown, text or HTML.") from None
    if path.suffix.lower() == ".json":
        # A connector result saved as JSON: the text sits under a content, text or markdown field.
        data = _json(path)
        for key in ("content", "text", "markdown", "body"):
            if isinstance(data, dict) and isinstance(data.get(key), str):
                return data[key]
        raise SourceError(f"{path} is JSON with no content, text or markdown field. Save the page text itself.")
    return raw


def _iso(value: Any) -> str:
    moment = convert.when(value)
    return moment.date().isoformat() if moment else ""


def _modified(path: Path) -> str:
    return datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.UTC).date().isoformat()


def linear(path: Path, project: str | None = None) -> tuple[str, Json]:
    data = _json(path)
    single = data.get("project") if isinstance(data, dict) and isinstance(data.get("project"), dict) else None
    if single is None and isinstance(data, dict) and ("description" in data or "content" in data) and "name" in data:
        single = data
    if single is not None:
        found = [single]
    else:
        try:
            found = from_linear.read_items([path], ("projects", "nodes"), "projects")
        except SystemExit as e:
            raise SourceError(str(e)) from None
    if project:
        found = [p for p in found if (from_linear.name_of(p) or "").strip().lower() == project.strip().lower()]
    if len(found) != 1:
        names = ", ".join(sorted(from_linear.name_of(p) or "(no name)" for p in found)[:8])
        raise SourceError(f"{path} holds {len(found)} matching projects{f' ({names})' if names else ''}. Pass --project NAME for one.")
    p = found[0]
    text = "\n".join(p[k] for k in ("content", "description") if isinstance(p.get(k), str))
    if not text.strip():
        raise SourceError(f"the project {from_linear.name_of(p)!r} has no description or content.")
    brief, why = from_linear.brief_of(p)
    return text, {
        "kind": "linear",
        "title": from_linear.name_of(p) or "",
        "location": p.get("url") or "",
        "updated_at": _iso(p.get("updatedAt")),
        "file": str(path),
        "leader_report_reads_brief": brief is not None,
        "leader_report_note": why,
    }


def _meta_item(meta: Path | None, keys: tuple[str, ...]) -> Json:
    if meta is None:
        return {}
    data = _json(meta)
    listed = convert.items(data, *keys)
    if listed is None:
        return data if isinstance(data, dict) else {}
    if len(listed) != 1:
        raise SourceError(f"{meta} lists {len(listed)} items. Save the one for this spec.")
    return listed[0]


def notion(path: Path, meta: Path | None = None) -> tuple[str, Json]:
    page = _meta_item(meta, ("results",))
    text = _text(path)
    heading = next((x[2:].strip() for x in text.splitlines() if x.startswith("# ")), "")
    return text, {
        "kind": "notion",
        "title": from_notion.title_of(page) or heading or path.stem,
        "location": page.get("url") or "",
        "updated_at": _iso(page.get("last_edited_time")),
        "file": str(path),
    }


def gdrive(path: Path, meta: Path | None = None) -> tuple[str, Json]:
    item = _meta_item(meta, ("files",))
    if item.get("mimeType") == from_gdrive.FOLDER:
        raise SourceError(f"{meta} is a folder, not a document.")
    return _text(path), {
        "kind": "gdrive",
        # The Drive API says name and webViewLink; the Claude Drive connector says title and viewUrl (as from_gdrive.py reads them).
        "title": item.get("name") or item.get("title") or path.stem,
        "location": item.get("webViewLink") or item.get("viewUrl") or "",
        "updated_at": _iso(item.get("modifiedTime")),
        "file": str(path),
    }


def local(path: Path) -> tuple[str, Json]:
    text = _text(path)
    heading = next((x[2:].strip() for x in text.splitlines() if x.startswith("# ")), "")
    return text, {"kind": "file", "title": heading or path.stem, "location": str(path), "updated_at": _modified(path), "file": str(path)}


def load(kind: str, path: Path, meta: Path | None = None, project: str | None = None) -> tuple[str, Json]:
    if kind == "linear":
        return linear(path, project)
    if kind == "notion":
        return notion(path, meta)
    if kind == "gdrive":
        return gdrive(path, meta)
    return local(path)
