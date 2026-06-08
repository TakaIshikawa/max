"""Publisher webhook failure export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_webhook_failure_report.v1"
KIND = "max.publisher_webhook_failure_report"
_STATUS_RANK = {"failing": 0, "degraded": 1, "healthy": 2}


def generate_publisher_webhook_failure_report(
    attempts: Iterable[dict[str, Any]],
    *,
    degraded_failure_rate_threshold: float = 0.05,
    failing_failure_rate_threshold: float = 0.20,
) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(_group)
    destination_status: dict[str, str] = {}

    for raw in attempts:
        if not isinstance(raw, dict):
            continue
        row = _attempt(raw)
        group = groups[(row["destination"], row["event_type"])]
        group["destination"] = row["destination"]
        group["event_type"] = row["event_type"]
        group["attempt_count"] += 1
        group["success_count"] += 1 if row["successful"] else 0
        group["failure_count"] += 1 if row["failed"] else 0
        group["status_code_family_counts"][row["status_code_family"]] += 1
        group["timeout_count"] += 1 if row["timed_out"] else 0
        group["retry_exhausted_count"] += 1 if row["retry_exhausted"] else 0

    rows = []
    for group in groups.values():
        failure_rate = _ratio(group["failure_count"], group["attempt_count"])
        status = _status(failure_rate, degraded_failure_rate_threshold, failing_failure_rate_threshold)
        destination = group["destination"]
        destination_status[destination] = _worst(destination_status.get(destination, "healthy"), status)
        rows.append(
            {
                "destination": destination,
                "event_type": group["event_type"],
                "attempt_count": group["attempt_count"],
                "success_count": group["success_count"],
                "failure_count": group["failure_count"],
                "failure_rate": failure_rate,
                "status_code_families": {
                    "2xx": group["status_code_family_counts"]["2xx"],
                    "3xx": group["status_code_family_counts"]["3xx"],
                    "4xx": group["status_code_family_counts"]["4xx"],
                    "5xx": group["status_code_family_counts"]["5xx"],
                    "unknown": group["status_code_family_counts"]["unknown"],
                },
                "4xx_count": group["status_code_family_counts"]["4xx"],
                "5xx_count": group["status_code_family_counts"]["5xx"],
                "timeout_count": group["timeout_count"],
                "retry_exhausted_count": group["retry_exhausted_count"],
                "status": status,
            }
        )

    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], -row["failure_count"], row["destination"].casefold(), row["event_type"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "destination_count": len(destination_status),
            "group_count": len(rows),
            "attempt_count": sum(row["attempt_count"] for row in rows),
            "failure_count": sum(row["failure_count"] for row in rows),
            "failure_rate": _ratio(sum(row["failure_count"] for row in rows), sum(row["attempt_count"] for row in rows)),
            "4xx_count": sum(row["4xx_count"] for row in rows),
            "5xx_count": sum(row["5xx_count"] for row in rows),
            "timeout_count": sum(row["timeout_count"] for row in rows),
            "retry_exhausted_count": sum(row["retry_exhausted_count"] for row in rows),
            "healthy_count": sum(1 for status in destination_status.values() if status == "healthy"),
            "degraded_count": sum(1 for status in destination_status.values() if status == "degraded"),
            "failing_count": sum(1 for status in destination_status.values() if status == "failing"),
            "degraded_failure_rate_threshold": max(0.0, degraded_failure_rate_threshold),
            "failing_failure_rate_threshold": max(0.0, failing_failure_rate_threshold),
        },
        "rows": rows,
    }


def _group() -> dict[str, Any]:
    return {
        "destination": "",
        "event_type": "",
        "attempt_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "status_code_family_counts": defaultdict(int),
        "timeout_count": 0,
        "retry_exhausted_count": 0,
    }


def _attempt(raw: dict[str, Any]) -> dict[str, Any]:
    status = _text(raw.get("status") or raw.get("outcome")).casefold()
    status_code = _int_or_none(raw.get("status_code") or raw.get("http_status") or raw.get("response_code"))
    family = _status_code_family(status_code)
    timed_out = bool(raw.get("timed_out") or raw.get("timeout")) or status in {"timeout", "timed_out"}
    retry_exhausted = bool(raw.get("retry_exhausted") or raw.get("retries_exhausted") or raw.get("exhausted")) or status in {
        "retry_exhausted",
        "failed_exhausted",
        "exhausted",
    }
    failed = timed_out or retry_exhausted or family in {"4xx", "5xx"} or status in {"failed", "failure", "error", "network_error"}
    successful = not failed and (family in {"2xx", "3xx"} or status in {"success", "succeeded", "ok", "delivered"})
    return {
        "destination": _text(raw.get("destination") or raw.get("destination_id") or raw.get("target") or raw.get("url")) or "unknown-destination",
        "event_type": _text(raw.get("event_type") or raw.get("event") or raw.get("type")) or "unknown-event",
        "status_code_family": family,
        "timed_out": timed_out,
        "retry_exhausted": retry_exhausted,
        "failed": failed,
        "successful": successful,
    }


def _status(failure_rate: float, degraded_threshold: float, failing_threshold: float) -> str:
    degraded_threshold = max(0.0, degraded_threshold)
    failing_threshold = max(degraded_threshold, failing_threshold)
    if failure_rate >= failing_threshold:
        return "failing"
    if failure_rate >= degraded_threshold:
        return "degraded"
    return "healthy"


def _worst(left: str, right: str) -> str:
    return left if _STATUS_RANK[left] <= _STATUS_RANK[right] else right


def _status_code_family(value: int | None) -> str:
    if value is None:
        return "unknown"
    if 200 <= value <= 299:
        return "2xx"
    if 300 <= value <= 399:
        return "3xx"
    if 400 <= value <= 499:
        return "4xx"
    if 500 <= value <= 599:
        return "5xx"
    return "unknown"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
