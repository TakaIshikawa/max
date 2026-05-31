"""JSON API renderer for publisher retry pressure status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_pressure_status.v1"
KIND = "max.api.publisher_retry_pressure_status"


def publisher_retry_pressure_status_to_json(
    payload: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
    high_retry_count: int | None = None,
) -> str:
    as_of = parse_datetime(now) or datetime.now(timezone.utc)
    high = max(1, int_or_zero(high_retry_count if high_retry_count is not None else payload.get("high_retry_count")) or 3)
    rows = _rows(payload, as_of, high)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, high), "rows": rows, "metadata": source_metadata(payload, group_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime, high: int) -> list[dict[str, Any]]:
    source = payload.get("jobs") if isinstance(payload.get("jobs"), list) else payload.get("publication_jobs")
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []:
        key = (_text(item.get("target_type"), "unknown"), _text(item.get("target_name") or item.get("target"), "unknown"))
        retry_count = max(0, int_or_zero(item.get("retry_count") or item.get("attempts")))
        next_retry = parse_datetime(item.get("next_retry_at"))
        overdue = bool(next_retry and next_retry <= as_of)
        group = groups.setdefault(key, {"total_retrying": 0, "overdue_retry_count": 0, "max_retry_count": 0, "retry_count_buckets": {"0": 0, "1_2": 0, "3_plus": 0}})
        group["total_retrying"] += 1
        group["overdue_retry_count"] += 1 if overdue else 0
        group["max_retry_count"] = max(group["max_retry_count"], retry_count)
        group["retry_count_buckets"]["0" if retry_count == 0 else "1_2" if retry_count < high else "3_plus"] += 1
    rows = [_row(target_type, target_name, data, high) for (target_type, target_name), data in groups.items()]
    return sorted(rows, key=lambda row: (row["severity_rank"], -row["overdue_retry_count"], row["target_type"], row["target_name"]))


def _row(target_type: str, target_name: str, data: Mapping[str, Any], high: int) -> dict[str, Any]:
    severity = "critical" if data["overdue_retry_count"] and data["max_retry_count"] >= high else "warn" if data["overdue_retry_count"] or data["max_retry_count"] >= high else "healthy"
    return {**data, "target_type": target_type, "target_name": target_name, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], high: int) -> dict[str, Any]:
    severity = "critical" if any(row["severity"] == "critical" for row in rows) else "warn" if any(row["severity"] == "warn" for row in rows) else "healthy"
    return {"severity": severity, "group_count": len(rows), "total_retrying": sum(row["total_retrying"] for row in rows), "overdue_retry_count": sum(row["overdue_retry_count"] for row in rows), "max_retry_count": max([row["max_retry_count"] for row in rows] or [0]), "high_retry_count": high}


def _text(value: Any, default: str) -> str:
    return " ".join(str(value).strip().split()) if value not in (None, "") else default
