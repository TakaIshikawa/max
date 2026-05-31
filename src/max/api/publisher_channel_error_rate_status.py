"""JSON API renderer for publisher channel error rate status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_channel_error_rate_status.v1"
KIND = "max.api.publisher_channel_error_rate_status"
STATUS_RANK = {"critical": 0, "degraded": 1, "healthy": 2}


def publisher_channel_error_rate_status_to_json(payload: Mapping[str, Any]) -> str:
    channels = [_channel(item, index, payload) for index, item in enumerate(list_of_maps(payload.get("channels") or payload.get("publishers")), start=1)]
    channels.sort(key=lambda row: (STATUS_RANK[row["status"]], row["channel_id"]))
    status = "critical" if any(row["status"] == "critical" for row in channels) else ("degraded" if any(row["status"] == "degraded" for row in channels) else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "channel_count": len(channels), "publish_attempt_count": sum(row["attempt_count"] for row in channels), "error_count": sum(row["error_count"] for row in channels), "retry_pressure": sum(row["retry_count"] for row in channels)}, "channels": channels, "top_error_codes": _top_errors(payload), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _channel(item: Mapping[str, Any], index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    attempts = int_or_zero(item.get("attempt_count", item.get("attempts")))
    errors = int_or_zero(item.get("error_count", item.get("errors")))
    rate = round(errors / attempts, 4) if attempts else 0.0
    degraded = float(payload.get("degraded_error_rate", 0.05))
    critical = float(payload.get("critical_error_rate", 0.2))
    status = "critical" if attempts and rate >= critical else ("degraded" if attempts and rate >= degraded else "healthy")
    return {"channel_id": _text(item.get("channel_id") or item.get("channel")) or f"channel-{index}", "attempt_count": attempts, "error_count": errors, "error_rate": rate, "retry_count": int_or_zero(item.get("retry_count", item.get("retries"))), "status": status}


def _top_errors(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "sample_channel_ids": set()})
    for item in list_of_maps(payload.get("errors") or payload.get("error_codes")):
        code = _text(item.get("code") or item.get("error_code")) or "unknown"
        grouped[code]["count"] += max(1, int_or_zero(item.get("count", 1)))
        channel = _text(item.get("channel_id") or item.get("channel"))
        if channel:
            grouped[code]["sample_channel_ids"].add(channel)
    rows = [{"code": code, "count": data["count"], "sample_channel_ids": sorted(data["sample_channel_ids"])[:3]} for code, data in grouped.items()]
    return sorted(rows, key=lambda row: (-row["count"], row["code"]))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
