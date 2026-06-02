"""Publication delegate load export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_delegate_load_report.v1"
KIND = "max.publication_delegate_load_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
DEFAULT_OLDEST_PENDING_SLA_HOURS = 48


def build_publication_delegate_load_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Publication Delegate Load Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    oldest_pending_sla_hours: int = DEFAULT_OLDEST_PENDING_SLA_HOURS,
) -> dict[str, Any]:
    rows = []
    for index, raw in enumerate(records):
        if isinstance(raw, dict):
            rows.append(_row(raw, index=index, oldest_pending_sla_hours=max(0, oldest_pending_sla_hours)))
    rows.sort(key=lambda row: (row["delegate"].lower(), row["destination"].lower(), row["profile"].lower()))
    overloaded = [row for row in rows if row["overloaded"]]
    overloaded.sort(key=lambda row: (-row["utilization"], -row["oldest_pending_hours"], row["delegate"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Publication Delegate Load Report",
        "summary": {
            "delegate_assignment_count": len(rows),
            "delegate_count": len({row["delegate"] for row in rows}),
            "pending_count": sum(row["pending_count"] for row in rows),
            "overloaded_delegate_count": len({row["delegate"] for row in overloaded}),
        },
        "delegate_rows": rows,
        "overloaded_delegates": overloaded,
        "destination_hot_spots": _destination_hot_spots(rows),
    }


def render_publication_delegate_load_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_delegate_load_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Publication Delegate Load Report'}",
        "",
        "## Summary",
        "",
        f"- Delegates: {summary.get('delegate_count', 0)}",
        f"- Pending: {summary.get('pending_count', 0)}",
        f"- Overloaded delegates: {summary.get('overloaded_delegate_count', 0)}",
        "",
        "## Overloaded Delegates",
        "",
    ]
    overloaded = report.get("overloaded_delegates") or []
    lines.extend([f"- {row['delegate']} -> {row['destination']} ({row['utilization']:.2f}x, oldest {row['oldest_pending_hours']}h)" for row in overloaded] or ["- No overloaded delegates."])
    return "\n".join(lines).rstrip() + "\n"


def _row(raw: dict[str, Any], *, index: int, oldest_pending_sla_hours: int) -> dict[str, Any]:
    pending = _int(raw.get("pending_count"))
    capacity = _int(raw.get("capacity_limit"))
    oldest = _int(raw.get("oldest_pending_hours"))
    utilization = round(pending / capacity, 4) if capacity > 0 else (1.0 if pending > 0 else 0.0)
    overloaded = pending > capacity if capacity > 0 else pending > 0
    overloaded = overloaded or oldest > oldest_pending_sla_hours
    return {
        "row_id": _text(raw.get("row_id") or raw.get("id")) or f"delegate-load-{index + 1}",
        "delegate": _text(raw.get("delegate")) or "Unassigned",
        "destination": _text(raw.get("destination")) or "unspecified-destination",
        "profile": _text(raw.get("profile")) or "default",
        "pending_count": pending,
        "oldest_pending_hours": oldest,
        "approved_count": _int(raw.get("approved_count")),
        "rejected_count": _int(raw.get("rejected_count")),
        "capacity_limit": capacity,
        "utilization": utilization,
        "overloaded": overloaded,
        "overload_reasons": _overload_reasons(pending=pending, capacity=capacity, oldest=oldest, sla=oldest_pending_sla_hours),
    }


def _destination_hot_spots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["destination"]].append(row)
    hot_spots = [
        {
            "destination": destination,
            "pending_count": sum(row["pending_count"] for row in items),
            "delegate_count": len({row["delegate"] for row in items}),
            "overloaded_count": sum(1 for row in items if row["overloaded"]),
        }
        for destination, items in grouped.items()
    ]
    hot_spots.sort(key=lambda row: (-row["pending_count"], -row["overloaded_count"], row["destination"].lower()))
    return hot_spots


def _overload_reasons(*, pending: int, capacity: int, oldest: int, sla: int) -> list[str]:
    reasons = []
    if capacity == 0 and pending > 0:
        reasons.append("zero_capacity")
    elif pending > capacity:
        reasons.append("capacity_exceeded")
    if oldest > sla:
        reasons.append("sla_exceeded")
    return reasons


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
