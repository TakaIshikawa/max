"""JSON API renderer for PII detection backlog status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.pii_detection_backlog_status.v1"
KIND = "max.api.pii_detection_backlog_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def pii_detection_backlog_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    buckets = _buckets(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(buckets), "buckets": buckets, "status_totals": _status_totals(buckets), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, bucket_count=len(buckets))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _buckets(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("buckets") if isinstance(payload.get("buckets"), list) else payload.get("backlog")
    rows = [_bucket_row(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["suspected_pii_count"], -row["oldest_pending_age_hours"], row["bucket"]))


def _bucket_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    pending = max(0, int_or_zero(item.get("pending_items", item.get("pending"))))
    sampled = max(0, int_or_zero(item.get("sampled_items", item.get("sampled"))))
    suspected = max(0, int_or_zero(item.get("suspected_pii_count", item.get("suspected_pii"))))
    oldest = max(0, int_or_zero(item.get("oldest_pending_age_hours", item.get("age_hours"))))
    status = _status(item.get("status"), pending, suspected, oldest)
    return {"bucket": _text(item.get("bucket")) or f"bucket-{index}", "pending_items": pending, "sampled_items": sampled, "suspected_pii_count": suspected, "oldest_pending_age_hours": oldest, "owner": _text(item.get("owner")) or "unassigned", "status": status}


def _status(value: Any, pending: int, suspected: int, oldest: int) -> str:
    explicit = _name(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if suspected >= 10 or oldest >= 168:
        return "critical"
    if suspected > 0 or oldest >= 72:
        return "high"
    if pending > 0 or oldest >= 24:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "bucket_count": len(rows), "pending_item_count": sum(row["pending_items"] for row in rows), "suspected_pii_count": sum(row["suspected_pii_count"] for row in rows), "critical_bucket_count": counts["critical"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "bucket_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _name(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
