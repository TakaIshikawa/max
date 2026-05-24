"""JSON API renderer for review assignment queues."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "max.api.review_assignment_queue.v1"
KIND = "max.api.review_assignment_queue"
HIGH_PRIORITIES = {"high", "urgent", "p0", "p1", "critical"}
OPEN_STATUSES = {"assigned", "pending", "queued", "in_review", "open"}


def review_assignment_queue_to_json(
    payload: Mapping[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> str:
    """Render review assignment queue data as deterministic API JSON."""
    effective_as_of = _parse_datetime(as_of) or _parse_datetime(payload.get("as_of"))
    assignments = _assignments(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(assignments),
        "assignments": assignments,
        "counts_by_reviewer": _counts(assignments, "reviewer"),
        "counts_by_status": _counts(assignments, "status"),
        "counts_by_priority": _counts(assignments, "priority"),
        "overdue_assignments": [row for row in assignments if row["overdue"]],
        "metadata": _metadata(payload, assignments, effective_as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    ages = [row["age_days"] for row in assignments if row["age_days"] is not None]
    return {
        "total_assignments": len(assignments),
        "overdue_count": sum(1 for row in assignments if row["overdue"]),
        "high_priority_count": sum(1 for row in assignments if row["high_priority"]),
        "unassigned_count": sum(1 for row in assignments if row["reviewer"] == "unassigned"),
        "oldest_assignment_age_days": max(ages) if ages else None,
    }


def _assignments(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("assignments")
    if not isinstance(source, list):
        source = payload.get("review_assignments")
    rows = [
        _assignment_row(item, index, as_of)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(
        rows,
        key=lambda row: (
            str(row["reviewer"]),
            str(row["due_at"] or ""),
            str(row["assignment_id"]),
        ),
    )


def _assignment_row(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    reviewer = item.get("reviewer") or item.get("assignee") or "unassigned"
    status = str(item.get("status") or "assigned")
    priority = str(item.get("priority") or "normal").lower()
    assigned_at = item.get("assigned_at") or item.get("created_at")
    due_at = item.get("due_at")
    age_days = _age_days(assigned_at, as_of)
    due_dt = _parse_datetime(due_at)
    overdue = bool(as_of and due_dt and due_dt < as_of and status.lower() in OPEN_STATUSES)
    return {
        "assignment_id": item.get("assignment_id") or item.get("id") or f"assignment-{index}",
        "idea_id": item.get("idea_id") or item.get("artifact_id"),
        "reviewer": str(reviewer),
        "status": status,
        "priority": priority,
        "assigned_at": assigned_at,
        "due_at": due_at,
        "age_days": age_days,
        "overdue": overdue,
        "high_priority": priority in HIGH_PRIORITIES,
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def _metadata(
    payload: Mapping[str, Any],
    assignments: list[dict[str, Any]],
    as_of: datetime | None,
) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "assignment_count": len(assignments),
        "as_of": metadata.get("as_of") or _datetime_to_string(as_of),
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


def _datetime_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _age_days(value: Any, as_of: datetime | None) -> int | None:
    started = _parse_datetime(value)
    if not started or not as_of:
        return None
    return max((as_of - started).days, 0)
