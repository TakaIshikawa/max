"""Publisher webhook latency export report."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.exports.publisher_webhook_latency_report.v1"
KIND = "max.exports.publisher_webhook_latency_report"


def generate_publisher_webhook_latency_report(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    attempts = _attempts(payload)
    groups = _groups(attempts)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(attempts, groups),
        "groups": groups,
        "attempts": attempts,
        "metadata": {"group_count": len(groups)},
    }


def render_publisher_webhook_latency_report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_publisher_webhook_latency_report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Publisher Webhook Latency Report",
        "",
        "| Target | Event Type | Attempts | Completed | p50 ms | p95 ms | Timeout Rate | Retry Impact ms | Severity |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("groups", []):
        lines.append(
            f"| {row['target']} | {row['event_type']} | {row['attempt_count']} | "
            f"{row['completed_count']} | {row['p50_latency_ms']} | {row['p95_latency_ms']} | "
            f"{row['timeout_rate']} | {row['retry_impact_ms']} | {row['severity']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _attempts(payload: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        source = payload.get("attempts") or payload.get("deliveries") or payload.get("items")
    else:
        source = list(payload)
    rows = [_attempt(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["target"], row["event_type"], row["attempt_id"]))
    return rows


def _attempt(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    status = _text(item.get("status") or item.get("outcome")).lower()
    timed_out = bool(item.get("timed_out")) or status in {"timeout", "timed_out"}
    latency = _duration(item)
    completed = not timed_out and latency > 0 and status not in {"failed", "error", "network_error"}
    retry_count = max(0, _int(item.get("retry_count", item.get("retries"))))
    return {
        "attempt_id": _text(item.get("attempt_id") or item.get("id")) or f"attempt-{index}",
        "target": _text(item.get("target") or item.get("destination") or item.get("publisher")) or "unknown_target",
        "event_type": _text(item.get("event_type") or item.get("event") or item.get("type")) or "unknown_event",
        "latency_ms": latency,
        "completed": completed,
        "timed_out": timed_out,
        "retry_count": retry_count,
    }


def _groups(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[(attempt["target"], attempt["event_type"])].append(attempt)
    rows = []
    for (target, event_type), items in grouped.items():
        completed = [item["latency_ms"] for item in items if item["completed"]]
        timeout_count = sum(1 for item in items if item["timed_out"])
        retry_attempts = [item for item in items if item["retry_count"] > 0]
        first_attempt_latencies = [item["latency_ms"] for item in items if item["completed"] and item["retry_count"] == 0]
        retry_latencies = [item["latency_ms"] for item in retry_attempts if item["completed"]]
        retry_impact = max(0, _average(retry_latencies) - _average(first_attempt_latencies)) if retry_latencies and first_attempt_latencies else 0
        timeout_rate = round(timeout_count / len(items), 4) if items else 0.0
        rows.append(
            {
                "target": target,
                "event_type": event_type,
                "attempt_count": len(items),
                "completed_count": len(completed),
                "timeout_count": timeout_count,
                "timeout_rate": timeout_rate,
                "retry_attempt_count": len(retry_attempts),
                "retry_impact_ms": int(round(retry_impact)),
                "p50_latency_ms": _percentile(completed, 0.50),
                "p95_latency_ms": _percentile(completed, 0.95),
                "severity": _severity(timeout_rate, completed),
            }
        )
    rows.sort(key=lambda row: (_severity_rank(row["severity"]), row["target"], row["event_type"]))
    return rows


def _summary(attempts: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    worst = groups[0]["severity"] if groups else "ok"
    return {
        "status": worst,
        "attempt_count": len(attempts),
        "group_count": len(groups),
        "timeout_count": sum(row["timeout_count"] for row in groups),
        "retry_attempt_count": sum(row["retry_attempt_count"] for row in groups),
    }


def _severity(timeout_rate: float, completed: list[int]) -> str:
    if timeout_rate >= 0.5:
        return "critical"
    if timeout_rate > 0 or _percentile(completed, 0.95) >= 30000:
        return "warning"
    return "ok"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(value, 3)


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _duration(item: Mapping[str, Any]) -> int:
    return max(0, _int(item.get("latency_ms", item.get("duration_ms", item.get("elapsed_ms")))))


def _average(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
