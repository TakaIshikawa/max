"""Source field completeness export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_field_completeness_report.v1"
KIND = "max.source_field_completeness_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_field_completeness_report(records: Iterable[dict[str, Any]], *, fields: Iterable[dict[str, Any]], threshold_percent: float = 95.0, title: str = "Source Field Completeness Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    configs = [_field(f) for f in fields]
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"total": 0, "populated": 0})
    for raw in records:
        if not isinstance(raw, dict):
            continue
        source = _text(raw.get("source")) or "unknown-source"
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        for config in configs:
            slot = counts[(source, config["field_name"])]
            slot["total"] += 1
            if _present(payload.get(config["field_name"])):
                slot["populated"] += 1
    rows = []
    for source, field in sorted(counts):
        config = next(c for c in configs if c["field_name"] == field)
        total = counts[(source, field)]["total"]
        populated = counts[(source, field)]["populated"]
        missing = max(total - populated, 0)
        percent = round((populated / total * 100.0) if total else 0.0, 2)
        status = "blocker" if config["required"] and percent < threshold_percent else "warning" if percent < threshold_percent else "healthy"
        rows.append({"source": source, "field_name": field, "required": config["required"], "populated_count": populated, "missing_count": missing, "completeness_percent": percent, "status": status, "ingestion_quality_recommendation": _recommendation(status, field)})
    rows.sort(key=lambda r: (r["source"].lower(), r["completeness_percent"], r["field_name"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Field Completeness Report", "summary": {"row_count": len(rows), "blocker_count": sum(1 for r in rows if r["status"] == "blocker"), "warning_count": sum(1 for r in rows if r["status"] == "warning")}, "completeness_rows": rows}


def render_source_field_completeness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_field_completeness_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Field Completeness Report'}", "", "## Field Completeness", ""]
    lines.extend([f"- {r['source']} {r['field_name']}: {r['completeness_percent']}% {r['status']}" for r in report.get("completeness_rows") or []] or ["- No field completeness rows."])
    return "\n".join(lines).rstrip() + "\n"


def _field(raw: dict[str, Any]) -> dict[str, Any]:
    return {"field_name": _text(raw.get("field_name") or raw.get("name") or raw.get("field")) or "unknown_field", "required": bool(raw.get("required"))}


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _recommendation(status: str, field: str) -> str:
    if status == "blocker":
        return f"block ingestion release until required field {field} is populated"
    if status == "warning":
        return f"improve optional field {field} enrichment"
    return "no action needed"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
