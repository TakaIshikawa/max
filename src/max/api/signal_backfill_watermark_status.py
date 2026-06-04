"""JSON API renderer for signal backfill watermark status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.signal_backfill_watermark_status.v1"
KIND = "max.api.signal_backfill_watermark_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def signal_backfill_watermark_status_to_json(
    payload: Any,
    *,
    as_of: datetime | str | None = None,
    warning_lag_minutes: int = 60,
    critical_lag_minutes: int = 240,
    warning_pending_signal_count: int = 1,
) -> str:
    payload_map = mapping(payload)
    as_of_dt = parse_datetime(as_of) or datetime.now(timezone.utc)
    adapters = _adapters(
        payload,
        as_of=as_of_dt,
        warning_lag_minutes=warning_lag_minutes,
        critical_lag_minutes=critical_lag_minutes,
        warning_pending_signal_count=warning_pending_signal_count,
    )
    status = _overall_status(adapters)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "adapter_count": len(adapters),
                "lagging_adapter_count": sum(1 for row in adapters if row["status"] != "ok"),
                "total_pending_signal_count": sum(row["pending_signal_count"] for row in adapters),
                "max_lag_minutes": max((row["lag_minutes"] for row in adapters), default=0),
                "status": status,
            },
            "adapters": adapters,
            "metadata": source_metadata(payload_map, adapter_count=len(adapters)),
        },
        indent=2,
        sort_keys=True,
    )


def _adapters(payload: Any, *, as_of: datetime, warning_lag_minutes: int, critical_lag_minutes: int, warning_pending_signal_count: int) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("sources") or payload_map.get("adapters") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_adapter(row, index, as_of, warning_lag_minutes, critical_lag_minutes, warning_pending_signal_count) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["lag_minutes"], row["adapter"]))


def _adapter(item: Mapping[str, Any], index: int, as_of: datetime, warning_lag_minutes: int, critical_lag_minutes: int, warning_pending_signal_count: int) -> dict[str, Any]:
    explicit_lag = item.get("lag_minutes")
    if explicit_lag is not None:
        lag = max(0, int_or_zero(explicit_lag))
    else:
        current = parse_datetime(item.get("current_watermark_at"))
        oldest = parse_datetime(item.get("oldest_required_at"))
        anchor = current or oldest
        lag = max(0, int((as_of - anchor).total_seconds() // 60)) if anchor else 0
    pending = max(0, int_or_zero(item.get("pending_signal_count")))
    if lag > critical_lag_minutes:
        status = "critical"
    elif lag > warning_lag_minutes or pending >= warning_pending_signal_count:
        status = "warning"
    else:
        status = "ok"
    return {
        "adapter": _text(item.get("adapter") or item.get("source")) or f"adapter-{index}",
        "profile": _text(item.get("profile")) or "default",
        "oldest_required_at": datetime_to_string(parse_datetime(item.get("oldest_required_at"))),
        "current_watermark_at": datetime_to_string(parse_datetime(item.get("current_watermark_at"))),
        "lag_minutes": lag,
        "pending_signal_count": pending,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
