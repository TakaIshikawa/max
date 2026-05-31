"""JSON API renderer for retrospective learning health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.retrospective_learning_health_status.v1"
KIND = "max.api.retrospective_learning_health_status"


def retrospective_learning_health_status_to_json(payload: Mapping[str, Any]) -> str:
    now = parse_datetime(payload.get("now")) or parse_datetime(payload.get("as_of")) or datetime.utcnow()
    outcomes = list_of_maps(payload.get("feedback_outcomes") or payload.get("outcomes") or payload.get("items"))
    checkpoint = payload.get("learning_job") if isinstance(payload.get("learning_job"), Mapping) else payload.get("checkpoint")
    latest_applied = parse_datetime(checkpoint.get("latest_applied_outcome_at") if isinstance(checkpoint, Mapping) else None)
    rows = [_row(item, latest_applied, now) for item in outcomes]
    pending = [row for row in rows if row["pending"]]
    oldest = max((row["pending_age_hours"] for row in pending), default=0)
    severity = "critical" if oldest >= 168 else "warning" if pending else "ok"
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": severity, "outcome_count": len(rows), "unprocessed_outcome_count": len(pending), "oldest_pending_age_hours": oldest, "latest_applied_outcome_at": datetime_to_string(latest_applied)}, "rows": sorted(rows, key=lambda row: (not row["pending"], -row["pending_age_hours"], row["outcome_id"])), "pending_outcomes": sorted(pending, key=lambda row: (-row["pending_age_hours"], row["outcome_id"])), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], latest_applied: datetime | None, now: datetime) -> dict[str, Any]:
    occurred = parse_datetime(item.get("outcome_at") or item.get("created_at") or item.get("timestamp"))
    processed = bool(item.get("processed") or item.get("incorporated"))
    pending = not processed and (latest_applied is None or occurred is None or occurred > latest_applied)
    age = int((now - occurred).total_seconds() // 3600) if pending and occurred else 0
    return {"outcome_id": str(item.get("id") or item.get("outcome_id") or "unknown_outcome"), "occurred_at": datetime_to_string(occurred), "pending": pending, "pending_age_hours": max(0, age), "severity": "critical" if age >= 168 else "warning" if pending else "ok"}
