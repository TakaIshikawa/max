"""JSON API renderer for idea approval pipeline status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.idea_approval_pipeline_status.v1"
KIND = "max.api.idea_approval_pipeline_status"
KNOWN_STATES = {"pending", "approved", "rejected", "needs_changes"}


def idea_approval_pipeline_status_to_json(
    payload: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
    stale_pending_seconds: int | None = None,
    critical_pending_seconds: int | None = None,
) -> str:
    as_of = parse_datetime(now) or datetime.now(timezone.utc)
    stale = _int(stale_pending_seconds if stale_pending_seconds is not None else payload.get("stale_pending_seconds"), 86400)
    critical = _int(critical_pending_seconds if critical_pending_seconds is not None else payload.get("critical_pending_seconds"), stale * 2)
    rows = [_row(item, as_of, stale, critical) for item in _items(payload)]
    rows.sort(key=lambda row: (row["severity_rank"], -row["pending_age_seconds"], row["idea_id"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, stale, critical), "rows": rows, "metadata": source_metadata(payload, idea_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = payload.get("ideas") if isinstance(payload.get("ideas"), list) else payload.get("reviews")
    return [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any], as_of: datetime, stale: int, critical: int) -> dict[str, Any]:
    state = str(item.get("review_state") or item.get("state") or item.get("status") or "unknown").strip().lower()
    state = state if state in KNOWN_STATES else "unknown"
    submitted = parse_datetime(item.get("review_requested_at") or item.get("submitted_at"))
    age = max(0, int((as_of - submitted).total_seconds())) if state == "pending" and submitted else 0
    stale_pending = state == "pending" and age >= stale
    severity = "critical" if state == "pending" and age >= critical else "warn" if stale_pending else "healthy"
    return {"idea_id": str(item.get("idea_id") or item.get("id") or "unknown_idea"), "state": state, "pending_age_seconds": age, "stale_pending": stale_pending, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], stale: int, critical: int) -> dict[str, Any]:
    states = {state: sum(1 for row in rows if row["state"] == state) for state in sorted(KNOWN_STATES | {"unknown"})}
    oldest = max([row["pending_age_seconds"] for row in rows if row["state"] == "pending"] or [0])
    severity = "critical" if oldest >= critical else "warn" if any(row["stale_pending"] for row in rows) else "healthy"
    return {"severity": severity, "idea_count": len(rows), "state_counts": states, "stale_pending_count": sum(1 for row in rows if row["stale_pending"]), "oldest_pending_age_seconds": oldest, "stale_pending_seconds": stale, "critical_pending_seconds": critical}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
