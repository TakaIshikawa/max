"""JSON API renderer for publisher retry policy status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_policy_status.v1"
KIND = "max.api.publisher_retry_policy_status"
STATUS_RANK = {"misconfigured": 0, "exhausted": 1, "paused": 2, "active": 3}


def publisher_retry_policy_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    destinations = _destinations(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(destinations), "destinations": destinations, "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, destination_count=len(destinations))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _destinations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("policies")
    rows = [_destination(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["destination"]))


def _destination(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    attempts = max(0, int_or_zero(item.get("attempts", item.get("attempt_count"))))
    max_attempts = max(0, int_or_zero(item.get("max_attempts", item.get("retry_limit"))))
    paused = bool(item.get("paused")) or _bucket(item.get("state"), "") == "paused"
    misconfigured = max_attempts == 0 or not _text(item.get("backoff_strategy") or item.get("backoff"))
    exhausted = max_attempts > 0 and attempts >= max_attempts
    status = "misconfigured" if misconfigured else ("exhausted" if exhausted else ("paused" if paused else "active"))
    return {"destination": _text(item.get("destination") or item.get("destination_id") or item.get("id")) or f"destination-{index}", "attempts": attempts, "max_attempts": max_attempts, "backoff_strategy": _bucket(item.get("backoff_strategy") or item.get("backoff"), ""), "next_retry_at": datetime_to_string(parse_datetime(item.get("next_retry_at"))), "misconfigured": misconfigured, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    status = "misconfigured" if counts["misconfigured"] else ("exhausted" if counts["exhausted"] else ("paused" if counts["paused"] else "active"))
    return {"status": status, "destination_count": len(rows), "active_count": counts["active"], "paused_count": counts["paused"], "exhausted_count": counts["exhausted"]}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
