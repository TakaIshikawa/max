"""Profile signal freshness by source export report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def generate_profile_signal_freshness_by_source_report(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        profile = _text(record.get("profile") or record.get("profile_id")) or "unknown-profile"
        source = _text(record.get("source") or record.get("source_adapter")) or "unknown-source"
        group = groups.setdefault((profile, source), {"profile": profile, "source": source, "total_count": 0, "missing_timestamp_count": 0, "timestamps": [], "freshness_buckets": {"fresh": 0, "aging": 0, "stale": 0}})
        group["total_count"] += 1
        observed = _dt(record.get("observed_at") or record.get("published_at") or record.get("timestamp"))
        if observed is None:
            group["missing_timestamp_count"] += 1
            continue
        group["timestamps"].append(observed)
        group["freshness_buckets"][_bucket(observed)] += 1
    rows = []
    for group in groups.values():
        timestamps = group.pop("timestamps")
        group["oldest_observed_at"] = min(timestamps).isoformat() if timestamps else None
        group["newest_observed_at"] = max(timestamps).isoformat() if timestamps else None
        rows.append(group)
    rows.sort(key=lambda row: (row["profile"].lower(), row["source"].lower()))
    return {"schema_version": "max.profile_signal_freshness_by_source_report.v1", "kind": "max.profile_signal_freshness_by_source_report", "summary": {"row_count": len(rows), "total_count": sum(row["total_count"] for row in rows), "missing_timestamp_count": sum(row["missing_timestamp_count"] for row in rows)}, "rows": rows}


def _bucket(value: datetime) -> str:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    age_days = (now - value).total_seconds() / 86400
    if age_days <= 1:
        return "fresh"
    if age_days <= 7:
        return "aging"
    return "stale"


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
