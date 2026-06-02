"""JSON API renderer for feedback reviewer workload status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.feedback_reviewer_workload_status.v1"
KIND = "max.api.feedback_reviewer_workload_status"


def feedback_reviewer_workload_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = float_or_zero(payload.get("warning_utilization")) or 0.8
    critical = float_or_zero(payload.get("critical_utilization")) or 1.0
    reviewers = [_reviewer(row, warning, critical) for row in _items(payload)]
    reviewers.sort(key=lambda row: (_rank(row["status"]), row["reviewer"]))
    summary = _summary(reviewers)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "reviewers": reviewers, "profile_hot_spots": _hot_spots(reviewers), "metadata": source_metadata(payload, reviewer_count=len(reviewers))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("reviewers")) or list_of_maps(payload.get("items"))


def _reviewer(row: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    pending = max(0, int_or_zero(row.get("pending_reviews")))
    completed = max(0, int_or_zero(row.get("completed_reviews")))
    capacity = max(0, int_or_zero(row.get("capacity")))
    overdue = max(0, int_or_zero(row.get("overdue_reviews")))
    utilization = round(pending / capacity, 4) if capacity else (1.0 if pending else 0.0)
    status = "critical" if (capacity == 0 and pending) or overdue or utilization >= critical else "warning" if utilization >= warning else "ok"
    return {"reviewer": _bucket(row.get("reviewer"), "unknown_reviewer"), "pending_reviews": pending, "completed_reviews": completed, "capacity": capacity, "overdue_reviews": overdue, "profiles": sorted(_bucket(value, "unknown_profile") for value in as_list(row.get("profiles"))), "utilization": utilization, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "reviewer_count": len(rows), "overloaded_count": critical + warning, "overdue_total": sum(row["overdue_reviews"] for row in rows), "pending_total": sum(row["pending_reviews"] for row in rows), "critical_count": critical, "warning_count": warning}


def _hot_spots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        for profile in row["profiles"]:
            if row["pending_reviews"]:
                counts[profile] += row["pending_reviews"]
    return [{"profile": profile, "pending_reviews": count} for profile, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
