"""JSON API renderer for feedback reviewer SLA breach status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.feedback_reviewer_sla_breach_status.v1"
KIND = "max.api.feedback_reviewer_sla_breach_status"


def feedback_reviewer_sla_breach_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    reviewers = [_reviewer(row, as_of) for row in _items(payload)]
    reviewers.sort(key=lambda row: (_rank(row["status"]), row["reviewer"]))
    summary = _summary(reviewers)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "reviewers": reviewers, "profile_hot_spots": _hot_spots(reviewers), "metadata": source_metadata(payload, reviewer_count=len(reviewers))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("reviewers")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _reviewer(row: Mapping[str, Any], as_of: datetime) -> dict[str, Any]:
    sla = max(0, int_or_zero(row.get("sla_hours"))) or 24
    opened = parse_datetime(row.get("oldest_opened_at"))
    age = round(max((as_of - opened).total_seconds() / 3600, 0), 2) if opened else None
    breached = max(0, int_or_zero(row.get("breached_reviews")))
    over_sla = age is not None and age > sla
    status = "critical" if breached > 1 or (age is not None and age > sla * 2) else "warning" if breached or over_sla else "ok"
    return {"reviewer": _bucket(row.get("reviewer"), "unknown_reviewer"), "profile": _bucket(row.get("profile"), "unknown_profile"), "open_reviews": max(0, int_or_zero(row.get("open_reviews"))), "oldest_opened_at": row.get("oldest_opened_at"), "oldest_open_age_hours": age, "sla_hours": sla, "breached_reviews": breached, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    breached = [row for row in rows if row["status"] != "ok"]
    return {"status": "critical" if critical else "warning" if warning else "ok", "reviewer_count": len(rows), "breached_reviewer_count": len(breached), "breached_review_total": sum(row["breached_reviews"] for row in rows), "overdue_profile_count": len({row["profile"] for row in breached})}


def _hot_spots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row["status"] != "ok":
            counts[row["profile"]] += max(row["breached_reviews"], 1)
    return [{"profile": profile, "breach_count": count} for profile, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
