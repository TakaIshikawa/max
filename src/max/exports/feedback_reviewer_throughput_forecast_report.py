"""Feedback reviewer throughput forecast export report."""

from __future__ import annotations

from collections import defaultdict
from math import ceil
from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_reviewer_throughput_forecast_report.v1"
KIND = "max.feedback_reviewer_throughput_forecast_report"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_feedback_reviewer_throughput_forecast_report(
    records: Iterable[dict[str, Any]],
    *,
    warning_days_to_clear: int = 14,
    critical_days_to_clear: int = 30,
) -> dict[str, Any]:
    rows = [_row(raw, index, warning_days_to_clear, critical_days_to_clear) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], -(row["days_to_clear"] or 0), row["reviewer"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "reviewer_count": len(rows),
            "overloaded_reviewer_count": sum(1 for row in rows if row["status"] != "healthy"),
            "open_review_total": sum(row["open_reviews"] for row in rows),
            "no_throughput_count": sum(1 for row in rows if row["reason"] == "no_throughput"),
        },
        "reviewer_rows": rows,
        "profile_hot_spots": _profile_hot_spots(rows),
    }


def _row(raw: dict[str, Any], index: int, warning_days: int, critical_days: int) -> dict[str, Any]:
    open_reviews = _int(raw.get("open_reviews"))
    completed = _int(raw.get("completed_last_7d") or raw.get("completed_reviews_last_7d"))
    capacity = _int(raw.get("capacity_per_week"))
    throughput = completed if completed > 0 else capacity
    days_to_clear = None if throughput <= 0 and open_reviews > 0 else (0 if open_reviews == 0 else ceil(open_reviews / throughput * 7))
    status, reason = _classify(open_reviews, throughput, days_to_clear, warning_days, critical_days)
    return {
        "reviewer": _text(raw.get("reviewer") or raw.get("reviewer_id") or raw.get("name")) or f"reviewer-{index}",
        "open_reviews": open_reviews,
        "completed_last_7d": completed,
        "capacity_per_week": capacity,
        "profiles": _list(raw.get("profiles") or raw.get("profile")),
        "days_to_clear": days_to_clear,
        "status": status,
        "reason": reason,
        "severity_rank": SEVERITY_RANK[status],
    }


def _classify(open_reviews: int, throughput: int, days_to_clear: int | None, warning_days: int, critical_days: int) -> tuple[str, str]:
    if open_reviews > 0 and throughput <= 0:
        return "critical", "no_throughput"
    if days_to_clear is not None and days_to_clear >= critical_days:
        return "critical", "critical_backlog"
    if days_to_clear is not None and days_to_clear >= warning_days:
        return "warning", "slow_clearance"
    return "healthy", "within_capacity"


def _profile_hot_spots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"open_review_count": 0, "reviewer_count": 0})
    for row in rows:
        profiles = row["profiles"] or ["unassigned"]
        for profile in profiles:
            totals[profile]["open_review_count"] += row["open_reviews"]
            totals[profile]["reviewer_count"] += 1
    hot_spots = [{"profile": profile, **values} for profile, values in totals.items()]
    hot_spots.sort(key=lambda row: (-row["open_review_count"], row["profile"].casefold()))
    return hot_spots


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
