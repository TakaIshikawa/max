"""Source adapter retry jitter export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_retry_jitter_report.v1"
KIND = "max.source_adapter_retry_jitter_report"
STATUS_RANK = {"missing_jitter": 0, "low_jitter": 1, "excessive_retry": 2, "healthy": 3}


def generate_source_adapter_retry_jitter_report(
    records: Iterable[dict[str, Any]],
    *,
    excessive_retry_count: int = 5,
    minimum_jitter_span_ms: int = 100,
) -> dict[str, Any]:
    rows = [_row(raw, index, excessive_retry_count, minimum_jitter_span_ms) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["status_rank"], -row["retry_count"], row["source"].casefold()))
    for row in rows:
        row.pop("status_rank", None)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "adapter_rows": rows}


def render_source_adapter_retry_jitter_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def render_source_adapter_retry_jitter_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source Adapter Retry Jitter Report",
        "",
        f"- Adapters: {report['summary']['adapter_count']}",
        f"- Risky adapters: {report['summary']['risky_adapter_count']}",
        f"- Missing jitter: {report['summary']['missing_jitter_count']}",
        f"- Excessive retry: {report['summary']['excessive_retry_count']}",
        "",
    ]
    for row in report.get("adapter_rows", []):
        lines.append(f"- {row['source']}: {row['status']} ({row['retry_count']} retries, {row['jitter_span_ms']} ms jitter span)")
    return "\n".join(lines)


def _row(raw: dict[str, Any], index: int, excessive_retry_count: int, minimum_jitter_span_ms: int) -> dict[str, Any]:
    retry_count = _int(raw.get("retry_count") or raw.get("retries"))
    min_delay = _int(raw.get("min_delay_ms") or raw.get("minimum_delay_ms"))
    max_delay = _int(raw.get("max_delay_ms") or raw.get("maximum_delay_ms"))
    observed_delay = _int(raw.get("observed_delay_ms") or raw.get("delay_ms"))
    jitter_enabled = _bool(raw.get("jitter_enabled") if "jitter_enabled" in raw else raw.get("jitter"))
    jitter_span = max(max_delay - min_delay, 0)
    status = _status(retry_count, jitter_enabled, jitter_span, excessive_retry_count, minimum_jitter_span_ms)
    return {
        "source": _text(raw.get("source") or raw.get("adapter") or raw.get("adapter_name")) or f"source-{index}",
        "retry_count": retry_count,
        "min_delay_ms": min_delay,
        "max_delay_ms": max_delay,
        "observed_delay_ms": observed_delay,
        "jitter_enabled": jitter_enabled,
        "jitter_span_ms": jitter_span,
        "synchronized_retry": retry_count > 0 and jitter_span < minimum_jitter_span_ms,
        "status": status,
        "status_rank": STATUS_RANK[status],
    }


def _status(retry_count: int, jitter_enabled: bool, jitter_span: int, excessive_retry_count: int, minimum_jitter_span_ms: int) -> str:
    if retry_count > 0 and not jitter_enabled:
        return "missing_jitter"
    if retry_count > 0 and jitter_span < minimum_jitter_span_ms:
        return "low_jitter"
    if retry_count >= excessive_retry_count:
        return "excessive_retry"
    return "healthy"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "adapter_count": len(rows),
        "risky_adapter_count": sum(1 for row in rows if row["status"] != "healthy"),
        "missing_jitter_count": sum(1 for row in rows if row["status"] == "missing_jitter"),
        "excessive_retry_count": sum(1 for row in rows if row["status"] == "excessive_retry"),
        "low_jitter_count": sum(1 for row in rows if row["status"] == "low_jitter"),
    }


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
