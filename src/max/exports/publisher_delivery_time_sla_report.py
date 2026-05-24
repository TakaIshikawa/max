"""Publisher delivery time SLA export report."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.publisher_delivery_time_sla_report.v1"
KIND = "max.publisher_delivery_time_sla_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class PublisherDeliveryInput(TypedDict, total=False):
    artifact_id: str
    destination: str
    requested_at: str
    completed_at: str
    sla_minutes: int | float | str


def build_publisher_delivery_time_sla_report(
    records: Iterable[PublisherDeliveryInput | dict[str, Any]],
    *,
    as_of: str = DEFAULT_GENERATED_AT,
    title: str = "Publisher Delivery Time SLA Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = [_row(raw, index, as_of) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "met", -row["breach_minutes"], row["destination"].lower(), row["artifact_id"].lower()))
    deliveries = [row["delivery_minutes"] for row in rows]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Publisher Delivery Time SLA Report",
        "as_of": _text(as_of) or DEFAULT_GENERATED_AT,
        "summary": {
            "delivery_count": len(rows),
            "average_delivery_minutes": round(sum(deliveries) / len(deliveries), 2) if deliveries else 0.0,
            "p95_delivery_minutes": _percentile(deliveries, 0.95),
            "breach_count": sum(1 for row in rows if row["status"] == "breached"),
            "destination_summaries": _destination_summaries(rows),
        },
        "delivery_rows": rows,
        "sla_breaches": [row for row in rows if row["status"] == "breached"],
    }


def render_publisher_delivery_time_sla_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publisher_delivery_time_sla_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([
        f"# {report.get('title') or 'Publisher Delivery Time SLA Report'}",
        "",
        "## Summary",
        "",
        f"- Deliveries: {summary.get('delivery_count', 0)}",
        f"- Breaches: {summary.get('breach_count', 0)}",
    ]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int, as_of: str) -> dict[str, Any]:
    requested = _text(raw.get("requested_at"))
    completed = _text(raw.get("completed_at"))
    delivery = _minutes(requested, completed or as_of)
    sla = _float(raw.get("sla_minutes"), 60.0)
    return {
        "artifact_id": _text(raw.get("artifact_id") or raw.get("id")) or f"unknown-artifact-{index}",
        "destination": _text(raw.get("destination")) or "Unknown destination",
        "requested_at": requested,
        "completed_at": completed,
        "delivery_minutes": round(delivery, 2),
        "sla_minutes": round(sla, 2),
        "breach_minutes": round(max(delivery - sla, 0.0), 2),
        "status": "breached" if delivery > sla else "met",
    }


def _destination_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for destination in sorted({row["destination"] for row in rows}, key=str.casefold):
        subset = [row for row in rows if row["destination"] == destination]
        result.append({
            "destination": destination,
            "delivery_count": len(subset),
            "breach_count": sum(1 for row in subset if row["status"] == "breached"),
            "average_delivery_minutes": round(sum(row["delivery_minutes"] for row in subset) / len(subset), 2),
        })
    return result


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def _minutes(start: Any, end: Any) -> float:
    started = _parse_time(start)
    ended = _parse_time(end)
    if not started or not ended:
        return 0.0
    return max(0.0, (ended - started).total_seconds() / 60)


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _float(value: Any, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
