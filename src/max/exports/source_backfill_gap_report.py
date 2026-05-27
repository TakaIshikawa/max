"""Source backfill gap export report."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "max.source_backfill_gap_report.v1"
KIND = "max.source_backfill_gap_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_backfill_gap_report(records: list[dict[str, Any]] | dict[str, Any], *, title: str = "Source Backfill Gap Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    source = records.get("sources") if isinstance(records, dict) else records
    rows = []
    for raw in source or []:
        missing = _missing(_text(raw.get("expected_start")), _text(raw.get("expected_end")), raw.get("observed_windows") or [])
        for start, end in missing:
            hours = round((_parse(end) - _parse(start)).total_seconds() / 3600, 2)
            rows.append({"source": _text(raw.get("source")) or "unknown-source", "expected_window": f"{_text(raw.get('expected_start'))}/{_text(raw.get('expected_end'))}", "observed_coverage": len(raw.get("observed_windows") or []), "missing_interval": f"{start}/{end}", "gap_duration_hours": hours, "priority": _priority(hours, _text(raw.get("importance"))), "suggested_backfill_command": {"source": _text(raw.get("source")) or "unknown-source", "start": start, "end": end}})
    rows.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}[r["priority"]], -r["gap_duration_hours"], r["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Backfill Gap Report", "summary": {"gap_count": len(rows), "source_count": len({r["source"] for r in rows}), "gap_duration_hours": round(sum(r["gap_duration_hours"] for r in rows), 2)}, "gap_rows": rows}


def render_source_backfill_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_backfill_gap_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Backfill Gap Report'}", "", "## Backfill Gaps", ""]
    lines.extend([f"- {r['source']} {r['missing_interval']}: {r['gap_duration_hours']}h {r['priority']}" for r in report.get("gap_rows") or []] or ["- No backfill gaps detected."])
    return "\n".join(lines).rstrip() + "\n"


def _missing(start: str, end: str, observed: list[dict[str, Any]]) -> list[tuple[str, str]]:
    gaps = [(start, end)] if start and end else []
    for window in sorted(observed, key=lambda w: _text(w.get("start"))):
        ws, we = _text(window.get("start")), _text(window.get("end"))
        next_gaps = []
        for gs, ge in gaps:
            if not ws or not we or we <= gs or ws >= ge:
                next_gaps.append((gs, ge))
            else:
                if gs < ws:
                    next_gaps.append((gs, ws))
                if we < ge:
                    next_gaps.append((we, ge))
        gaps = next_gaps
    return gaps


def _priority(hours: float, importance: str) -> str:
    if importance.lower() == "critical" or hours >= 24:
        return "high"
    if hours >= 4:
        return "medium"
    return "low"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
