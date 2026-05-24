"""Publisher webhook delivery export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, parse_datetime

SCHEMA_VERSION = "max.exports.publisher_webhook_delivery_report.v1"
KIND = "max.exports.publisher_webhook_delivery_report"


def generate_publisher_webhook_delivery_report(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    as_of: str | datetime | None = None,
    success_rate_threshold: float | None = None,
) -> dict[str, Any]:
    effective_as_of = parse_datetime(as_of) or parse_datetime(
        payload.get("as_of") if isinstance(payload, Mapping) else None
    )
    threshold = _threshold(payload, success_rate_threshold)
    attempts = _attempts(payload, effective_as_of)
    destinations = _destinations(attempts, threshold)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(attempts, destinations),
        "destinations": destinations,
        "status_family_counts": _status_family_counts(attempts),
        "undelivered_backlog": _undelivered_backlog(attempts),
        "flagged_destinations": [
            row for row in destinations if row["below_success_rate_threshold"]
        ],
        "attempts": attempts,
        "metadata": {
            "as_of": datetime_to_string(effective_as_of),
            "success_rate_threshold": threshold,
        },
    }


def render_publisher_webhook_delivery_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _attempts(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]], as_of: datetime | None
) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        source = payload.get("attempts") or payload.get("deliveries") or payload.get("webhooks")
    else:
        source = list(payload)
    rows = [
        _attempt(item, index, as_of)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    rows.sort(key=lambda row: (row["destination"], row["attempted_at"] or "", row["attempt_id"]))
    return rows


def _attempt(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    status_code = int(
        _float(item.get("status_code", item.get("response_status", item.get("http_status"))))
    )
    status_family = _status_family(status_code, item.get("status") or item.get("outcome"))
    delivered = status_family == "2xx"
    attempted_at = parse_datetime(
        item.get("attempted_at") or item.get("created_at") or item.get("last_attempt_at")
    )
    retry_count = max(0, int(_float(item.get("retry_count", item.get("retries")))))
    error = _text(item.get("error") or item.get("last_error") or item.get("error_message"))
    return {
        "attempt_id": _text(item.get("attempt_id") or item.get("id")) or f"attempt-{index}",
        "payload_id": _text(
            item.get("payload_id") or item.get("event_id") or item.get("artifact_id")
        ),
        "destination": _text(
            item.get("destination")
            or item.get("endpoint")
            or item.get("url")
            or item.get("publisher")
        )
        or "unknown-destination",
        "status_family": status_family,
        "status_code": status_code,
        "delivered": delivered,
        "retry_count": retry_count,
        "attempted_at": datetime_to_string(attempted_at),
        "undelivered_age_hours": _age_hours(attempted_at, as_of) if not delivered else 0,
        "error": error,
    }


def _destinations(attempts: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt["destination"]].append(attempt)
    rows = []
    for destination, items in grouped.items():
        success_count = sum(1 for item in items if item["delivered"])
        attempt_count = len(items)
        rate = round(success_count / attempt_count, 4) if attempt_count else 0.0
        undelivered = [item for item in items if not item["delivered"]]
        rows.append(
            {
                "destination": destination,
                "attempt_count": attempt_count,
                "success_count": success_count,
                "failure_count": attempt_count - success_count,
                "success_rate": rate,
                "retry_count": sum(item["retry_count"] for item in items),
                "oldest_undelivered_age_hours": max(
                    (item["undelivered_age_hours"] for item in undelivered), default=0
                ),
                "last_error": _last_error(items),
                "below_success_rate_threshold": rate < threshold if attempt_count else False,
            }
        )
    rows.sort(
        key=lambda row: (
            row["success_rate"],
            -row["oldest_undelivered_age_hours"],
            row["destination"],
        )
    )
    return rows


def _summary(attempts: list[dict[str, Any]], destinations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "attempt_count": len(attempts),
        "destination_count": len(destinations),
        "success_count": sum(1 for item in attempts if item["delivered"]),
        "failure_count": sum(1 for item in attempts if not item["delivered"]),
        "retry_count": sum(item["retry_count"] for item in attempts),
        "undelivered_payload_count": len(
            {item["payload_id"] or item["attempt_id"] for item in attempts if not item["delivered"]}
        ),
        "flagged_destination_count": sum(
            1 for row in destinations if row["below_success_rate_threshold"]
        ),
    }


def _status_family_counts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(item["status_family"] for item in attempts)
    return [{"status_family": family, "count": count} for family, count in sorted(counts.items())]


def _undelivered_backlog(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "payload_id": item["payload_id"],
            "attempt_id": item["attempt_id"],
            "destination": item["destination"],
            "status_family": item["status_family"],
            "age_hours": item["undelivered_age_hours"],
            "retry_count": item["retry_count"],
            "error": item["error"],
        }
        for item in attempts
        if not item["delivered"]
    ]
    rows.sort(
        key=lambda row: (
            -row["age_hours"],
            row["destination"],
            row["payload_id"],
            row["attempt_id"],
        )
    )
    return rows


def _last_error(items: list[dict[str, Any]]) -> str:
    errors = [item for item in items if item["error"]]
    errors.sort(key=lambda row: (row["attempted_at"] or "", row["attempt_id"]))
    return errors[-1]["error"] if errors else ""


def _status_family(status_code: int, status: Any) -> str:
    if status_code:
        return f"{status_code // 100}xx"
    text = _text(status).lower()
    if text in {"success", "succeeded", "delivered", "complete", "completed"}:
        return "2xx"
    if text in {"pending", "queued", "in_progress"}:
        return "pending"
    if text in {"timeout", "network_error"}:
        return "network_error"
    return "unknown"


def _age_hours(value: datetime | None, as_of: datetime | None) -> int:
    if value is None or as_of is None:
        return 0
    return max(0, int((as_of - value).total_seconds() // 3600))


def _threshold(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]], override: float | None
) -> float:
    raw = (
        override
        if override is not None
        else (payload.get("success_rate_threshold") if isinstance(payload, Mapping) else None)
    )
    value = _float(raw if raw is not None else 0.95)
    return min(1.0, max(0.0, value))


def _float(value: Any) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
