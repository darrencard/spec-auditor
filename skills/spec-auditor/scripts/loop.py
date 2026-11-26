"""The spec key of the Landing Loop record, landing/<bet>.json (plans/landing-loop-contract-2026-11.md, schema landing-loop/1).

spec-auditor writes only the `spec` key and keeps every other key exactly as it found it. A new record gets the schema,
the bet and the brief (the spec file's path and SHA-256), because the spec is where the brief is read; an existing
record's brief is never changed. Every figure carries value, unit, source, window (from, to) and as_of. The verdict
is pass or hold, set in code; no status word (landed, watch, stalled) is written here, because the spec is not shipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import landing_brief

SCHEMA = "landing-loop/1"
CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
Json = dict[str, Any]


class LoopError(ValueError):
    """A loop record that cannot be written without breaking another skill's key."""


def figure(value: float | int, unit: str, source: str, start: str, end: str, as_of: str) -> Json:
    return {"value": value, "unit": unit, "source": source, "window": {"from": start, "to": end}, "as_of": as_of}


def brief_figures(text: str, where: str, lines: dict[str, int], as_of: str) -> Json:
    """The brief's bar as a figure, sourced to its line. Empty when the brief does not parse. The cost budget is left
    out on purpose: cost-budget-check owns tokens per task and price per token (contract, one owner per figure)."""
    try:
        b = landing_brief.parse(text)
    except landing_brief.BriefError:
        return {}

    def src(key: str) -> str:
        return f"{where}, line {lines[key]}" if key in lines else where

    out: Json = {
        "metric": b.metric,
        "better": "higher" if b.higher_is_better else "lower",
        "by": b.by,
        "line": b.line,
        "decides": b.decides,
        "bar": figure(b.bar, " ".join(x for x in (CURRENCY.get(b.prefix, b.prefix), b.unit) if x) or "number", src("bar"), as_of, b.by, as_of),
    }
    return out


def spec_key(report: Json, source: Json, brief: Json, as_of: str) -> Json:
    where = source.get("location") or source.get("file") or report["spec"]
    tool = f"spec-auditor {report['version']}, audit of {where}"
    counts = {r: figure(report["counts"][r], "findings", tool, as_of, as_of, as_of) for r in ("hold", "note", "pass")}
    return {
        "tool": "spec-auditor",
        "version": report["version"],
        "as_of": as_of,
        "source": source,
        "verdict": report["verdict"],
        "ai_feature": report["ai_feature"],
        "counts": counts,
        "brief": brief,
        "holds": [{"check": f["check"], "lines": f["lines"], "message": f["message"], "fix": f["fix"]} for f in report["findings"] if f["result"] == "hold"],
        "notes": [{"check": f["check"], "lines": f["lines"], "message": f["message"]} for f in report["findings"] if f["result"] == "note"],
    }


def write(folder: Path, bet: str, spec: Json, spec_file: Path) -> Path:
    """Set the spec key of folder/<bet>.json, keeping every other key as it was. Written atomically."""
    if not SLUG.match(bet):
        raise LoopError(f"the bet slug {bet!r} must be lower-case letters, digits and hyphens, such as quote-drafting-assistant.")
    path = folder / f"{bet}.json"
    if path.exists():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise LoopError(f"cannot read {path} ({e}). Nothing was written; fix or move the file first.") from None
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            raise LoopError(f"{path} is not a {SCHEMA} record. Nothing was written.")
        if record.get("bet") != bet:
            raise LoopError(f"{path} is for the bet {record.get('bet')!r}, not {bet!r}. Nothing was written.")
    else:
        record = {"schema": SCHEMA, "bet": bet, "brief": {"path": str(spec_file), "sha256": hashlib.sha256(spec_file.read_bytes()).hexdigest()}}
    record["spec"] = spec
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{bet}.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return path
