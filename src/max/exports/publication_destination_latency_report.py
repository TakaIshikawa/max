"""Publication destination latency export report."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Iterable


def build_publication_destination_latency_report(records: Iterable[dict[str, Any]], *, sla_ms: int = 30000, timeout_ms: int = 60000) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = {}
    for raw in records:
        destination = _text(raw.get("destination") or raw.get("channel")) or "unknown-destination"
        latency = _latency(raw)
        groups.setdefault(destination, []).append(latency)
    rows = []
    for destination, values in groups.items():
        values = sorted(values)
        timeout_count = sum(1 for value in values if value >= timeout_ms)
        p95 = _percentile(values, 0.95)
        status = "breach" if timeout_count or p95 > sla_ms else "healthy"
        rows.append({"destination": destination, "attempt_count": len(values), "p50_latency_ms": _percentile(values, 0.5), "p95_latency_ms": p95, "max_latency_ms": max(values) if values else 0, "timeout_count": timeout_count, "sla_status": status})
    rows.sort(key=lambda row: (0 if row["sla_status"] == "breach" else 1, row["destination"].lower()))
    return rows


def render_publication_destination_latency_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_destination_latency_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Publication Destination Latency Report", "", "| Destination | Attempts | p50 ms | p95 ms | Max ms | Timeouts | SLA |", "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        lines.append(f"| {row['destination']} | {row['attempt_count']} | {row['p50_latency_ms']} | {row['p95_latency_ms']} | {row['max_latency_ms']} | {row['timeout_count']} | {row['sla_status']} |")
    return "\n".join(lines).rstrip() + "\n"


def _latency(raw: dict[str, Any]) -> int:
    direct = raw.get("latency_ms") if raw.get("latency_ms") is not None else raw.get("duration_ms")
    if direct is not None:
        return _int(direct)
    start = _dt(raw.get("started_at"))
    end = _dt(raw.get("completed_at"))
    return max(0, int((end - start).total_seconds() * 1000)) if start and end else 0


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    index = min(len(values) - 1, int(round((len(values) - 1) * ratio)))
    return values[index]


def _dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
