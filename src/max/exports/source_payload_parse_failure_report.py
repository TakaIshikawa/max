"""Source payload parse failure export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_payload_parse_failure_report.v1"
KIND = "max.source_payload_parse_failure_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_payload_parse_failure_report(records: Iterable[dict[str, Any]], *, title: str = "Source Payload Parse Failure Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        source = _text(raw.get("source")) or "unknown-source"
        endpoint = _text(raw.get("endpoint") or raw.get("url")) or "unknown-endpoint"
        stage = _text(raw.get("parser_stage") or raw.get("stage")) or "parse"
        category = _category(raw.get("error_category") or raw.get("error") or raw.get("error_code"))
        key = (source, endpoint, stage, category)
        row = grouped.setdefault(key, {"source": source, "endpoint": endpoint, "parser_stage": stage, "error_category": category, "failed_count": 0, "sample_payload_reference": "", "first_seen_at": "", "last_seen_at": ""})
        row["failed_count"] += _int(raw.get("failed_count", raw.get("count", 1)))
        row["sample_payload_reference"] = row["sample_payload_reference"] or _text(raw.get("sample_payload_reference") or raw.get("sample_ref") or raw.get("payload_id"))
        ts = _text(raw.get("timestamp") or raw.get("seen_at") or raw.get("first_seen_at") or raw.get("last_seen_at"))
        row["first_seen_at"] = min([x for x in [row["first_seen_at"], ts] if x], default="")
        row["last_seen_at"] = max(row["last_seen_at"], ts)
    rows = list(grouped.values())
    for row in rows:
        row["remediation_hint"] = _hint(row["error_category"], row["parser_stage"])
    rows.sort(key=lambda row: (-row["failed_count"], row["last_seen_at"], row["source"].lower(), row["endpoint"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Payload Parse Failure Report", "summary": {"failed_count": sum(r["failed_count"] for r in rows), "row_count": len(rows), "source_count": len({r["source"] for r in rows})}, "failure_rows": rows}


def render_source_payload_parse_failure_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_payload_parse_failure_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Payload Parse Failure Report'}", "", "## Parse Failures", ""]
    lines.extend([f"- {r['source']} {r['endpoint']} {r['error_category']}: {r['failed_count']} failed" for r in report.get("failure_rows") or []] or ["- No parse failures detected."])
    return "\n".join(lines).rstrip() + "\n"


def _category(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_")
    if "json" in text:
        return "json_decode"
    if "schema" in text or "field" in text:
        return "schema_validation"
    if "timeout" in text:
        return "timeout"
    return text or "parse_error"


def _hint(category: str, stage: str) -> str:
    return f"review {stage} handling for {category}"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
