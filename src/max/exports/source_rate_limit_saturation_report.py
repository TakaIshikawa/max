"""Source rate-limit saturation export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_rate_limit_saturation_report.v1"
KIND = "max.source_rate_limit_saturation_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_rate_limit_saturation_report(records: Iterable[dict[str, Any]], *, threshold_percent: float = 20.0, title: str = "Source Rate Limit Saturation Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = [_row(raw, threshold_percent) for raw in records if isinstance(raw, dict)]
    rows.sort(key=lambda row: (-row["saturation_percent"], row["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Rate Limit Saturation Report", "summary": {"source_count": len(rows), "limited_request_count": sum(r["limited_requests"] for r in rows), "requests_attempted": sum(r["requests_attempted"] for r in rows), "over_threshold_count": sum(1 for r in rows if r["over_threshold"])}, "saturation_rows": rows}


def render_source_rate_limit_saturation_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_rate_limit_saturation_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Rate Limit Saturation Report'}", "", "## Saturation", ""]
    lines.extend([f"- {r['source']} {r['window']}: {r['saturation_percent']}% limited ({r['allocation_recommendation']})" for r in report.get("saturation_rows") or []] or ["- No rate-limit saturation rows."])
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], threshold: float) -> dict[str, Any]:
    attempted = _int(raw.get("requests_attempted", raw.get("attempted", 0)))
    limited = _int(raw.get("limited_requests", raw.get("rate_limited", 0)))
    percent = round((limited / attempted * 100.0) if attempted else 0.0, 2)
    return {"source": _text(raw.get("source")) or "unknown-source", "adapter": _text(raw.get("adapter")) or "unknown-adapter", "window": _text(raw.get("window")) or "unknown-window", "requests_attempted": attempted, "limited_requests": limited, "saturation_percent": percent, "retry_after_seconds": _int(raw.get("retry_after_seconds", raw.get("retry_after_total", 0))), "over_threshold": percent >= threshold, "allocation_recommendation": "throttle requests or allocate additional credentials" if percent >= threshold else "keep current allocation"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
