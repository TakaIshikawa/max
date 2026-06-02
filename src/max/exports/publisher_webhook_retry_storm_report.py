"""Publisher webhook retry storm export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.publisher_webhook_retry_storm_report.v1"
KIND = "max.publisher_webhook_retry_storm_report"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_publisher_webhook_retry_storm_report(
    records: Iterable[dict[str, Any]],
    *,
    retry_threshold: int = 5,
    window_minutes: int = 10,
) -> dict[str, Any]:
    attempts = [_attempt(raw, index) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[(attempt["destination"], attempt["webhook_identifier"])].append(attempt)
    rows = [_storm_row(destination, identifier, items, retry_threshold, window_minutes) for (destination, identifier), items in grouped.items()]
    rows = [row for row in rows if row["is_storm"]]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["destination"].casefold(), row["webhook_identifier"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "attempt_count": len(attempts),
            "storm_group_count": len(rows),
            "affected_destination_count": len({row["destination"] for row in rows}),
            "highest_severity": rows[0]["severity"] if rows else "low",
        },
        "storm_rows": rows,
    }


def render_publisher_webhook_retry_storm_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publisher_webhook_retry_storm_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Publisher Webhook Retry Storm Report",
        "",
        f"- Attempts: {report.get('summary', {}).get('attempt_count', 0)}",
        f"- Storm groups: {report.get('summary', {}).get('storm_group_count', 0)}",
        "",
        "## Recommendations",
        "",
    ]
    rows = report.get("storm_rows") or []
    if not rows:
        lines.append("- No retry storms detected.")
    for row in rows:
        lines.append(f"- {row['severity'].upper()}: {row['destination']} / {row['webhook_identifier']} - {row['recommendation']}")
    return "\n".join(lines).rstrip() + "\n"


def _storm_row(destination: str, identifier: str, items: list[dict[str, Any]], retry_threshold: int, window_minutes: int) -> dict[str, Any]:
    items.sort(key=lambda item: (item["attempted_at"] or datetime.min.replace(tzinfo=timezone.utc), item["attempt_id"]))
    burst_count = _burst_count(items, max(1, retry_threshold), max(1, window_minutes))
    retry_count = sum(1 for item in items if item["is_retry"])
    severity = _severity(retry_count, burst_count, retry_threshold)
    return {
        "destination": destination,
        "webhook_identifier": identifier,
        "attempt_count": len(items),
        "retry_count": retry_count,
        "retry_burst_count": burst_count,
        "window_minutes": max(1, window_minutes),
        "severity": severity,
        "is_storm": burst_count > 0,
        "first_attempt_at": items[0]["attempted_at"].isoformat() if items and items[0]["attempted_at"] else None,
        "last_attempt_at": items[-1]["attempted_at"].isoformat() if items and items[-1]["attempted_at"] else None,
        "recommendation": _recommendation(severity),
    }


def _attempt(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "attempt_id": _text(raw.get("attempt_id") or raw.get("id")) or f"attempt-{index}",
        "destination": _text(raw.get("destination") or raw.get("destination_id")) or "unknown-destination",
        "webhook_identifier": _text(raw.get("webhook_id") or raw.get("endpoint") or raw.get("url")) or "unknown-webhook",
        "attempted_at": _dt(raw.get("attempted_at") or raw.get("created_at") or raw.get("timestamp")),
        "is_retry": bool(raw.get("is_retry", raw.get("retry", raw.get("retry_count", 0)))),
    }


def _burst_count(items: list[dict[str, Any]], retry_threshold: int, window_minutes: int) -> int:
    dated = [item for item in items if item["attempted_at"] is not None and item["is_retry"]]
    bursts = 0
    for index, item in enumerate(dated):
        window_end = item["attempted_at"].timestamp() + window_minutes * 60
        count = sum(1 for candidate in dated[index:] if candidate["attempted_at"].timestamp() <= window_end)
        if count >= retry_threshold:
            bursts += 1
            break
    undated_retries = sum(1 for item in items if item["attempted_at"] is None and item["is_retry"])
    return bursts or (1 if undated_retries >= retry_threshold else 0)


def _severity(retry_count: int, burst_count: int, retry_threshold: int) -> str:
    if burst_count and retry_count >= retry_threshold * 3:
        return "critical"
    if burst_count and retry_count >= retry_threshold * 2:
        return "high"
    if burst_count:
        return "medium"
    return "low"


def _recommendation(severity: str) -> str:
    if severity in {"critical", "high"}:
        return "quarantine destination and apply exponential backoff"
    return "increase backoff and monitor retry pressure"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
