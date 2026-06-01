"""Feedback outcome latency by profile export report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.exports.feedback_outcome_latency_by_profile_report.v1"
KIND = "max.exports.feedback_outcome_latency_by_profile_report"
DEFAULT_NOW = "2026-06-01T00:00:00+00:00"


def generate_feedback_outcome_latency_by_profile_report(
    feedback_events: Iterable[dict[str, Any]],
    *,
    now: str | datetime | None = None,
    sla_hours: float = 72,
) -> dict[str, Any]:
    as_of = _parse_datetime(now or DEFAULT_NOW) or _parse_datetime(DEFAULT_NOW)
    assert as_of is not None
    grouped: dict[str, list[float]] = defaultdict(list)
    overdue_by_profile: dict[str, int] = defaultdict(int)
    invalid_records: list[dict[str, Any]] = []

    for index, event in enumerate(feedback_events, start=1):
        profile = _text(event.get("profile") or event.get("profile_name") or event.get("persona")) or "unknown"
        created_at = _parse_datetime(event.get("idea_created_at"))
        recorded_at = _parse_datetime(event.get("outcome_recorded_at"))
        event_id = _text(event.get("id") or event.get("event_id") or event.get("idea_id")) or f"event-{index}"
        if created_at is None or recorded_at is None:
            invalid_records.append({"id": event_id, "profile": profile, "reason": "missing timestamp"})
            continue
        latency_hours = max(0.0, (recorded_at - created_at).total_seconds() / 3600)
        grouped[profile].append(latency_hours)
        if latency_hours > sla_hours:
            overdue_by_profile[profile] += 1

    profiles = []
    for profile, latencies in grouped.items():
        profiles.append(
            {
                "profile": profile,
                "count": len(latencies),
                "average_latency_hours": round(sum(latencies) / len(latencies), 2),
                "p95_latency_hours": round(_percentile(latencies, 0.95), 2),
                "overdue_count": overdue_by_profile.get(profile, 0),
            }
        )
    profiles.sort(key=lambda row: (-row["average_latency_hours"], row["profile"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": as_of.isoformat(),
        "sla_hours": sla_hours,
        "summary": {
            "profile_count": len(profiles),
            "valid_record_count": sum(row["count"] for row in profiles),
            "invalid_record_count": len(invalid_records),
            "overdue_count": sum(row["overdue_count"] for row in profiles),
        },
        "profiles": profiles,
        "slowest_profiles": profiles[:5],
        "invalid_records": sorted(invalid_records, key=lambda row: (row["profile"], row["id"])),
    }


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
