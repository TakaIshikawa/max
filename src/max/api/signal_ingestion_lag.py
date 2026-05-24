"""JSON API renderer for signal ingestion lag reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "max.api.signal_ingestion_lag.v1"
KIND = "max.api.signal_ingestion_lag"
DEFAULT_STALE_THRESHOLD_SECONDS = 3600


def signal_ingestion_lag_to_json(payload: Mapping[str, Any]) -> str:
    """Render signal ingestion lag data as deterministic API JSON."""
    threshold = _int_or_zero(payload.get("stale_threshold_seconds")) or DEFAULT_STALE_THRESHOLD_SECONDS
    records = _records(payload)
    sources = _sources(records, threshold)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(records, sources),
        "signal_lag_records": records,
        "lag_by_source": sources,
        "incomplete_records": [row for row in records if row["missing_timestamp_count"]],
        "metadata": _metadata(payload, records, threshold),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_records": len(records),
        "incomplete_record_count": sum(1 for row in records if row["missing_timestamp_count"]),
        "source_count": len(sources),
        "stale_source_count": sum(1 for row in sources if row["stale"]),
    }


def _records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("signals")
    if not isinstance(source, list):
        source = payload.get("signal_timings")
    rows = [
        _record_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["source"]), str(row["signal_id"])))


def _record_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    observed_at = item.get("observed_at")
    fetched_at = item.get("fetched_at")
    stored_at = item.get("stored_at") or item.get("persisted_at")
    fetch_lag = _seconds_between(observed_at, fetched_at)
    persistence_lag = _seconds_between(fetched_at, stored_at)
    end_to_end_lag = _seconds_between(observed_at, stored_at)
    missing = sum(1 for value in (observed_at, fetched_at, stored_at) if _parse_datetime(value) is None)
    return {
        "signal_id": item.get("signal_id") or item.get("id") or f"signal-{index}",
        "source": str(item.get("source") or "unknown-source"),
        "observed_at": observed_at,
        "fetched_at": fetched_at,
        "stored_at": stored_at,
        "fetch_lag_seconds": fetch_lag,
        "persistence_lag_seconds": persistence_lag,
        "end_to_end_lag_seconds": end_to_end_lag,
        "missing_timestamp_count": missing,
    }


def _sources(records: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["source"]), []).append(record)
    rows = []
    for source, items in sorted(grouped.items()):
        lags = [item["end_to_end_lag_seconds"] for item in items if item["end_to_end_lag_seconds"] is not None]
        max_lag = max(lags) if lags else None
        rows.append(
            {
                "source": source,
                "record_count": len(items),
                "average_lag_seconds": round(sum(lags) / len(lags), 2) if lags else None,
                "max_lag_seconds": max_lag,
                "incomplete_record_count": sum(1 for item in items if item["missing_timestamp_count"]),
                "stale": bool(max_lag is not None and max_lag >= threshold),
            }
        )
    return rows


def _metadata(payload: Mapping[str, Any], records: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "record_count": len(records),
        "stale_threshold_seconds": threshold,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_between(start: Any, end: Any) -> int | None:
    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end)
    if not start_dt or not end_dt:
        return None
    return max(int((end_dt - start_dt).total_seconds()), 0)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
